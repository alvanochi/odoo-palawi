# -*- coding: utf-8 -*-
import json
import logging
import base64

from datetime import datetime, date, timedelta
from odoo.osv import expression
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError, UserError, AccessDenied
from odoo import fields

_logger = logging.getLogger(__name__)
_logger.info(">>> REST API CONTROLLER LOADED <<<")

class RestApi(http.Controller):

    # -------------------------------------------
    # JSON Response helper
    # -------------------------------------------
    def _json_response(self, success, data=None, message=None, status=200):
        body = {"success": success}
        if message is not None:
            body["message"] = message
        if data is not None:
            body["data"] = data

        def json_default(o):
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            return str(o)

        return request.make_response(
            data=json.dumps(body, default=json_default),
            headers=[("Content-Type", "application/json")] + self._cors_headers(),
            status=status,
        )

    # -------------------------------------------
    def _load_json_body(self):
        raw = request.httprequest.data or b"{}"
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8").strip() or "{}"
        try:
            return json.loads(raw)
        except Exception:
            return None

    # -------------------------------------------
    def auth_api_key(self, api_key):
        if not api_key:
            return self._json_response(False, message="No API key provided", status=401)

        user = request.env["res.users"].sudo().search([("api_key", "=", api_key)], limit=1)
        if user:
            return True

        return self._json_response(False, message="Invalid API key", status=401)

    # ============================================================
    # SUPPORT BINARY BASE64 UPLOAD → PREPARE BEFORE CREATE/WRITE
    # ============================================================
    def _process_binary_fields(self, model_env, values):
        """Validate uploaded base64 for binary fields."""
        for fname, fdef in model_env._fields.items():
            if fdef.type == "binary" and fname in values:
                val = values[fname]
                if not val:
                    continue

                if not isinstance(val, str):
                    return (False, f"Field '{fname}' must be BASE64 string")

                try:
                    base64.b64decode(val)
                except Exception:
                    return (False, f"Invalid base64 for field '{fname}'")

        return (True, None)

    # ============================================================
    # MULTIPART HELPERS
    # ============================================================
    def _is_multipart(self):
        content_type = request.httprequest.headers.get("Content-Type", "")
        return content_type.startswith("multipart/form-data")

    def _load_multipart_values(self):
        """
        Ambil:
        - values[...] → dict values
        - file fields → werkzeug FileStorage (request.httprequest.files)
        """
        values = {}
        files = {}

        # form values
        for key, val in request.httprequest.form.items():
            if key.startswith("values[") and key.endswith("]"):
                field = key[7:-1]
                values[field] = val
            else:
                values[key] = val

        # files
        for key, file in request.httprequest.files.items():
            files[key] = file

        return values, files

    # -------------------------------------------
    def _normalize_datetime_values(self, model_env, values):
        """Normalize semua field datetime & date supaya Odoo bisa baca format ISO."""
        if not isinstance(values, dict):
            return

        for fname, fdef in model_env._fields.items():
            if fname not in values:
                continue

            val = values.get(fname)
            if not val or not isinstance(val, str):
                continue

            if fdef.type == "datetime":
                cleaned = val.replace("T", " ").split(".")[0].replace("Z", "")
                dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
                values[fname] = dt.strftime("%Y-%m-%d %H:%M:%S")

            elif fdef.type == "date":
                cleaned = val.split("T")[0]
                dt = datetime.strptime(cleaned, "%Y-%m-%d").date()
                values[fname] = dt.strftime("%Y-%m-%d")

    # ============================================================
    # CORE RESPONSE HANDLER
    # ============================================================
    def generate_response(self, method, model_id, rec_id, limit=None, offset=0, search=None, env=None, domain=None):
        """
        method: HTTP method (GET/POST/PUT/DELETE)
        model_id: ir.model ID
        """
        
        total = 0 
        records = []
        if env is None:
            env = request.env

        # ✅ Ambil konfigurasi connection.api berdasarkan model_id
        option = env["connection.api"].sudo().search([("model_id", "=", model_id)], limit=1)
        if not option:
            return self._json_response(False, message="No configuration found for this model in connection.api", status=400)

        model_name = option.model_id.model

        # ✅ jangan sudo supaya record rules + company context tetap berlaku
        model_env = env[model_name]

        # ------------------ Load body ------------------
        if method != "DELETE":
            if method == "POST" and self._is_multipart():
                data = {}
            else:
                data = self._load_json_body()
                if data is None:
                    return self._json_response(False, message="Invalid JSON data", status=400)
        else:
            data = {}

        # ------------------ Skip fields filter ------------------
        def _parse_skip_fields(params, data_obj):
            skip = set()

            raw = params.get("skip") if params else None
            if raw:
                skip |= {x.strip() for x in str(raw).split(",") if x.strip()}

            if isinstance(data_obj, dict):
                raw2 = data_obj.get("skip")
                if isinstance(raw2, list):
                    skip |= {str(x).strip() for x in raw2 if str(x).strip()}
                elif isinstance(raw2, str):
                    skip |= {x.strip() for x in raw2.split(",") if x.strip()}

            return skip

        params = request.httprequest.args

        DEFAULT_SKIP_FIELDS = {
            "groups_id", "log_ids", "device_ids", "company_ids", "resource_ids",
            "karma_tracking_ids", "crm_team_member_ids", "model_access", "employee_ids",
            "category_ids", "goal_ids", "employee_skill_ids", "tracking_value_ids",
        }
        SKIP_FIELDS = set(DEFAULT_SKIP_FIELDS) | _parse_skip_fields(params, data)

        # ------------------ Fields request ------------------
        fields_req = data.get("fields") if isinstance(data, dict) else []
        if not isinstance(fields_req, list):
            fields_req = []

        fields_original = [f for f in fields_req if isinstance(f, str)]

        fields_root = []
        for f in fields_original:
            root = f.split(".", 1)[0]
            if root and root not in fields_root:
                fields_root.append(root)

        fields_original = [
            f for f in fields_original
            if isinstance(f, str) and f.split(".", 1)[0] not in SKIP_FIELDS
        ]
        fields_root = [f for f in fields_root if f not in SKIP_FIELDS]

        # ------------------ Pagination/search ------------------
        # ✅ Untuk GET: paging idealnya dari query string.
        # ✅ Body tetap didukung (misal POST list), tapi query punya prioritas saat GET.
        if method == "GET":
            # querystring: ?limit=10&offset=20
            try:
                q_limit = params.get("limit")
                if q_limit not in (None, "", False):
                    limit = int(q_limit)
            except Exception:
                pass

            try:
                q_offset = params.get("offset")
                if q_offset not in (None, "", False):
                    offset = int(q_offset)
            except Exception:
                pass

            if search is None:
                q_search = params.get("search") or params.get("q")
                if isinstance(q_search, str):
                    search = q_search.strip() or None

        # fallback dari body jika belum ada
        if isinstance(data, dict):
            if limit is None and isinstance(data.get("limit"), int):
                limit = data.get("limit")
            if isinstance(data.get("offset"), int):
                offset = data.get("offset")
            if search is None:
                body_search = data.get("search") or data.get("q")
                if isinstance(body_search, str):
                    search = body_search.strip() or None

        # ✅ Paging policy untuk mobile
        DEFAULT_LIMIT = 10
        MAX_LIMIT = 100

        if limit is None or not isinstance(limit, int) or limit <= 0:
            limit = DEFAULT_LIMIT
        elif limit > MAX_LIMIT:
            limit = MAX_LIMIT

        offset = offset if isinstance(offset, int) and offset >= 0 else 0

        # ---------------------- Default fields GET if none requested ----------------------
        if method == "GET" and not fields_root:
            if hasattr(option, "get_field_ids") and option.get_field_ids:
                fields_root = [n for n in option.get_field_ids.mapped("name") if n not in SKIP_FIELDS]
                fields_original = list(fields_root)
            else:
                fields_root = []
                for fname, fdef in model_env._fields.items():
                    if fname in SKIP_FIELDS:
                        continue
                    if fdef.type != "binary":
                        fields_root.append(fname)
                    elif fname in ("photo", "icon"):
                        fields_root.append(fname)
                fields_original = list(fields_root)

        if "id" not in fields_root:
            fields_root.append("id")

        # ------------------------------------------------------------------
        # Helper expand relational fields (punya kamu tetap)
        # ------------------------------------------------------------------
        def _expand_record(model_rec, rec_dict, depth=0, max_depth=1, fields_original_ctx=None):
            # ... (ISI FUNCTION INI PERSIS PUNYA KAMU)
            # aku tidak ulangin di sini supaya tidak kepanjangan / risk typo.
            pass

        # ------------------------------------------------------------------
        # GET
        # ------------------------------------------------------------------
        if method == "GET":
            if not option.is_get:
                return self._json_response(False, message="GET method is not allowed for this model", status=405)

            base_domain = domain or []
            local_domain = []

            if rec_id:
                local_domain = [("id", "=", rec_id)]
            elif search:
                fields_def = model_env._fields
                has_name = "name" in fields_def
                has_display_name = "display_name" in fields_def

                if has_name and has_display_name:
                    local_domain = ["|", ("name", "ilike", search), ("display_name", "ilike", search)]
                elif has_name:
                    local_domain = [("name", "ilike", search)]
                elif has_display_name:
                    local_domain = [("display_name", "ilike", search)]

            # --- FILTER DARI CONFIG (param_ids) --- (punya kamu, biarin)
            if hasattr(option, "param_ids"):
                for param in option.param_ids:
                    if param.method and param.method.upper() != method:
                        continue
                    field_name = (
                        getattr(param, "field_name", False)
                        or getattr(param, "field_path", False)
                        or getattr(param, "odoo_field_path", False)
                    )

                    if not field_name:
                        odoo_field = getattr(param, "odoo_field_id", False)
                        related_field = getattr(param, "related_field_id", False)
                        if odoo_field and related_field:
                            field_name = f"{odoo_field.name}.{related_field.name}"
                        elif odoo_field:
                            field_name = odoo_field.name

                    if not param.name or not field_name:
                        continue

                    raw_val = params.get(param.name)
                    if raw_val is None and isinstance(data, dict):
                        raw_val = data.get(param.name)

                    if raw_val in (None, ""):
                        continue

                    vtype = (param.value_type or "char").lower()
                    try:
                        if vtype in ("int", "integer"):
                            val = int(raw_val)
                        elif vtype in ("float", "double", "number"):
                            val = float(raw_val)
                        elif vtype == "bool":
                            val = str(raw_val).lower() in ("1", "true", "t", "yes", "y")
                        else:
                            val = str(raw_val)
                            if val.isdigit():
                                val = int(val)
                    except Exception:
                        continue

                    op = param.operator or "="

                    if "." in field_name:
                        first, rest = field_name.split(".", 1)
                        field_def = model_env._fields.get(first)
                        if field_def and field_def.type == "one2many":
                            line_model = env[field_def.comodel_name]
                            line_recs = line_model.search([(rest, op, val)])
                            parent_ids = line_recs.mapped(field_def.inverse_name).ids
                            local_domain.append(("id", "in", parent_ids or [0]))
                            continue

                    local_domain.append((field_name, op, val))

            # --- FALLBACK AUTO FILTER (punya kamu, biarin) ---
            RESERVED = {
                "model", "Id", "id",
                "limit", "offset",
                "search", "q", "skip",
                "category", "category_id"
            }
            for k, v in request.httprequest.args.items():
                if k in RESERVED or v in (None, ""):
                    continue
                if k not in model_env._fields:
                    continue
                f = model_env._fields[k]

                if f.type == "many2one":
                    if str(v).isdigit():
                        local_domain.append((k, "=", int(v)))
                    else:
                        local_domain.append((k, "ilike", v))
                    continue

                if f.type == "boolean":
                    val_bool = str(v).lower() in ("1", "true", "t", "yes", "y")
                    local_domain.append((k, "=", val_bool))
                    continue

                if f.type == "integer":
                    if str(v).lstrip("-").isdigit():
                        local_domain.append((k, "=", int(v)))
                    continue

                if f.type == "float":
                    try:
                        local_domain.append((k, "=", float(v)))
                    except Exception:
                        pass
                    continue

                local_domain.append((k, "ilike", v))
                
                # =========================================================
                # CATEGORY FILTER (POS-LIKE): parent include children
                # supports:
                #  - ?category_id=47
                #  - ?category=Signature
                # =========================================================
                cat_id_q = request.httprequest.args.get("category_id")
                cat_name_q = request.httprequest.args.get("category")

                # pastikan fallback auto-filter tidak nyentuh category
                # (TAMBAHKAN INI DI RESERVED)
                # RESERVED = {..., "category", "category_id"}

                pos_cat_model = env["pos.category"].sudo()
                resolved_cat_id = None

                # 1) Prefer category_id
                if cat_id_q and str(cat_id_q).isdigit():
                    resolved_cat_id = int(cat_id_q)

                # 2) Resolve by name / display_name
                elif isinstance(cat_name_q, str) and cat_name_q.strip():
                    cat_name = cat_name_q.strip()

                    cat_rec = pos_cat_model.search([("display_name", "=", cat_name)], limit=1)
                    if not cat_rec:
                        cat_rec = pos_cat_model.search([("name", "=", cat_name)], limit=1)
                    if not cat_rec:
                        cat_rec = pos_cat_model.search([("display_name", "ilike", cat_name)], limit=1)
                    if not cat_rec:
                        cat_rec = pos_cat_model.search([("name", "ilike", cat_name)], limit=1)

                    if cat_rec:
                        resolved_cat_id = cat_rec.id

                # 3) POS-like behavior: parent include children
                if resolved_cat_id:
                    local_domain.append(("pos_categ_ids", "child_of", resolved_cat_id))
                
                category_q = request.httprequest.args.get("category")
                if isinstance(category_q, str) and category_q.strip():
                    local_domain.append(("pos_categ_ids.display_name", "ilike", category_q.strip()))

                availpos = params.get("availpos")
                if availpos is not None:
                    val_bool = str(availpos).lower() in ("1", "true", "t", "yes", "y")
                    if "available_in_pos" in model_env._fields:
                        local_domain.append(("available_in_pos", "=", val_bool))

                cat = params.get("category")
                if cat:
                    cat_name = str(cat).strip()
                    if cat_name:
                        # cari pos.category by name/display_name
                        PosCat = env["pos.category"].sudo()
                        cat_recs = PosCat.search(["|", ("name", "ilike", cat_name), ("display_name", "ilike", cat_name)])
                        if cat_recs:
                            # product.product m2m: pos_categ_ids
                            if "pos_categ_ids" in model_env._fields:
                                local_domain.append(("pos_categ_ids", "in", cat_recs.ids))
                                
            final_domain = expression.AND([base_domain, local_domain])

            # ✅ ORDER STABIL: kunci paging biar gak duplikat/ngacak
            order = "id asc"

            # 🔥 FORCE fields khusus pos.session (punya kamu, tapi indent dibenerin)
            if model_name == "pos.session":
                fields_root = ["access_token", "config_id", "name", "start_at", "stop_at", "id"]
                fields_original = list(fields_root)
                
            FORCE_FIELDS = {"company_id", "pos_categ_ids"}
            for f in FORCE_FIELDS:
                if f in model_env._fields and f not in SKIP_FIELDS and f not in fields_root:
                    fields_root.append(f)
                    if f not in fields_original:
                        fields_original.append(f)


            # 🔥 FORCE fields khusus pos.order (punya kamu, tapi indent dibenerin)
            records = model_env.search_read(
                domain=final_domain,
                fields=fields_root,
                offset=offset,
                limit=limit,
                order=order,
            )
            # ✅ Convert many2one default array -> object (minimal, FE-friendly)
            def _m2o_to_obj(val):
                if isinstance(val, (list, tuple)) and len(val) >= 2 and isinstance(val[0], int):
                    return {"id": val[0], "display_name": val[1]}
                return val

            def _m2m_ids_to_obj_list(model, ids):
                if not isinstance(ids, list) or not ids:
                    return []
                int_ids = [i for i in ids if isinstance(i, int)]
                if not int_ids:
                    return []
                recs = model.browse(int_ids).read(["id", "display_name"])
                by_id = {r["id"]: r for r in recs}
                return [by_id[i] for i in int_ids if i in by_id]

            # pos_categ_ids comodel biasanya 'pos.category' (optional)
            try:
                pos_cat_model = env["pos.category"].sudo()
            except Exception:
                pos_cat_model = None

            for rec in records:
                # company_id object
                if "company_id" in rec:
                    rec["company_id"] = _m2o_to_obj(rec.get("company_id"))

                # image_1920 -> URL
                if "image_1920" in rec:
                    rec["image_1920"] = self._binary_to_file_url(rec.get("image_1920"), model_name, rec.get("id"), "image_1920")

                # pos_categ_ids -> list object
                if "pos_categ_ids" in rec:
                    if pos_cat_model is not None:
                        rec["pos_categ_ids"] = _m2m_ids_to_obj_list(pos_cat_model, rec.get("pos_categ_ids"))
                    else:
                        ids = rec.get("pos_categ_ids") or []
                        rec["pos_categ_ids"] = [{"id": i, "display_name": str(i)} for i in ids if isinstance(i, int)]

                # expand relasi lain (kalau memang fungsi aslinya ada)
                try:
                    _expand_record(model_env, rec, depth=0, max_depth=2, fields_original_ctx=fields_original)
                except Exception:
                    _logger.exception("expand_record failed model=%s id=%s", model_name, rec.get("id"))

                total = model_env.search_count(final_domain)


            return self._json_response(True, data={
                "items": records,
                "limit": limit,
                "offset": offset,
                "count": total,   
                "page_count": len(records),  
                "search": search,
                "order": order,
            })
            

        # ------------------------------------------------------------------
        # PUT
        # ------------------------------------------------------------------
        if method == "PUT":
            if not option.is_put:
                return self._json_response(False, message="PUT method is not allowed for this model", status=405)

            if not rec_id:
                return self._json_response(False, message="No ID provided for update", status=400)

            resource = model_env.browse(int(rec_id))
            if not resource.exists():
                return self._json_response(False, message="Resource not found", status=404)

            try:
                values = data.get("values") if isinstance(data, dict) else None
                if not isinstance(values, dict):
                    return self._json_response(False, message="No 'values' dict provided for update", status=400)

                ok, err = self._process_binary_fields(model_env, values)
                if not ok:
                    return self._json_response(False, message=err, status=400)

                self._normalize_datetime_values(model_env, values)
                resource.write(values)

                read_fields = option.post_field_ids.mapped("name") if getattr(option, "post_field_ids", False) else ["id", "display_name"]
                if "id" not in read_fields:
                    read_fields.append("id")

                recs = model_env.search_read([("id", "=", resource.id)], read_fields)

                return self._json_response(True, message="Resource updated successfully", data=recs)

            except (ValidationError, UserError) as e:
                msg = getattr(e, "name", False) or str(e)
                return self._json_response(False, message=msg, status=400)
            except Exception as e:
                _logger.exception("Error in PUT /send_request")
                return self._json_response(False, message=str(e), status=500)

        # ------------------------------------------------------------------
        # POST (CREATE) - MULTIPART
        # ------------------------------------------------------------------
        if method == "POST" and self._is_multipart():
            if not getattr(option, "is_post", False):
                return self._json_response(False, message="POST method is not allowed for this model", status=405)

            try:
                values, files = self._load_multipart_values()

                # convert numeric string → int (simple)
                for k, v in list(values.items()):
                    if isinstance(v, str) and v.isdigit():
                        values[k] = int(v)

                self._normalize_datetime_values(model_env, values)

                # baca file SEKALI (biar bisa dipakai untuk binary field & attachment)
                file_payloads = {}
                for field_name, file in files.items():
                    content = file.read()
                    file_payloads[field_name] = (content, file)

                    # CASE A: langsung ke binary field (mis: photo)
                    if field_name in model_env._fields and model_env._fields[field_name].type == "binary":
                        values[field_name] = base64.b64encode(content).decode("utf-8")

                rec = model_env.create(values)

                # CASE B (optional & recommended): simpan sebagai attachment
                attachments = []
                for field_name, (content, file) in file_payloads.items():
                    attachment = request.env["ir.attachment"].sudo().create({
                        "name": file.filename,
                        "res_model": model_env._name,
                        "res_id": rec.id,
                        "datas": base64.b64encode(content).decode("utf-8"),
                        "mimetype": file.mimetype,
                    })
                    attachments.append(attachment.id)

                read_fields = option.post_field_ids.mapped("name") if getattr(option, "post_field_ids", False) else ["id", "display_name"]
                if "id" not in read_fields:
                    read_fields.append("id")

                recs = model_env.search_read([("id", "=", rec.id)], read_fields)

                return self._json_response(
                    True,
                    message="Resource created successfully (multipart)",
                    data={
                        "record": recs,
                        "attachment_ids": attachments,
                    },
                )

            except (ValidationError, UserError) as e:
                return self._json_response(False, message=str(e), status=400)
            except Exception as e:
                _logger.exception("Error in POST multipart")
                return self._json_response(False, message=str(e), status=500)

        # ------------------------------------------------------------------
        # POST (CREATE) - JSON
        # ------------------------------------------------------------------
        if method == "POST":
            if not getattr(option, "is_post", False):
                return self._json_response(False, message="POST method is not allowed for this model", status=405)

            try:
                values = data.get("values") if isinstance(data, dict) else None
                if not isinstance(values, dict):
                    return self._json_response(False, message="No 'values' dict provided for create", status=400)

                ok, err = self._process_binary_fields(model_env, values)
                if not ok:
                    return self._json_response(False, message=err, status=400)

                self._normalize_datetime_values(model_env, values)

                rec = model_env.create(values)

                read_fields = option.post_field_ids.mapped("name") if getattr(option, "post_field_ids", False) else ["id", "display_name"]
                if "id" not in read_fields:
                    read_fields.append("id")

                recs = model_env.search_read([("id", "=", rec.id)], read_fields)
                return self._json_response(True, message="Resource created successfully", data=recs)

            except (ValidationError, UserError) as e:
                msg = getattr(e, "name", False) or str(e)
                return self._json_response(False, message=msg, status=400)
            except Exception as e:
                _logger.exception("Error in POST /send_request")
                return self._json_response(False, message=str(e), status=500)

        # ------------------------------------------------------------------
        # DELETE
        # ------------------------------------------------------------------
        if method == "DELETE":
            if not option.is_delete:
                return self._json_response(False, message="DELETE method is not allowed for this model", status=405)

            if not rec_id:
                return self._json_response(False, message="No ID provided for delete", status=400)

            resource = model_env.browse(int(rec_id))
            if not resource.exists():
                return self._json_response(False, message="Resource not found", status=404)

            recs = model_env.search_read([("id", "=", resource.id)], ["id", "display_name"])
            resource.unlink()

            return self._json_response(True, message="Resource deleted successfully", data=recs)

        return self._json_response(False, message="Unsupported HTTP method", status=405)

    
    def _binary_to_file_url(self, val, model, rec_id, field_name):
        if val in (None, False, "", 0):
            return False
        if isinstance(val, str):
            s = val.strip()
            if s.startswith("/rest_api/file/") or s.startswith("http://") or s.startswith("https://"):
                return s
            return f"/rest_api/file/{model}/{rec_id}/{field_name}"
        return f"/rest_api/file/{model}/{rec_id}/{field_name}"


    # -------------------------------------------------------------------------
    # ROUTE UTAMA: /send_request
    # -------------------------------------------------------------------------
    @http.route(
        ["/send_request"],
        type="http",
        auth="none",
        methods=["GET", "POST", "PUT", "DELETE"],
        csrf=False,
    )
    def fetch_data(self, **kw):

        # Preflight CORS
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=self._cors_headers(), status=200)

        # 1) API KEY
        api_key = request.httprequest.headers.get("api-key")
        auth_api = self.auth_api_key(api_key)
        if auth_api is not True:
            return auth_api

        # (Optional) log param yang aman saja (hindari log seluruh request.params)
        try:
            _logger.info(
                "send_request model=%s limit=%s offset=%s search=%s",
                kw.get("model"),
                kw.get("limit"),
                kw.get("offset"),
                (kw.get("search") or kw.get("q") or "")[:50],  # potong biar aman
            )
        except Exception:
            pass

        # 2) Basic user auth
        username = request.httprequest.headers.get("login")
        password = request.httprequest.headers.get("password")

        if not username or not password:
            return self._json_response(False, message="Missing login or password", status=401)

        user = request.env["res.users"].sudo().search([("login", "=", username)], limit=1)
        if not user:
            return self._json_response(False, message="Invalid login or password", status=401)

        try:
            creds = {"type": "password", "password": password}
            user.with_user(user)._check_credentials(creds, {"interactive": False})
        except AccessDenied:
            return self._json_response(False, message="Invalid login or password", status=401)

        # 3) Validasi model
        model = kw.get("model")
        if not model:
            return self._json_response(False, message="Missing model parameter", status=400)

        model_id = request.env["ir.model"].sudo().search([("model", "=", model)], limit=1)
        if not model_id:
            return self._json_response(False, message="Invalid model", status=400)

        # 4) Param lain (paging safe)
        # Id safe parse
        rec_id_raw = kw.get("Id") or kw.get("id") or kw.get("ID")
        try:
            rec_id = int(rec_id_raw) if rec_id_raw not in (None, "", False) else 0
        except Exception:
            rec_id = 0

        # limit / offset parse + clamp
        limit_raw = kw.get("limit")
        offset_raw = kw.get("offset")
        search = kw.get("search") or kw.get("q")

        # default paging
        DEFAULT_LIMIT = 10
        MAX_LIMIT = 100

        try:
            limit = int(limit_raw) if limit_raw not in (None, "", False) else DEFAULT_LIMIT
        except Exception:
            limit = DEFAULT_LIMIT

        try:
            offset = int(offset_raw) if offset_raw not in (None, "", False) else 0
        except Exception:
            offset = 0

        # normalize paging values
        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        if offset < 0:
            offset = 0

        # normalize search
        search = search.strip() if isinstance(search, str) else None

        http_method = request.httprequest.method.upper()

        # company handling
        company_id = request.httprequest.headers.get("company-id")
        try:
            company_id = int(company_id) if company_id else user.company_id.id
        except Exception:
            company_id = user.company_id.id

        if company_id not in user.company_ids.ids:
            return self._json_response(False, message="Company not allowed", status=403)

        # env user w/ company context
        env_user = request.env(
            user=user.id,
            context=dict(
                request.env.context,
                **{
                    "allowed_company_ids": [company_id],
                    "force_company": company_id,
                }
            ),
        )

        # company domain (kalau model punya company_id field)
        company_domain = []
        if model and "company_id" in env_user[model]._fields:
            company_domain = ["|", ("company_id", "=", False), ("company_id", "=", company_id)]



        return self.generate_response(
            http_method,
            model_id.id,
            rec_id,
            limit=limit,
            offset=offset,
            search=search,
            env=env_user,
            domain=company_domain,
            # order=order,  # aktifkan kalau generate_response support
        )
        
    # ============================================================
    # BINARY FILE SERVE ROUTE
    # ============================================================
    @http.route(
        ["/rest_api/file/<string:model>/<int:record_id>/<string:field_name>"],
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def rest_api_file(self, model, record_id, field_name):
        Model = request.env[model].sudo()
        rec = Model.browse(record_id)
        if not rec.exists():
            return request.not_found()

        file_data = rec[field_name]
        if not file_data:
            return request.not_found()

        binary = base64.b64decode(file_data)
        headers = [
            ("Content-Type", "image/jpeg"),
            ('Content-Disposition', 'inline; filename="file.jpg"'),
        ]
        return request.make_response(binary, headers=headers)

    # ============================================================
    # /odoo_connect
    # ============================================================
    @http.route(
        ["/api/pos/odoo_connect"],
        type="http",
        auth="none",
        csrf=False,
        methods=["GET"],
    )
    def odoo_connect(self):
        
        username = request.httprequest.headers.get("login")
        password = request.httprequest.headers.get("password")
        db = request.params.get("db") or request.httprequest.headers.get("db")

        if not (username and password and db):
            return self._json_response(False, message="Missing db/login/password", status=400)

        try:
            request.session.db = db
            auth = request.session.authenticate(db, {"login": username, "password": password, "type": "password"})

            user = request.env["res.users"].browse(auth["uid"]).sudo()
            api_key = request.env.user.generate_api(username)

            employee_id = False
            employee_name = False
            if hasattr(user, "employee_id") and user.employee_id:
                employee_id = user.employee_id.id
                employee_name = user.employee_id.name
            else:
                Employee = request.env["hr.employee"].sudo()
                emp = Employee.search([("user_id", "=", user.id)], limit=1)
                if emp:
                    employee_id = emp.id
                    employee_name = emp.name

            get_roles = getattr(user, "_get_user_roles", None)
            roles = get_roles() if get_roles else []

            data = {
                "status": "auth successful",
                "user": user.name,
                "user_id": user.id,
                "company_id": user.company_id.id,
                "company_name": user.company_id.name,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "role": roles,
                "api-key": api_key,
            }

            return self._json_response(True, data=data)

        except Exception:
            _logger.exception("Error in /odoo_connect")
            return self._json_response(False, message="Wrong login credentials", status=401)

    
    def _cors_headers(self):
        origin = request.httprequest.headers.get("Origin") or "*"

        # Kalau kamu pakai cookies/sessions: jangan '*', tapi echo origin + Allow-Credentials true
        return [
            ("Access-Control-Allow-Origin", origin),
            ("Vary", "Origin"),
            ("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, Authorization, api-key, login, password, company-id"),
            ("Access-Control-Max-Age", "86400"),
        ]
