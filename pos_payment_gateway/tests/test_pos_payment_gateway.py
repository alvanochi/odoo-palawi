from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

MANAGER_GROUPS = (
    "base.group_user,point_of_sale.group_pos_user,"
    "pos_payment_gateway.group_pos_payment_gateway_manager"
)
CASHIER_GROUPS = "base.group_user,point_of_sale.group_pos_user"
PAPER_URL = "https://open-api.paper.id/api/v1"


def _setup_common(cls):
    cls.pos_config = cls.env["pos.config"].create({"name": "Test POS PG"})
    cls.manager = new_test_user(cls.env, login="pg_manager", groups=MANAGER_GROUPS)
    cls.cashier = new_test_user(cls.env, login="pg_cashier", groups=CASHIER_GROUPS)
    cls.paper = cls.env.ref("pos_payment_gateway.gateway_paper")
    cls.other_gw = cls.env["pos.payment.gateway"].create(
        {"name": "Other GW", "code": "othergw", "default_base_url": "https://api.other.test/v2/"}
    )
    cls.Cred = cls.env["pos.payment.gateway.credential"]


@tagged("post_install", "-at_install")
class TestPosPaymentGateway(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _setup_common(cls)

    def _create(self, gateway=None, **kw):
        vals = {
            "pos_config_id": self.pos_config.id,
            "gateway_id": (gateway or self.paper).id,
            "client_id": "cid",
            "client_secret": "secret",
        }
        vals.update(kw)
        return self.Cred.with_user(self.manager).create(vals)

    def test_base_url_default_from_gateway(self):
        self.assertEqual(self._create().base_url, PAPER_URL)
        self.assertEqual(self._create(self.other_gw).base_url, "https://api.other.test/v2")

    def test_base_url_override_normalized(self):
        cred = self._create(base_url="https://sandbox.paper.id/api/v1/")
        self.assertEqual(cred.base_url, "https://sandbox.paper.id/api/v1")

    def test_base_url_must_be_https(self):
        with self.assertRaises(ValidationError):
            self._create(base_url="http://open-api.paper.id/api/v1")

    def test_gateway_code_format(self):
        with self.assertRaises(ValidationError):
            self.env["pos.payment.gateway"].create({"name": "X", "code": "Bad Code"})

    def test_one_active_per_pos_and_gateway(self):
        self._create()
        self._create(self.other_gw)  # gateway lain di POS yang sama: boleh
        with self.assertRaises(ValidationError):
            self._create(client_id="dup")

    def test_cashier_cannot_access(self):
        self._create()
        with self.assertRaises(AccessError):
            self.Cred.with_user(self.cashier).search([])

    def test_get_credential(self):
        cred = self._create(client_id="abc")
        cred.extra_param_ids = [(0, 0, {"key": "webhook_token", "value": "wh"})]
        res = self.Cred.get_credential(self.pos_config.id, "paper", fallback_env=False)
        self.assertEqual(res["client_id"], "abc")
        self.assertEqual(res["client_secret"], "secret")
        self.assertEqual(res["extra_params"], {"webhook_token": "wh"})
        self.assertEqual(res["source"], "database")

    def test_get_credential_missing(self):
        self.assertIsNone(
            self.Cred.get_credential(self.pos_config.id, "paper", fallback_env=False)
        )


@tagged("post_install", "-at_install")
class TestPosPaymentGatewayApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _setup_common(cls)
        cls.Cred.create(
            {
                "pos_config_id": cls.pos_config.id,
                "gateway_id": cls.paper.id,
                "client_id": "abc123",
                "client_secret": "s3cr3t",
            }
        )

    def _key_for(self, user):
        Keys = self.env["res.users.apikeys"].with_user(user)
        try:  # Odoo 18: _generate(scope, name, expiration_date)
            return Keys._generate(None, "test", fields.Datetime.now() + timedelta(days=1))
        except TypeError:  # signature lama: _generate(scope, name)
            return Keys._generate(None, "test")

    def _get(self, pos_config_id, key=None, gateway=None):
        url = f"/api/payment-gateway/credential/{pos_config_id}"
        if gateway:
            url += f"?gateway={gateway}"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        return self.url_open(url, headers=headers)

    def test_unauthorized(self):
        self.assertEqual(self._get(self.pos_config.id).status_code, 401)
        self.assertEqual(self._get(self.pos_config.id, key="wrong").status_code, 401)

    def test_forbidden_for_cashier(self):
        res = self._get(self.pos_config.id, key=self._key_for(self.cashier))
        self.assertEqual(res.status_code, 403)

    def test_success_single_gateway(self):
        res = self._get(self.pos_config.id, key=self._key_for(self.manager), gateway="paper")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["gateway"], "paper")
        self.assertEqual(data["client_id"], "abc123")
        self.assertEqual(data["client_secret"], "s3cr3t")
        self.assertEqual(data["base_url"], PAPER_URL)

    def test_success_all_gateways(self):
        res = self._get(self.pos_config.id, key=self._key_for(self.manager))
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual([d["gateway"] for d in data], ["paper"])

    def test_not_found(self):
        key = self._key_for(self.manager)
        res = self._get(999999, key=key, gateway="paper")
        self.assertEqual(res.json()["error"]["code"], "POS_CONFIG_NOT_FOUND")
        res = self._get(self.pos_config.id, key=key, gateway="nope")
        self.assertEqual(res.json()["error"]["code"], "GATEWAY_NOT_FOUND")
        res = self._get(self.pos_config.id, key=key, gateway="othergw")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "CREDENTIAL_NOT_FOUND")
