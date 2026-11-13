from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services.econique_client import EconiqueClient, EconiqueError

MANAGER_GROUP = "pos_econique_union.group_pos_econique_manager"

BASE_URLS = {
    "staging": "https://stg-api.econique.id",
    "production": "https://api.econique.co.id",
}


TOKEN_RESET_FIELDS = {
    "environment", "base_url", "username", "password",
    "login_basic_auth", "basic_auth_user", "basic_auth_password",
}


def _normalize_url(url):
    return (url or "").strip().rstrip("/")


class PosEconiqueConfig(models.Model):
    """Union Kuliner Econique integration settings for one POS config.

    Standalone: it has nothing to do with the payment gateway credentials. One
    active record per POS config; a POS config without an active record sends
    nothing to Econique.
    """

    _name = "pos.econique.config"
    _description = "POS Econique Integration Config"
    _inherit = ["mail.thread"]
    _order = "pos_config_id, id"

    pos_config_id = fields.Many2one(
        "pos.config",
        string="POS Config",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="pos_config_id.company_id", store=True, readonly=True)
    active = fields.Boolean(default=True, tracking=True)
    note = fields.Text()

    # --- Connection -------------------------------------------------------
    environment = fields.Selection(
        [("staging", "Staging"), ("production", "Production")],
        default="production",
        required=True,
        tracking=True,
    )
    base_url = fields.Char(
        string="Base URL",
        compute="_compute_base_url",
        store=True,
        readonly=False,
        precompute=True,
        required=True,
        tracking=True,
        help="Filled from the environment; can be edited.",
    )
    username = fields.Char(string="API Username", required=True, tracking=True)
    # Deliberately NOT tracked so the value never reaches the chatter or logs.
    password = fields.Char(
        string="API Password", required=True, groups=MANAGER_GROUP, copy=False
    )
    login_basic_auth = fields.Boolean(
        string="Login with Basic Auth",
        default=True,
        help="The documentation says the login endpoint uses Basic Auth. When on, a Basic "
        "header is sent with the username/password below (empty = same as the API "
        "username/password).",
    )
    basic_auth_user = fields.Char(string="Basic Auth Username")
    basic_auth_password = fields.Char(
        string="Basic Auth Password", groups=MANAGER_GROUP, copy=False
    )
    # The token comes from logging in; it is never typed in manually.
    token = fields.Char(groups=MANAGER_GROUP, copy=False)
    token_date = fields.Datetime(
        string="Token Obtained At", groups=MANAGER_GROUP, copy=False, readonly=True
    )

    # --- Tenant identity --------------------------------------------------
    tenant_code = fields.Char(
        string="Tenant Code", tracking=True, help="Sent as tenant_code. Example: TN00001."
    )
    tenant_name = fields.Char(
        string="Tenant Name", tracking=True, help="Sent as tenant_name. Example: Cafe Pubin."
    )

    # --- Sending ----------------------------------------------------------
    auto_send = fields.Boolean(
        string="Auto Send",
        default=True,
        tracking=True,
        help="Send the order to Econique automatically once it is paid in this POS "
        "(from the cashier screen as well as from the REST API). When off, nothing "
        "is queued and queued transactions are not sent by the cron.",
    )
    api_version = fields.Char(string="API Version", default="1.0.0")
    max_attempts = fields.Integer(
        string="Max Attempts",
        default=5,
        help="After this many temporary failures (network/5xx) the transaction is marked Failed.",
    )
    timeout = fields.Integer(string="Timeout (seconds)", default=20)

    # --- Mapping rules ----------------------------------------------------
    invoice_source = fields.Selection(
        [("pos_reference", "POS Reference"), ("name", "Order Name")],
        string="invoice_number Source",
        default="pos_reference",
    )
    product_code_source = fields.Selection(
        [("default_code", "Internal Reference"), ("barcode", "Barcode"), ("id", "Product ID")],
        string="product_code Source",
        default="default_code",
        help="When empty on the product, the fallback order is: Internal Reference, "
        "Barcode, Product ID.",
    )
    price_from_pricelist = fields.Boolean(
        string="price_code from Pricelist",
        help="On: price_code = order pricelist ID, price_name = pricelist name. "
        "Off: use the fixed values below.",
    )
    price_code = fields.Char(string="Fixed price_code", default="STANDARD")
    price_name = fields.Char(string="Fixed price_name", default="Standard Price")
    service_fee_percent = fields.Float(
        string="Service Fee (%)",
        default=0.0,
        help="Percentage of (gross - discount). Use 0 when there is no service charge.",
    )
    default_issuer = fields.Char(
        string="Default payment_issuer",
        default="PT PHI",
        help="Per the documentation, cash payments use 'PT PHI'. Can be overridden per "
        "payment method in the mapping table.",
    )
    send_payment_vendor = fields.Boolean(
        string="Also Send payment_vendor",
        default=True,
        help="The example request in the documentation uses 'payment_vendor' while the "
        "field table uses 'payment_issuer'. On: both are sent.",
    )
    payment_map_ids = fields.One2many(
        "pos.econique.payment.map", "config_id", string="Payment Method Mapping"
    )
    transaction_count = fields.Integer(compute="_compute_transaction_count")

    # ------------------------------------------------------------------ #
    # Compute / display / normalization
    # ------------------------------------------------------------------ #
    @api.depends("environment")
    def _compute_base_url(self):
        for rec in self:
            rec.base_url = BASE_URLS.get(rec.environment) or rec.base_url or False

    @api.depends("pos_config_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Econique - %s" % (rec.pos_config_id.display_name or "")

    def _compute_transaction_count(self):
        Transaction = self.env["pos.econique.transaction"]
        for rec in self:
            rec.transaction_count = Transaction.search_count([("econique_config_id", "=", rec.id)])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("base_url"):
                vals["base_url"] = _normalize_url(vals["base_url"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("base_url"):
            vals["base_url"] = _normalize_url(vals["base_url"])
        # A token belongs to one environment + login: drop it when any of those change.
        if TOKEN_RESET_FIELDS & set(vals) and "token" not in vals:
            vals = dict(vals, token=False, token_date=False)
        res = super().write(vals)
        if "password" in vals:
            for rec in self:
                rec.message_post(body=_("API password updated."))
        return res

    # ------------------------------------------------------------------ #
    # Constraints
    # ------------------------------------------------------------------ #
    @api.constrains("base_url")
    def _check_base_url(self):
        for rec in self:
            if not (rec.base_url or "").startswith("https://"):
                raise ValidationError(_("Base URL must start with https://"))

    @api.constrains("auto_send", "tenant_code", "tenant_name")
    def _check_tenant(self):
        for rec in self:
            if rec.auto_send and not (rec.tenant_code and rec.tenant_name):
                raise ValidationError(
                    _("Tenant Code and Tenant Name are required when Auto Send is on.")
                )

    @api.constrains("pos_config_id", "active")
    def _check_unique_active(self):
        for rec in self.filtered("active"):
            dup = self.sudo().search_count(
                [
                    ("id", "!=", rec.id),
                    ("pos_config_id", "=", rec.pos_config_id.id),
                    ("active", "=", True),
                ]
            )
            if dup:
                raise ValidationError(
                    _(
                        "POS config %(pos)s already has an active Econique configuration.",
                        pos=rec.pos_config_id.display_name,
                    )
                )

    def init(self):
        # DB-level safety net: one active config per POS config.
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS pos_econique_config_active_uniq
            ON pos_econique_config (pos_config_id)
            WHERE active
            """
        )

    # ------------------------------------------------------------------ #
    # Econique API
    # ------------------------------------------------------------------ #
    def _client(self):
        self.ensure_one()
        config = self.sudo()
        basic_auth = None
        if config.login_basic_auth:
            basic_auth = (
                config.basic_auth_user or config.username,
                config.basic_auth_password or config.password,
            )
        return EconiqueClient(
            base_url=config.base_url,
            username=config.username,
            password=config.password,
            basic_auth=basic_auth,
            timeout=config.timeout or 20,
        )

    def _login(self, client=None):
        """Log in to Econique, store the token and return it."""
        self.ensure_one()
        config = self.sudo()
        client = client or config._client()
        token = client.login()
        config.write({"token": token, "token_date": fields.Datetime.now()})
        return token

    # ------------------------------------------------------------------ #
    # Buttons
    # ------------------------------------------------------------------ #
    def action_test_login(self):
        self.ensure_one()
        try:
            self._login()
        except EconiqueError as e:
            kind, message, sticky = "danger", str(e), True
        else:
            kind, message, sticky = "success", _("Login succeeded, token saved."), False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Econique Test Login"),
                "message": message,
                "type": kind,
                "sticky": sticky,
            },
        }

    def action_clear_token(self):
        """Forget the cached token; the next send logs in again."""
        self.sudo().write({"token": False, "token_date": False})
        return True

    def action_view_transactions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "pos_econique_union.pos_econique_transaction_action"
        )
        action["domain"] = [("econique_config_id", "=", self.id)]
        action["context"] = {}
        return action
