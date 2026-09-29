# -*- coding: utf-8 -*-
import base64
import logging
import requests
from odoo import api, fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class KasQrisProvince(models.Model):
    _name = "kas.qris.province"
    _description = "QRIS Province (Winpay)"

    name = fields.Char(required=True)
    code = fields.Char("External ID", required=True, index=True)

    _sql_constraints = [
        ("qris_province_code_uniq", "unique (code)", "Province code must be unique!"),
    ]


class KasQrisCity(models.Model):
    _name = "kas.qris.city"
    _description = "QRIS City (Winpay)"

    name = fields.Char(required=True)
    code = fields.Char("External ID", required=True, index=True)
    province_id = fields.Many2one("kas.qris.province", string="Province", required=True)

    _sql_constraints = [
        ("qris_city_code_uniq", "unique (code)", "City code must be unique!"),
    ]


class KasQrisMerchantType(models.Model):
    _name = "kas.qris.merchant.type"
    _description = "QRIS Merchant Type"

    name = fields.Char(required=True)
    code = fields.Char("Code", required=True, index=True)

    _sql_constraints = [
        ("qris_merchant_type_code_uniq", "unique (code)", "Merchant type code must be unique!"),
    ]


class KasQrisMerchantCriteria(models.Model):
    _name = "kas.qris.merchant.criteria"
    _description = "QRIS Merchant Criteria"

    name = fields.Char(required=True)
    code = fields.Char("Code", required=True, index=True)

    _sql_constraints = [
        ("qris_merchant_criteria_code_uniq", "unique (code)", "Merchant criteria code must be unique!"),
    ]


class KasQrisMerchantCategory(models.Model):
    _name = "kas.qris.merchant.category"
    _description = "QRIS Merchant Category (MCC)"

    name = fields.Char(required=True)
    code = fields.Char("MCC", required=True, index=True)

    _sql_constraints = [
        ("qris_merchant_category_code_uniq", "unique (code)", "Merchant category code must be unique!"),
    ]


class KasQrisBankCode(models.Model):
    _name = "kas.qris.bank.code"
    _description = "QRIS Bank Code"

    name = fields.Char(required=True)
    code = fields.Char("Bank Code", required=True, index=True)

    _sql_constraints = [
        ("qris_bank_code_uniq", "unique (code)", "Bank code must be unique!"),
    ]


class KasQrisSubmerchant(models.Model):
    _name = "kas.qris.submerchant"
    _description = "QRIS Submerchant"

    # merchant_id hanya diisi dari API (create/sync), bukan user
    merchant_id = fields.Char("Merchant ID", required=True, index=True, readonly=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        ondelete="cascade",
    )

    owner_name = fields.Char("Owner Name")
    store_name = fields.Char("Store Name")
    address = fields.Char("Address")
    email = fields.Char("Email")
    phone_number = fields.Char("Phone Number")
    postcode = fields.Char("Postcode")
    status = fields.Char("Status")

    account_number = fields.Char("Account Number")
    account_name = fields.Char("Account Name")
    bank_code = fields.Char("Bank Code")
    bank_branch = fields.Char("Bank Branch")

    doc_ktp = fields.Char("Doc KTP (URL / Info)")
    doc_selfie = fields.Char("Doc Selfie (URL / Info)")
    doc_location = fields.Char("Doc Location (URL / Info)")
    doc_npwp = fields.Char("Doc NPWP (URL / Info)")

    _sql_constraints = [
        ("kas_qris_submerchant_uniq", "unique(merchant_id, company_id)", "Merchant ID must be unique per company!"),
    ]


class ResCompany(models.Model):
    _inherit = "res.company"

    # ---------- Request fields ----------
    qris_owner_name = fields.Char("Owner Name")
    qris_store_name = fields.Char("Store Name")
    qris_address = fields.Char("Address")
    qris_email = fields.Char("Email")
    qris_phone_number = fields.Char("Phone Number")
    qris_postcode = fields.Char("Postcode")
    qris_longitude = fields.Char("Longitude")
    qris_latitude = fields.Char("Latitude")
    qris_ktp_number = fields.Char("KTP Number")
    qris_npwp_number = fields.Char("NPWP Number")

    # pakai master data (dropdown)
    qris_province_id = fields.Many2one(
        "kas.qris.province",
        string="Province",
    )
    qris_city_id = fields.Many2one(
        "kas.qris.city",
        string="City",
        domain="[('province_id', '=', qris_province_id)]",
    )
    qris_merchant_type_id = fields.Many2one(
        "kas.qris.merchant.type",
        string="Merchant Type",
    )
    qris_merchant_criteria_id = fields.Many2one(
        "kas.qris.merchant.criteria",
        string="Merchant Criteria",
    )
    qris_merchant_category_id = fields.Many2one(
        "kas.qris.merchant.category",
        string="Merchant Category (MCC)",
    )

    qris_account_number = fields.Char("Account Number")
    qris_account_name = fields.Char("Account Name")
    qris_bank_code_id = fields.Many2one(
        "kas.qris.bank.code",
        string="Bank Code",
    )
    qris_bank_branch = fields.Char("Bank Branch")

    # ---------- Dokumen ----------
    qris_doc_ktp = fields.Binary("Doc KTP")
    qris_doc_ktp_filename = fields.Char("Doc KTP Filename")
    qris_doc_selfie = fields.Binary("Doc Selfie")
    qris_doc_selfie_filename = fields.Char("Doc Selfie Filename")
    qris_doc_location = fields.Binary("Doc Location")
    qris_doc_location_filename = fields.Char("Doc Location Filename")
    qris_doc_npwp = fields.Binary("Doc NPWP")
    qris_doc_npwp_filename = fields.Char("Doc NPWP Filename")

    # ---------- Response fields ----------
    qris_submerchant_id = fields.Char("Submerchant ID", readonly=True)
    qris_private_key1 = fields.Char("Private Key 1", readonly=True)
    qris_private_key2 = fields.Char("Private Key 2", readonly=True)
    qris_merchant_key = fields.Char("Merchant Key", readonly=True)

    # 🔹 Status helper (buat alert di view)
    qris_submerchant_status = fields.Char(
        string="Submerchant Status",
        compute="_compute_qris_submerchant_status",
    )

    # ---------- Relation to list (internal only) ----------
    qris_submerchant_ids = fields.One2many(
        "kas.qris.submerchant",
        "company_id",
        string="QRIS Submerchants",
    )
    
    

    # ----------------- COMPUTE HELPERS -----------------
    def _compute_qris_submerchant_status(self):
        """Ambil status dari submerchant utama (kalau ada)."""
        for rec in self:
            sub = rec.qris_submerchant_ids[:1]
            rec.qris_submerchant_status = sub.status if sub else False
            
            
    def write(self, vals):
        protected_fields = {
            "qris_owner_name", "qris_store_name", "qris_address",
            "qris_email", "qris_phone_number", "qris_postcode",
            "qris_longitude", "qris_latitude",
            "qris_ktp_number", "qris_npwp_number",
            "qris_province_id", "qris_city_id",
            "qris_merchant_type_id", "qris_merchant_criteria_id",
            "qris_merchant_category_id",
            "qris_account_number", "qris_account_name",
            "qris_bank_code_id", "qris_bank_branch",
        }

        if not self.env.context.get("allow_qris_edit"):
            if protected_fields.intersection(vals.keys()):
                for rec in self:
                    if rec.qris_submerchant_id:
                        raise UserError(_(
                            "Data QRIS tidak boleh diubah karena submerchant sudah dibuat."
                        ))

        return super().write(vals)        

    # ----------------- Helpers -----------------
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

    def _binary_to_file_tuple(self, binary_field, filename):
        if not binary_field:
            return None
        data = base64.b64decode(binary_field)
        return (filename or "file.jpg", data, "image/jpeg")

    def _winpay_get(self, path, use_x_api_token=False, use_bearer=False):
        base_url, api_token = self._get_qris_api_config()

        url = f"{base_url.rstrip('/')}{path}"

        headers = {
            "Accept": "application/json",
        }
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

        _logger.info("Winpay response for %s: %s", path, res_json)

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

        raise UserError(
            _("Struktur data Winpay tidak seperti yang diharapkan: %s") % res_json
        )

    def _qris_get_submerchant_detail(self, sub_id):
        """Call /api/sub-merchant/detail/<id> dan balikin dict detail-nya."""
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

        _logger.info("QRIS submerchant detail raw response for id=%s: %s", sub_id, res_json)

        data = res_json.get("data")
        if isinstance(data, dict) and not isinstance(data.get("data"), (list, dict)):
            detail = data
        elif isinstance(data, dict) and isinstance(data.get("data"), dict):
            detail = data["data"]
        else:
            detail = res_json

        if not isinstance(detail, dict):
            raise UserError(
                _("Struktur response detail QRIS tidak sesuai harapan: %s") % res_json
            )
            
            

        _logger.info("QRIS submerchant detail parsed for id=%s: %s", sub_id, detail)
        return detail



    # ----------------- Actions: Create Submerchant -----------------
    def action_create_qris_submerchant(self):
        self.ensure_one()

        try:
            if self.qris_submerchant_id:
                raise UserError(_("Submerchant sudah dibuat untuk company ini."))

            base_url, api_token = self._get_qris_api_config()
            url = f"{base_url.rstrip('/')}/api/sub-merchant/create"

            data = {
                "owner_name": self.qris_owner_name or self.partner_id.name,
                "store_name": self.qris_store_name or self.name,
                "address": self.qris_address or self.partner_id.contact_address or "",
                "email": self.qris_email or self.email or "",
                "phone_number": self.qris_phone_number or "",
                "postcode": self.qris_postcode or "",
                "longitude": self.qris_longitude or "",
                "latitude": self.qris_latitude or "",
                "ktp_number": self.qris_ktp_number or "",
                "npwp_number": self.qris_npwp_number or "",
                "province_id": self.qris_province_id.code or "",
                "city_id": self.qris_city_id.code or "",
                "merchant_type": self.qris_merchant_type_id.code or "",
                "merchant_criteria": self.qris_merchant_criteria_id.code or "",
                "merchant_category": self.qris_merchant_category_id.code or "",
                "account_number": self.qris_account_number or "",
                "account_name": self.qris_account_name or "",
                "bank_code": self.qris_bank_code_id.code or "",
                "bank_branch": self.qris_bank_branch or "",
            }

            files = {}
            ktp_file = self._binary_to_file_tuple(
                self.qris_doc_ktp, self.qris_doc_ktp_filename
            )
            selfie_file = self._binary_to_file_tuple(
                self.qris_doc_selfie, self.qris_doc_selfie_filename
            )
            loc_file = self._binary_to_file_tuple(
                self.qris_doc_location, self.qris_doc_location_filename
            )
            npwp_file = self._binary_to_file_tuple(
                self.qris_doc_npwp, self.qris_doc_npwp_filename
            )

            if ktp_file:
                files["doc_ktp"] = ktp_file
            if selfie_file:
                files["doc_selfie"] = selfie_file
            if loc_file:
                files["doc_location"] = loc_file
            if npwp_file:
                files["doc_npwp"] = npwp_file

            headers = {
                "Accept": "application/json",
                "X-API-TOKEN": api_token,
            }

            _logger.info("Calling QRIS submerchant create API: %s data=%s", url, data)

            try:
                response = requests.post(
                    url, headers=headers, data=data, files=files, timeout=60
                )
            except Exception as e:
                _logger.exception("Error calling QRIS submerchant create API")
                raise UserError(_("Gagal menghubungi server QRIS: %s") % e)

            if response.status_code not in (200, 201):
                raise UserError(
                    _("Request gagal. Status code: %s\nResponse: %s")
                    % (response.status_code, response.text)
                )

            try:
                res_json = response.json()
            except Exception:
                raise UserError(_("Response bukan JSON valid: %s") % response.text)

            _logger.info("QRIS submerchant create response: %s", res_json)

            data_outer = res_json.get("data") or {}
            resp_obj = data_outer.get("response") or {}

            rc = (
                resp_obj.get("rc")
                or res_json.get("rc")
                or (data_outer.get("rc") if isinstance(data_outer, dict) else None)
            )
            rd = (
                resp_obj.get("rd")
                or res_json.get("message")
                or res_json.get("rd")
                or (data_outer.get("rd") if isinstance(data_outer, dict) else None)
            )

            if rc not in ("00", "000", "SUCCESS", "Sukses", "SUCCESSFUL"):
                # BE error -> tampil sebagai popup merah, bukan refresh page
                raise UserError(_("Pendaftaran submerchant gagal. [%s] %s") % (rc, rd))

            inner = resp_obj.get("data") if isinstance(resp_obj.get("data"), dict) else {}

            detail_id = (
                inner.get("id")
                or data_outer.get("id")
            )
            merchant_id = inner.get("id_merchant")
            private_key1 = inner.get("private_key1")
            private_key2 = inner.get("private_key2")
            merchant_key = inner.get("merchant_key")

            if not detail_id:
                raise UserError(
                    _(
                        "Response create tidak mengembalikan ID submerchant. "
                        "Silakan cek format response API."
                    )
                )
            # Step 2: get detail
            detail = self._qris_get_submerchant_detail(detail_id)

            
            status = detail.get("status") or ""

            # Simpan credential di company
            self.write(
                {
                    "qris_submerchant_id": merchant_id,
                    "qris_private_key1": private_key1,
                    "qris_private_key2": private_key2,
                    "qris_merchant_key": merchant_key,
                }
            )

            # Upsert ke kas.qris.submerchant (internal list)
            Sub = self.env["kas.qris.submerchant"].sudo()
            vals_sub = {
                "merchant_id": merchant_id,
                "company_id": self.id,
                "owner_name": detail.get("owner_name") or self.qris_owner_name or "",
                "store_name": detail.get("store_name") or self.qris_store_name or "",
                "address": detail.get("address") or self.qris_address or "",
                "email": detail.get("email") or self.qris_email or "",
                "phone_number": detail.get("phone_number") or self.qris_phone_number or "",
                "postcode": detail.get("postcode") or self.qris_postcode or "",
                "status": status,
                "account_number": detail.get("account_number") or self.qris_account_number or "",
                "account_name": detail.get("account_name") or self.qris_account_name or "",
                "bank_code": detail.get("bank_code") or (self.qris_bank_code_id.code or ""),
                "bank_branch": detail.get("bank_branch") or self.qris_bank_branch or "",
                "doc_ktp": detail.get("doc_ktp") or "",
                "doc_selfie": detail.get("doc_selfie") or "",
                "doc_location": detail.get("doc_location") or "",
                "doc_npwp": detail.get("doc_npwp") or "",
            }

            _logger.info("Upserting kas.qris.submerchant with vals: %s", vals_sub)

            existing = Sub.search(
                [("merchant_id", "=", merchant_id), ("company_id", "=", self.id)],
                limit=1,
            )
            if existing:
                existing.write(vals_sub)
            else:
                Sub.create(vals_sub)

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Submerchant Created"),
                    "message": _(
                        "Submerchant berhasil dibuat.\nMerchant ID: %s\nStatus: %s"
                    ) % (merchant_id or "", status or ""),
                    "type": "success",
                    "sticky": False,
                    "next": {
                        "type": "ir.actions.act_window_reload",
                    },
                },
            }

        except UserError:
            # UserError biarin lewat ke UI sebagai notifikasi merah
            raise
        except Exception as e:
            # Error tak terduga -> jangan bikin page refresh, convert ke UserError
            _logger.exception("Unexpected error while creating QRIS submerchant")
            raise UserError(
                _("Terjadi kesalahan tidak terduga saat membuat submerchant: %s") % e
            )

  
    # ----------------- Actions: Sync Master Data Winpay -----------------
    def action_sync_qris_provinces(self):
        self.ensure_one()
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

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Provinces Complete"),
                "message": _("Master Province berhasil di-sync dari Winpay."),
                "sticky": False,
            },
        }

    def action_sync_qris_cities(self):
        self.ensure_one()
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
                prov = Province.create(
                    {
                        "code": str(prov_id),
                        "name": (item.get("province") or {}).get("name", str(prov_id)),
                    }
                )

            rec = City.search([("code", "=", code)], limit=1)
            vals = {
                "code": code,
                "name": name,
                "province_id": prov.id,
            }
            if rec:
                rec.write(vals)
            else:
                City.create(vals)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Cities Complete"),
                "message": _("Master City berhasil di-sync dari Winpay."),
                "sticky": False,
            },
        }

    def action_sync_qris_merchant_type(self):
        self.ensure_one()
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

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Merchant Type Complete"),
                "message": _("Master Merchant Type berhasil di-sync dari Winpay."),
                "sticky": False,
            },
        }

    def action_sync_qris_merchant_criteria(self):
        self.ensure_one()
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

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Merchant Criteria Complete"),
                "message": _("Master Merchant Criteria berhasil di-sync dari Winpay."),
                "sticky": False,
            },
        }

    def action_sync_qris_merchant_category(self):
        self.ensure_one()
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

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Merchant Category Complete"),
                "message": _("Master Merchant Category berhasil di-sync dari Winpay."),
                "sticky": False,
            },
        }

    def action_sync_qris_bank_code(self):
        self.ensure_one()
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

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Bank Code Complete"),
                "message": _("Master Bank Code berhasil di-sync dari Winpay."),
                "sticky": False,
            },
        }

    
    @api.model
    def read(self, fields=None, load='_classic_read'):
        """Auto refresh QRIS submerchant detail setiap kali form dibuka."""
        records = super(ResCompany, self).read(fields=fields, load=load)

        for rec_data in records:
            company_id = rec_data.get("id")
            if not company_id:
                continue

            company = self.browse(company_id)

            # Hanya refresh kalau sudah punya submerchant
            if company.qris_submerchant_id:
                try:
                    detail = company._qris_get_submerchant_detail(company.qris_submerchant_id)
                except Exception as e:
                    _logger.error(
                        f"Auto-sync QRIS detail gagal untuk company {company_id}: {e}"
                    )
                    continue

                # Ambil status
                status = detail.get("status") or ""

                # Update field response
                company.sudo().with_context(allow_qris_edit=True).write({
                    "qris_submerchant_id": detail.get("id_merchant") or company.qris_submerchant_id,
                    "qris_private_key1": detail.get("private_key1") or company.qris_private_key1,
                    "qris_private_key2": detail.get("private_key2") or company.qris_private_key2,
                    "qris_merchant_key": detail.get("merchant_key") or company.qris_merchant_key,
                })

                # Update internal list (kas.qris.submerchant)
                Sub = self.env["kas.qris.submerchant"].sudo()
                existing = Sub.search(
                    [("merchant_id", "=", company.qris_submerchant_id), ("company_id", "=", company.id)],
                    limit=1,
                )

                vals_sub = {
                    "merchant_id": company.qris_submerchant_id,
                    "company_id": company.id,
                    "owner_name": detail.get("owner_name") or "",
                    "store_name": detail.get("store_name") or "",
                    "address": detail.get("address") or "",
                    "email": detail.get("email") or "",
                    "phone_number": detail.get("phone_number") or "",
                    "postcode": detail.get("postcode") or "",
                    "status": status,
                    "account_number": detail.get("account_number") or "",
                    "account_name": detail.get("account_name") or "",
                    "bank_code": detail.get("bank_code") or "",
                    "bank_branch": detail.get("bank_branch") or "",
                    "doc_ktp": detail.get("doc_ktp") or "",
                    "doc_selfie": detail.get("doc_selfie") or "",
                    "doc_location": detail.get("doc_location") or "",
                    "doc_npwp": detail.get("doc_npwp") or "",
                }

                if existing:
                    existing.write(vals_sub)
                else:
                    Sub.create(vals_sub)

        return records
