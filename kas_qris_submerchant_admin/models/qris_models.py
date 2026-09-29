# -*- coding: utf-8 -*-
import base64
import logging
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from datetime import (
    timedelta
)
_logger = logging.getLogger(__name__)


class KasQrisApiMixin(models.AbstractModel):
    _name = "kas.qris.api.mixin"
    _description = "QRIS API Helpers (Winpay)"

    def _get_qris_api_config(self):
        IrConfig = self.env["ir.config_parameter"].sudo()
        base_url = IrConfig.get_param("base_url_api_external")
        api_token = IrConfig.get_param("api_token_external")

        if not base_url or not api_token:
            raise UserError(
                _(
                    "QRIS API Base URL dan/atau API Token belum diset di System Parameters "
                    "(base_url_api_external, api_token_external)."
                )
            )
        return base_url, api_token

    def _binary_to_file_tuple(self, binary_field, filename, mimetype="image/jpeg"):
        if not binary_field:
            return None
        data = base64.b64decode(binary_field)
        return (filename or "file.jpg", data, mimetype)

    def _winpay_get(self, path, use_x_api_token=False):
        base_url, api_token = self._get_qris_api_config()
        url = f"{base_url.rstrip('/')}{path}"

        headers = {"Accept": "application/json"}
        if use_x_api_token:
            headers["X-API-TOKEN"] = api_token

        _logger.info("Calling Winpay GET %s", url)

        try:
            response = requests.get(url, headers=headers, timeout=60)
        except Exception as e:
            _logger.exception("Error calling Winpay API %s", url)
            raise UserError(_("Gagal menghubungi server Winpay: %s") % e)

        if response.status_code != 200:
            raise UserError(
                _("Request ke Winpay gagal. Status code: %s\nResponse: %s")
                % (response.status_code, response.text)
            )

        try:
            res_json = response.json()
        except Exception:
            raise UserError(_("Response Winpay bukan JSON valid: %s") % response.text)

        if isinstance(res_json, list):
            return res_json

        if isinstance(res_json, dict) and isinstance(res_json.get("data"), list):
            return res_json["data"]

        if (
            isinstance(res_json, dict)
            and isinstance(res_json.get("data"), dict)
            and isinstance(res_json["data"].get("data"), list)
        ):
            return res_json["data"]["data"]

        raise UserError(_("Struktur data Winpay tidak seperti yang diharapkan: %s") % res_json)

    # ✅ FIXED: list endpoint parsing sesuai response kamu:
    # {
    #   "success": true,
    #   "data": [ ... ],
    #   "pagination": {"current_page": 1, "last_page": 1, ...}
    # }
    def _qris_get_submerchant_list(self, page=1, per_page=20):
        base_url, api_token = self._get_qris_api_config()
        url = f"{base_url.rstrip('/')}/api/sub-merchant/list?paginate=true&per_page={per_page}&page={page}"

        headers = {"Accept": "application/json", "X-API-TOKEN": api_token}
        _logger.info("Calling QRIS submerchant list API: %s", url)

        try:
            response = requests.get(url, headers=headers, timeout=60)
        except Exception as e:
            _logger.exception("Error calling QRIS submerchant list API")
            raise UserError(_("Gagal menghubungi server QRIS (list): %s") % e)

        if response.status_code != 200:
            raise UserError(_("Request list gagal. Status code: %s\nResponse: %s") % (response.status_code, response.text))

        try:
            res_json = response.json()
        except Exception:
            raise UserError(_("Response list bukan JSON valid: %s") % response.text)

        items = res_json.get("data") if isinstance(res_json.get("data"), list) else []
        pagination = res_json.get("pagination") if isinstance(res_json.get("pagination"), dict) else {}

        return items, pagination


    def _qris_get_submerchant_detail(self, sub_id):
        base_url, api_token = self._get_qris_api_config()
        url = f"{base_url.rstrip('/')}/api/sub-merchant/detail/{sub_id}"

        headers = {
            "Accept": "application/json",
            "X-API-TOKEN": api_token,
        }

        _logger.info("Calling QRIS submerchant detail API: %s", url)

        try:
            response = requests.get(url, headers=headers, timeout=60)
        except Exception as e:
            _logger.exception("Error calling QRIS submerchant detail API")
            raise UserError(_("Gagal menghubungi server QRIS (detail): %s") % e)

        if response.status_code != 200:
            raise UserError(
                _("Request detail gagal. Status code: %s\nResponse: %s")
                % (response.status_code, response.text)
            )

        try:
            res_json = response.json()
        except Exception:
            raise UserError(_("Response detail bukan JSON valid: %s") % response.text)

        data = res_json.get("data")
        if isinstance(data, dict) and not isinstance(data.get("data"), (list, dict)):
            detail = data
        elif isinstance(data, dict) and isinstance(data.get("data"), dict):
            detail = data["data"]
        else:
            detail = res_json

        if not isinstance(detail, dict):
            raise UserError(_("Struktur response detail QRIS tidak sesuai harapan: %s") % res_json)

        return detail


# ---------- Master data ----------
class KasQrisProvince(models.Model):
    _name = "kas.qris.province"
    _description = "QRIS Province (Winpay)"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char("External ID", required=True, index=True)

    _sql_constraints = [
        ("qris_province_code_uniq", "unique(code)", "Province code must be unique!"),
    ]

    def action_sync_from_winpay(self):
        self.env["kas.qris.sync.service"].sudo().sync_provinces()
        return self.env["kas.qris.sync.service"]._notify(
            _("Sync Provinces Complete"),
            _("Master Province berhasil di-sync dari Winpay."),
        )


class KasQrisCity(models.Model):
    _name = "kas.qris.city"
    _description = "QRIS City (Winpay)"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char("External ID", required=True, index=True)
    province_id = fields.Many2one("kas.qris.province", string="Province", required=True)

    _sql_constraints = [
        ("qris_city_code_uniq", "unique(code)", "City code must be unique!"),
    ]

    def action_sync_from_winpay(self):
        self.env["kas.qris.sync.service"].sudo().sync_cities()
        return self.env["kas.qris.sync.service"]._notify(
            _("Sync Cities Complete"),
            _("Master City berhasil di-sync dari Winpay."),
        )


class KasQrisMerchantType(models.Model):
    _name = "kas.qris.merchant.type"
    _description = "QRIS Merchant Type"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char("Code", required=True, index=True)

    _sql_constraints = [
        ("qris_merchant_type_code_uniq", "unique(code)", "Merchant type code must be unique!"),
    ]

    def action_sync_from_winpay(self):
        self.env["kas.qris.sync.service"].sudo().sync_merchant_type()
        return self.env["kas.qris.sync.service"]._notify(
            _("Sync Merchant Type Complete"),
            _("Master Merchant Type berhasil di-sync dari Winpay."),
        )


class KasQrisMerchantCriteria(models.Model):
    _name = "kas.qris.merchant.criteria"
    _description = "QRIS Merchant Criteria"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char("Code", required=True, index=True)

    _sql_constraints = [
        ("qris_merchant_criteria_code_uniq", "unique(code)", "Merchant criteria code must be unique!"),
    ]

    def action_sync_from_winpay(self):
        self.env["kas.qris.sync.service"].sudo().sync_merchant_criteria()
        return self.env["kas.qris.sync.service"]._notify(
            _("Sync Merchant Criteria Complete"),
            _("Master Merchant Criteria berhasil di-sync dari Winpay."),
        )


class KasQrisMerchantCategory(models.Model):
    _name = "kas.qris.merchant.category"
    _description = "QRIS Merchant Category (MCC)"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char("MCC", required=True, index=True)

    _sql_constraints = [
        ("qris_merchant_category_code_uniq", "unique(code)", "Merchant category code must be unique!"),
    ]

    def action_sync_from_winpay(self):
        self.env["kas.qris.sync.service"].sudo().sync_merchant_category()
        return self.env["kas.qris.sync.service"]._notify(
            _("Sync Merchant Category Complete"),
            _("Master Merchant Category berhasil di-sync dari Winpay."),
        )


class KasQrisBankCode(models.Model):
    _name = "kas.qris.bank.code"
    _description = "QRIS Bank Code"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char("Bank Code", required=True, index=True)

    _sql_constraints = [
        ("qris_bank_code_uniq", "unique(code)", "Bank code must be unique!"),
    ]

    def action_sync_from_winpay(self):
        self.env["kas.qris.sync.service"].sudo().sync_bank_code()
        return self.env["kas.qris.sync.service"]._notify(
            _("Sync Bank Code Complete"),
            _("Master Bank Code berhasil di-sync dari Winpay."),
        )


class KasQrisSyncService(models.TransientModel):
    _name = "kas.qris.sync.service"
    _inherit = "kas.qris.api.mixin"
    _description = "QRIS Sync Service"

    @api.model
    def _notify(self, title, message, typ="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": title, "message": message, "type": typ, "sticky": False},
        }

    # helper kecil biar required aman
    def _norm_required_char(self, v):
        v = (v or "").strip()
        return v or False

    @api.model
    def sync_provinces(self):
        data = self._winpay_get("/api/winpay/provinces", use_x_api_token=True)
        Province = self.env["kas.qris.province"].sudo()

        for item in data:
            code = self._norm_required_char(item.get("id") and str(item.get("id")))
            name = self._norm_required_char(item.get("name"))

            # kalau required gak terpenuhi, skip (jangan create record invalid)
            if not code or not name:
                continue

            rec = Province.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Province.create(vals)

    @api.model
    def sync_cities(self):
        data = self._winpay_get("/api/winpay/city", use_x_api_token=True)
        Province = self.env["kas.qris.province"].sudo()
        City = self.env["kas.qris.city"].sudo()

        for item in data:
            code = self._norm_required_char(item.get("id") and str(item.get("id")))
            name = self._norm_required_char(item.get("name"))
            prov_id = item.get("province_id")

            # city requires: code, name, province_id
            if not code or not name or not prov_id:
                continue

            prov_code = str(prov_id)
            prov = Province.search([("code", "=", prov_code)], limit=1)

            if not prov:
                prov_name = self._norm_required_char((item.get("province") or {}).get("name"))
                # province requires name; kalau gak ada, skip city (atau set fallback)
                if not prov_name:
                    continue

                prov = Province.create({"code": prov_code, "name": prov_name})

            rec = City.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name, "province_id": prov.id}
            if rec:
                rec.write(vals)
            else:
                City.create(vals)

    @api.model
    def sync_merchant_type(self):
        data = self._winpay_get("/api/winpay/type-merchant", use_x_api_token=True)
        Type = self.env["kas.qris.merchant.type"].sudo()

        for item in data:
            code = self._norm_required_char(item.get("code") and str(item.get("code")))
            name = self._norm_required_char(item.get("name"))
            if not code or not name:
                continue

            rec = Type.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Type.create(vals)

    @api.model
    def sync_merchant_criteria(self):
        data = self._winpay_get("/api/winpay/merchant-criteria", use_x_api_token=True)
        Criteria = self.env["kas.qris.merchant.criteria"].sudo()

        for item in data:
            code = self._norm_required_char(item.get("code") and str(item.get("code")))
            name = self._norm_required_char(item.get("name"))
            if not code or not name:
                continue

            rec = Criteria.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Criteria.create(vals)

    @api.model
    def sync_merchant_category(self):
        data = self._winpay_get("/api/winpay/merchant-category", use_x_api_token=True)
        Category = self.env["kas.qris.merchant.category"].sudo()

        for item in data:
            code = self._norm_required_char(item.get("code") and str(item.get("code")))
            name = self._norm_required_char(item.get("name"))
            if not code or not name:
                continue

            rec = Category.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Category.create(vals)

    @api.model
    def sync_bank_code(self):
        data = self._winpay_get("/api/winpay/bank-code", use_x_api_token=True)
        Bank = self.env["kas.qris.bank.code"].sudo()

        for item in data:
            code = self._norm_required_char(item.get("code") and str(item.get("code")))
            name = self._norm_required_char(item.get("name"))
            if not code or not name:
                continue

            rec = Bank.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Bank.create(vals)

class KasQrisSyncService(models.TransientModel):
    _name = "kas.qris.sync.service"
    _inherit = "kas.qris.api.mixin"
    _description = "QRIS Sync Service"

    @api.model
    def _notify(self, title, message, typ="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": typ,
                "sticky": False,
            },
        }


    @api.model
    def sync_provinces(self):
        data = self._winpay_get("/api/winpay/provinces", use_x_api_token=True)
        Province = self.env["kas.qris.province"].sudo()
        for item in data:
            code = str(item.get("id"))
            name = item.get("name") or ""
            if not code:
                continue
            rec = Province.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Province.create(vals)

    @api.model
    def sync_cities(self):
        data = self._winpay_get("/api/winpay/city", use_x_api_token=True)
        Province = self.env["kas.qris.province"].sudo()
        City = self.env["kas.qris.city"].sudo()

        for item in data:
            code = str(item.get("id"))
            name = item.get("name") or ""
            prov_id = item.get("province_id")
            if not code or not prov_id:
                continue

            prov = Province.search([("code", "=", str(prov_id))], limit=1)
            if not prov:
                prov = Province.create({
                    "code": str(prov_id),
                    "name": (item.get("province") or {}).get("name", str(prov_id)),
                })

            rec = City.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name, "province_id": prov.id}
            if rec:
                rec.write(vals)
            else:
                City.create(vals)

    @api.model
    def sync_merchant_type(self):
        data = self._winpay_get("/api/winpay/type-merchant", use_x_api_token=True)
        Type = self.env["kas.qris.merchant.type"].sudo()
        for item in data:
            code = str(item.get("code"))
            name = item.get("name") or ""
            if not code:
                continue
            rec = Type.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Type.create(vals)

    @api.model
    def sync_merchant_criteria(self):
        data = self._winpay_get("/api/winpay/merchant-criteria", use_x_api_token=True)
        Criteria = self.env["kas.qris.merchant.criteria"].sudo()
        for item in data:
            code = str(item.get("code"))
            name = item.get("name") or ""
            if not code:
                continue
            rec = Criteria.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Criteria.create(vals)

    @api.model
    def sync_merchant_category(self):
        data = self._winpay_get("/api/winpay/merchant-category", use_x_api_token=True)
        Category = self.env["kas.qris.merchant.category"].sudo()
        for item in data:
            code = str(item.get("code"))
            name = item.get("name") or ""
            if not code:
                continue
            rec = Category.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Category.create(vals)

    @api.model
    def sync_bank_code(self):
        data = self._winpay_get("/api/winpay/bank-code", use_x_api_token=True)
        Bank = self.env["kas.qris.bank.code"].sudo()
        for item in data:
            code = str(item.get("code"))
            name = item.get("name") or ""
            if not code:
                continue
            rec = Bank.search([("code", "=", code)], limit=1)
            vals = {"code": code, "name": name}
            if rec:
                rec.write(vals)
            else:
                Bank.create(vals)



    def _dedupe_store_name(self, Sub, name, exclude_id=None):
        base = (name or "").strip() or "Store"
        candidate = base
        i = 2

        dom = [("store_name", "=ilike", candidate)]
        if exclude_id:
            dom = [("id", "!=", exclude_id)] + dom

        while Sub.search(dom, limit=1):
            candidate = f"{base} ({i})"
            i += 1
            dom = [("store_name", "=ilike", candidate)]
            if exclude_id:
                dom = [("id", "!=", exclude_id)] + dom

        return candidate


    
    @api.model
    def sync_submerchant_list(self, per_page=50, page_start=1, max_pages=1, company_id=None):
        Sub = self.env["kas.qris.submerchant"].sudo()
        Company = self.env["res.company"].sudo()
        ICP = self.env["ir.config_parameter"].sudo()

        company = Company.browse(company_id) if company_id else (
            Company.browse(self.env.context.get("current_company_id"))
            if self.env.context.get("current_company_id")
            else Company.search([], limit=1)
        )
        company = company.sudo()

        def k(s):  # key helper
            return f"qris.submerchant.{s}.{company.id}"

        # kalau caller tidak kasih page_start, lanjut dari last_page
        if not page_start:
            last_page = int(ICP.get_param(k("last_page")) or 0)
            page_start = last_page + 1

        page = int(page_start or 1)
        end_page = page + int(max_pages or 1) - 1

        total_synced = 0
        last_page_seen = None

        while page <= end_page:
            items, pagination = self._qris_get_submerchant_list(page=page, per_page=per_page)
            if not items:
                break

            # upsert items
            for item in items:
                merchant_id = item.get("id_merchant") or item.get("merchant_id")
                detail_id = item.get("id")
                if not merchant_id:
                    continue

                vals = {
                    "company_id": company.id,
                    "merchant_id": str(merchant_id) if merchant_id else False,
                    "detail_id": str(detail_id) if detail_id else False,
                    "owner_name": item.get("owner_name") or "",
                    "store_name": item.get("store_name") or str(merchant_id),
                    "address": item.get("address") or "",
                    "email": item.get("email") or "",
                    "phone_number": item.get("phone_number") or "",
                    "postcode": item.get("postcode") or "",
                    "status": item.get("status") or "",
                }

                merchant_id = item.get("id_merchant") or item.get("merchant_id")
                detail_id = item.get("id")

                dom = [("company_id", "=", company.id)]
                if detail_id:
                    dom += [("detail_id", "=", str(detail_id))]
                elif merchant_id:
                    dom += [("merchant_id", "=", str(merchant_id))]
                else:
                    continue

                existing = Sub.search(dom, limit=1)

                vals["store_name"] = self._dedupe_store_name(Sub, vals.get("store_name"), exclude_id=existing.id if existing else None)
                if existing:
                    existing.write(vals)
                else:
                    Sub.create(vals)

                total_synced += 1

            # ambil info pagination (robust)
            cur = pagination.get("current_page") if isinstance(pagination, dict) else None
            last = pagination.get("last_page") if isinstance(pagination, dict) else None

            if cur:
                cur = int(cur)
            if last:
                last = int(last)

            if last:
                last_page_seen = last

            # simpan progres: page yang BARU selesai diproses
            ICP.set_param(k("last_page"), str(page))
            ICP.set_param(k("last_sync_at"), fields.Datetime.to_string(fields.Datetime.now()))
            if last_page_seen:
                ICP.set_param(k("last_page_max"), str(last_page_seen))

            # stop kalau sudah last page
            if cur and last and cur >= last:
                # reset supaya next run mulai dari 1 lagi
                ICP.set_param(k("last_page"), "0")
                break

            page += 1

        return total_synced


# ---------- Submerchant (CRUD) ----------
class KasQrisSubmerchant(models.Model):
    _name = "kas.qris.submerchant"
    _inherit = "kas.qris.api.mixin"
    _description = "QRIS Submerchant"
    _rec_name = "store_name"
    _order = "create_date desc"

    active = fields.Boolean(default=True)

    company_id = fields.Many2one("res.company", string="Company", required=True, ondelete="cascade", index=True)

    merchant_id = fields.Char("Merchant ID", index=True, readonly=True, help="ID merchant dari Winpay/QRIS (diisi saat register/sync).")
    detail_id = fields.Char("Detail ID", readonly=True, help="ID detail yang dipakai untuk request /detail/<id> jika API mengembalikan id berbeda.")

    owner_name = fields.Char("Owner Name")
    store_name = fields.Char("Store Name", required=True)
    address = fields.Char("Address")
    email = fields.Char("Email")
    phone_number = fields.Char("Phone Number")
    postcode = fields.Char("Postcode")
    longitude = fields.Char("Longitude")
    latitude = fields.Char("Latitude")
    ktp_number = fields.Char("KTP Number")
    npwp_number = fields.Char("NPWP Number")

    province_id = fields.Many2one("kas.qris.province", string="Province")
    city_id = fields.Many2one("kas.qris.city", string="City", domain="[('province_id', '=', province_id)]")
    merchant_type_id = fields.Many2one("kas.qris.merchant.type", string="Merchant Type")
    merchant_criteria_id = fields.Many2one("kas.qris.merchant.criteria", string="Merchant Criteria")
    merchant_category_id = fields.Many2one("kas.qris.merchant.category", string="Merchant Category (MCC)")

    account_number = fields.Char("Account Number")
    account_name = fields.Char("Account Name")
    bank_code_id = fields.Many2one("kas.qris.bank.code", string="Bank Code")
    bank_branch = fields.Char("Bank Branch")

    doc_ktp = fields.Binary("Doc KTP")
    doc_ktp_filename = fields.Char("Doc KTP Filename")
    doc_selfie = fields.Binary("Doc Selfie")
    doc_selfie_filename = fields.Char("Doc Selfie Filename")
    doc_location = fields.Binary("Doc Location")
    doc_location_filename = fields.Char("Doc Location Filename")
    doc_npwp = fields.Binary("Doc NPWP")
    doc_npwp_filename = fields.Char("Doc NPWP Filename")

    status = fields.Char("Status", readonly=True)
    private_key1 = fields.Char("Private Key 1", readonly=True)
    private_key2 = fields.Char("Private Key 2", readonly=True)
    merchant_key = fields.Char("Merchant Key", readonly=True)

    ext_doc_ktp = fields.Char("Doc KTP (URL / Info)", readonly=True)
    ext_doc_selfie = fields.Char("Doc Selfie (URL / Info)", readonly=True)
    ext_doc_location = fields.Char("Doc Location (URL / Info)", readonly=True)
    ext_doc_npwp = fields.Char("Doc NPWP (URL / Info)", readonly=True)
    last_qris_sync = fields.Datetime(
        string="Last QRIS Sync",
        readonly=True,
        copy=False
    )
    merchant_tier = fields.Selection(
    [
        ("lite", "LITE"),
        ("medium", "MEDIUM"),
        ("enterprise", "ENTERPRISE"),
    ],
    string="Merchant Tier",
    default="lite",
)
    _sql_constraints = [
        ("kas_qris_submerchant_uniq", "unique(merchant_id, company_id)", "Merchant ID must be unique per company!"),
    ]
    
    
    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        ctx = self.env.context

        # trigger auto fetch hanya sekali per request chain
        if ctx.get("auto_fetch_qris") and not ctx.get("auto_fetch_done"):
            self = self.with_context(auto_fetch_done=1)

            ICP = self.env["ir.config_parameter"].sudo()
            last_sync = ICP.get_param("kas_qris.last_sync")

            need_fetch = True
            if last_sync:
                last_sync_dt = fields.Datetime.from_string(last_sync)
                need_fetch = fields.Datetime.now() - last_sync_dt > timedelta(minutes=10)

            if need_fetch:
                # optional log biar keliatan kepanggil
                # _logger.warning("AUTO FETCH QRIS via web_search_read")
                self.action_fetch_qris_list()

        return super().web_search_read(
            domain=domain,
            specification=specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )


    @api.model
    def action_sync_submerchant_list_notify(self):
        n = self.env["kas.qris.sync.service"].sudo().sync_submerchant_list(
            per_page=20, page_start=1, max_pages=5
        )
        return self._notify(_("Sync Complete"), _("Berhasil sync %s submerchant.") % n)

    
    @api.model
    def action_fetch_qris_list(self):
        ICP = self.env["ir.config_parameter"].sudo()
        company_id = self.env.company.id

        # lanjut dari page terakhir
        last_page = int(ICP.get_param(f"qris.submerchant.last_page.{company_id}") or 0)
        page_start = last_page + 1

        self.env["kas.qris.sync.service"].sudo().with_context(
            current_company_id=company_id,
            qris_sync_running=True,
        ).sync_submerchant_list(
            per_page=50,
            page_start=page_start,
            max_pages=1,
            company_id=company_id,
        )
        return True


    def action_fetch_qris_list_notify(self):
        self.env['kas.qris.submerchant'].action_fetch_qris_list()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "QRIS", "message": "Fetch QRIS List berhasil.", "type": "success", "sticky": False},
        }
        
        
   

    def _auto_sync_chunk(self):
        _logger.warning("AUTO SYNC START. ctx=%s", self.env.context)

        ICP = self.env["ir.config_parameter"].sudo()

        min_interval_sec = 15 * 60
        last = ICP.get_param("qris.submerchant.last_sync_at")
        now = fields.Datetime.now()
        _logger.warning("AUTO SYNC last=%s now=%s", last, now)

        if last:
            last_dt = fields.Datetime.from_string(last)
            if (now - last_dt).total_seconds() < min_interval_sec:
                return

        last_page = int(ICP.get_param("qris.submerchant.last_sync_page") or 0)
        page_start = last_page + 1

        per_page = 20
        max_pages = 2

        self.env["kas.qris.sync.service"].sudo().with_context(qris_sync_running=True).sync_submerchant_list(
            per_page=per_page,
            page_start=page_start,
            max_pages=max_pages,
        )

        ICP.set_param("qris.submerchant.last_sync_at", fields.Datetime.to_string(now))
        ICP.set_param("qris.submerchant.last_sync_page", str(page_start + max_pages - 1))

    @api.model
    def search_read(self, domain=None, field_names=None, offset=0, limit=None, order=None):
        ctx = self.env.context
        if ctx.get("auto_fetch_qris") and not ctx.get("auto_fetch_done"):
            self = self.with_context(auto_fetch_done=1)

            ICP = self.env["ir.config_parameter"].sudo()
            last_sync = ICP.get_param("kas_qris.last_sync")

            need_fetch = True
            if last_sync:
                last_sync_dt = fields.Datetime.from_string(last_sync)  # ini sekarang aman
                need_fetch = fields.Datetime.now() - last_sync_dt > timedelta(minutes=10)

            if need_fetch:
                self.action_fetch_qris_list()

        return super().search_read(domain=domain, fields=field_names, offset=offset, limit=limit, order=order)


    def _notify(self, title, message, typ="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": typ,
                "sticky": False,
            },
    }


    # (bagian action_register_to_qris & action_sync_detail kamu biarin seperti sebelumnya)
    # --- aku nggak ubah untuk fokus ke fix list endpoint ---


    def action_register_to_qris(self):
        """Register (create) submerchant via API, then sync detail."""
        self.ensure_one()

        if self.merchant_id:
            raise UserError(_("Submerchant ini sudah memiliki Merchant ID."))

        # --- VALIDATION (biar jelas errornya dari Odoo dulu sebelum ke API) ---
        if not self.store_name:
            raise UserError(_("Store Name wajib diisi."))

        if not self.ktp_number:
            raise UserError(_("KTP Number wajib diisi sebelum register ke QRIS."))

        if not self.merchant_type_id:
            raise UserError(_("Merchant Type wajib diisi sebelum register ke QRIS."))

        # merchant_type harus integer (API requirement)
        # asumsi: merchant_type_id.code berisi angka (misal: "1", "2", dst)
        # kalau ternyata API pakai field lain, nanti kita mapping setelah cek master datanya.
        try:
            merchant_type_int = int(str(self.merchant_type_id.code or "").strip())
        except Exception:
            raise UserError(_("Merchant Type code harus integer. Sekarang: %s") % (self.merchant_type_id.code or "-"))

        base_url, api_token = self._get_qris_api_config()
        url = f"{base_url.rstrip('/')}/api/sub-merchant/create"

        # --- BUILD PAYLOAD ---
        data = {
            "owner_name": self.owner_name or (self.company_id.partner_id.name or ""),
            "store_name": self.store_name or (self.company_id.name or ""),
            "address": self.address or (self.company_id.partner_id.contact_address or ""),
            "email": self.email or (self.company_id.email or ""),
            "phone_number": self.phone_number or "",
            "postcode": self.postcode or "",
            "longitude": self.longitude or "",
            "latitude": self.latitude or "",
            "ktp_number": self.ktp_number,              # wajib, jangan ""
            "npwp_number": self.npwp_number or "",
            "province_id": (self.province_id.code or "") if self.province_id else "",
            "city_id": (self.city_id.code or "") if self.city_id else "",
            "merchant_type": merchant_type_int,         # wajib integer
            "merchant_criteria": (self.merchant_criteria_id.code or "") if self.merchant_criteria_id else "",
            "merchant_category": (self.merchant_category_id.code or "") if self.merchant_category_id else "",
            "account_number": self.account_number or "",
            "account_name": self.account_name or "",
            "bank_code": (self.bank_code_id.code or "") if self.bank_code_id else "",
            "bank_branch": self.bank_branch or "",
        }

        # --- CLEAN OPTIONAL EMPTY VALUES ---
        # Buang key yang nilainya kosong agar backend tidak menganggap invalid/required.
        # (ktp_number & merchant_type tetap dikirim karena wajib)
        keep_keys_even_if_empty = {"ktp_number", "merchant_type"}
        data = {
            k: v for k, v in data.items()
            if (k in keep_keys_even_if_empty) or (v not in (None, "", False))
        }

        # --- FILES ---
        files = {}
        ktp_file = self._binary_to_file_tuple(self.doc_ktp, self.doc_ktp_filename)
        selfie_file = self._binary_to_file_tuple(self.doc_selfie, self.doc_selfie_filename)
        loc_file = self._binary_to_file_tuple(self.doc_location, self.doc_location_filename)
        npwp_file = self._binary_to_file_tuple(self.doc_npwp, self.doc_npwp_filename)

        if ktp_file:
            files["doc_ktp"] = ktp_file
        if selfie_file:
            files["doc_selfie"] = selfie_file
        if loc_file:
            files["doc_location"] = loc_file
        if npwp_file:
            files["doc_npwp"] = npwp_file

        headers = {"Accept": "application/json", "X-API-TOKEN": api_token}

        # Log yang aman untuk debug (tidak print token)
        _logger.info(
            "Calling QRIS submerchant create API: %s payload_keys=%s merchant_type=%s ktp_filled=%s files=%s",
            url,
            list(data.keys()),
            data.get("merchant_type"),
            bool(data.get("ktp_number")),
            list(files.keys()),
        )

        try:
            response = requests.post(url, headers=headers, data=data, files=files, timeout=60)
        except Exception as e:
            _logger.exception("Error calling QRIS submerchant create API")
            raise UserError(_("Gagal menghubungi server QRIS: %s") % e)

        if response.status_code not in (200, 201):
            # biar kelihatan jelas response error dari API
            raise UserError(_("Request gagal. Status code: %s\nResponse: %s") % (response.status_code, response.text))

        try:
            res_json = response.json()
        except Exception:
            raise UserError(_("Response bukan JSON valid: %s") % response.text)

        data_outer = res_json.get("data") or {}
        resp_obj = data_outer.get("response") or {}

        rc = resp_obj.get("rc") or res_json.get("rc") or (data_outer.get("rc") if isinstance(data_outer, dict) else None)
        rd = resp_obj.get("rd") or res_json.get("message") or res_json.get("rd") or (data_outer.get("rd") if isinstance(data_outer, dict) else None)

        if rc not in ("00", "000", "SUCCESS", "Sukses", "SUCCESSFUL"):
            raise UserError(_("Pendaftaran submerchant gagal. [%s] %s") % (rc, rd))

        inner = resp_obj.get("data") if isinstance(resp_obj.get("data"), dict) else {}

        detail_id = inner.get("id") or data_outer.get("id")
        merchant_id = inner.get("id_merchant")
        private_key1 = inner.get("private_key1")
        private_key2 = inner.get("private_key2")
        merchant_key = inner.get("merchant_key")

        if not detail_id and not merchant_id:
            raise UserError(_("Response create tidak mengembalikan ID submerchant / merchant. Silakan cek format response API."))

        self.write({
            "detail_id": detail_id or False,
            "merchant_id": merchant_id or False,
            "private_key1": private_key1 or False,
            "private_key2": private_key2 or False,
            "merchant_key": merchant_key or False,
        })

        self.action_sync_detail()

        return self._notify(
            _("Submerchant Created"),
            _("Submerchant berhasil dibuat.\nMerchant ID: %s") % (self.merchant_id or ""),
        )


    def action_sync_detail(self):
        self.ensure_one()

        sub_id = self.detail_id
        if not sub_id:
            raise UserError(_("Belum ada Merchant ID/Detail ID untuk sync."))

        # ✅ FIX: pakai sub_id
        detail = self._qris_get_submerchant_detail(sub_id)

        status = detail.get("status") or ""
        vals = {
            "detail_id": str(detail.get("id") or "") or self.detail_id,
            "owner_name": detail.get("owner_name"),
            "store_name": detail.get("store_name"),
            "address": detail.get("address"),
            "postcode": detail.get("postcode"),
            "longitude": detail.get("longitude"),
            "latitude": detail.get("latitude"),
            "phone_number": detail.get("phone_number"),
            "email": detail.get("email"),
            "account_number": detail.get("account_number"),
            "account_name": detail.get("account_name"),
            "bank_branch": detail.get("bank_branch"),
            "status": status,
            "ext_doc_ktp": (detail.get("doc_ktp") or {}).get("url"),
            "ext_doc_npwp": (detail.get("doc_npwp") or {}).get("url"),
            "ext_doc_selfie": (detail.get("doc_selfie") or {}).get("url"),
            "ext_doc_location": (detail.get("doc_location") or {}).get("url"),
        }

        # ✅ credentials mapping
        resp = detail.get("response") or {}
        resp_data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        vals.update({
            "merchant_id": str(resp_data.get("id_merchant") or detail.get("id_merchant") or self.merchant_id or ""),
            "merchant_key": resp_data.get("merchant_key") or False,
            "private_key1": resp_data.get("private_key1") or False,
            "private_key2": resp_data.get("private_key2") or False,
        })

        # bank_code mapping
        bank_code = detail.get("bank_code")
        if bank_code:
            bank = self.env["kas.qris.bank.code"].sudo().search([("code", "=", str(bank_code))], limit=1)
            if bank:
                vals["bank_code_id"] = bank.id

        self.write(vals)

        # notif: keterangan + nmid kalau sukses
        rd = (resp.get("rd") or "").strip().lower()
        ket = resp.get("keterangan") or ""
        nmid = resp.get("nmid") or detail.get("nmid") or ""

        msg = _("Detail submerchant berhasil di-sync.\nStatus: %s") % (status or "")
        if rd == "sukses":
            msg = (ket or "Sukses") + (f"\nNMID: {nmid}" if nmid else "")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Complete"),
                "message": msg,
                "type": "success",
                "sticky": False,
            },
        }
