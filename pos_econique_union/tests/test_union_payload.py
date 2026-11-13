import unittest
from unittest import mock

import requests

from odoo.addons.pos_econique_union.services import econique_client, union_payload

CFG = {
    "version": "1.0.0",
    "tenant_code": "TN00001",
    "tenant_name": "Cafe Pubin",
    "service_fee_percent": 1,
    "send_payment_vendor": True,
}


def _line(qty=1, unit=20000, pct=0, discount=False, code="P1"):
    return {
        "product_code": code,
        "product_name": "Product %s" % code,
        "price_code": "STANDARD",
        "price_name": "Standard Price",
        "qty": qty,
        "unit_price": unit,
        "discount_percent": pct,
        "is_discount_line": discount,
    }


def _order(lines, ppn=2200):
    return {
        "invoice_number": "INV-1",
        "transaction_date": "2026-11-12 19:22:08",
        "voucher_code": None,
        "ppn": ppn,
        "lines": lines,
        "payment": {
            "issuer": "Paper.id",
            "transaction_id": "TRX-1",
            "type": "QRIS",
            "provider": "OVO",
            "status": "success",
            "date": "2026-11-12 19:22:08",
        },
    }


class TestUnionPayload(unittest.TestCase):
    def test_documentation_example(self):
        """bruto 20000, service 200, ppn 2200 -> netto 17600 (Econique example)."""
        p = union_payload.build_payload(_order([_line()]), CFG)
        self.assertEqual(p["bruto"], "20000.00")
        self.assertEqual(p["service_fee"], "200.00")
        self.assertEqual(p["ppn"], "2200.00")
        self.assertEqual(p["netto"], "17600.00")
        self.assertEqual(p["discount"], "0.00")
        self.assertIsNone(p["voucher_code"])

    def test_required_fields_present(self):
        p = union_payload.build_payload(_order([_line()]), CFG)
        for key in (
            "version", "invoice_number", "tenant_code", "tenant_name", "voucher_code",
            "transaction_date", "bruto", "discount", "service_fee", "ppn", "netto",
            "payment_issuer", "payment_transactions_id", "payment_type",
            "payment_provider", "payment_status", "payment_date", "items",
        ):
            self.assertIn(key, p)
        self.assertEqual(p["payment_vendor"], "Paper.id")
        for key in (
            "product_code", "product_name", "price_code", "price_name", "unit_price",
            "discount_percent", "discount_nominal", "amount", "total_price",
        ):
            self.assertIn(key, p["items"][0])

    def test_payment_vendor_can_be_disabled(self):
        p = union_payload.build_payload(_order([_line()]), dict(CFG, send_payment_vendor=False))
        self.assertNotIn("payment_vendor", p)

    def test_percent_discount_per_line(self):
        p = union_payload.build_payload(
            _order([_line(qty=2, unit=10000, pct=10)], ppn=0), dict(CFG, service_fee_percent=0))
        item = p["items"][0]
        self.assertEqual(item["amount"], 2)
        self.assertEqual(item["discount_nominal"], "2000.00")
        self.assertEqual(item["total_price"], "20000.00")
        self.assertEqual(p["bruto"], "20000.00")
        self.assertEqual(p["discount"], "10.00")
        self.assertEqual(p["netto"], "18000.00")

    def test_reward_line_is_a_discount_not_an_item(self):
        lines = [_line(unit=16500, code="A"), _line(unit=33000, code="B"),
                 _line(unit=-5445, code="REWARD", discount=True)]
        p = union_payload.build_payload(_order(lines, ppn=0), dict(CFG, service_fee_percent=0))
        self.assertEqual(len(p["items"]), 2)
        self.assertEqual(p["bruto"], "49500.00")
        self.assertEqual(p["discount"], "11.00")
        self.assertEqual(p["netto"], "44055.00")

    def test_fractional_qty_keeps_the_total(self):
        p = union_payload.build_payload(
            _order([_line(qty=0.5, unit=30000)], ppn=0), dict(CFG, service_fee_percent=0))
        item = p["items"][0]
        self.assertEqual(item["amount"], 1)
        self.assertEqual(item["unit_price"], "15000.00")
        self.assertEqual(item["total_price"], "15000.00")
        self.assertEqual(p["bruto"], "15000.00")

    def test_discount_never_exceeds_100_percent(self):
        lines = [_line(unit=10000), _line(unit=-15000, discount=True)]
        p = union_payload.build_payload(_order(lines, ppn=0), dict(CFG, service_fee_percent=0))
        self.assertEqual(p["discount"], "100.00")

    def test_order_without_items_is_rejected(self):
        with self.assertRaises(ValueError):
            union_payload.build_payload(_order([_line(unit=-100, discount=True)]), CFG)


def _response(status=200, data=None, text=""):
    res = mock.Mock()
    res.status_code = status
    res.json.return_value = data if data is not None else {}
    res.text = text
    return res


class TestEconiqueClient(unittest.TestCase):
    def _client(self):
        return econique_client.EconiqueClient(
            "https://stg-api.econique.id/", "u", "p", basic_auth=("u", "p"), timeout=5)

    def test_login_ok(self):
        data = {"status": "Success", "access_token": "123|abc"}
        with mock.patch.object(requests, "post", return_value=_response(200, data)) as post:
            self.assertEqual(self._client().login(), "123|abc")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://stg-api.econique.id/api/kuliner/login")
        self.assertEqual(kwargs["json"], {"username": "u", "password": "p"})
        self.assertEqual(kwargs["auth"], ("u", "p"))

    def test_login_failure(self):
        data = {"status": "Error", "message": "Wrong password"}
        with mock.patch.object(requests, "post", return_value=_response(401, data)):
            with self.assertRaises(econique_client.EconiqueLoginError):
                self._client().login()

    def test_transaction_uses_bearer_token(self):
        data = {"status": "success", "code": "S.TC.PT.001"}
        with mock.patch.object(requests, "post", return_value=_response(200, data)) as post:
            status, body, _text = self._client().post_transaction("tok", {"a": 1})
        self.assertEqual((status, body["code"]), (200, "S.TC.PT.001"))
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://stg-api.econique.id/api/kuliner/transaction")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok")

    def test_network_failure(self):
        with mock.patch.object(requests, "post", side_effect=requests.Timeout("slow")):
            with self.assertRaises(econique_client.EconiqueNetworkError):
                self._client().post_transaction("tok", {})

    def test_non_json_response(self):
        res = _response(502, text="<html>Bad Gateway</html>")
        res.json.side_effect = ValueError("no json")
        with mock.patch.object(requests, "post", return_value=res):
            status, body, text = self._client().post_transaction("tok", {})
        self.assertEqual((status, body), (502, {}))
        self.assertIn("Bad Gateway", text)


if __name__ == "__main__":
    unittest.main()
