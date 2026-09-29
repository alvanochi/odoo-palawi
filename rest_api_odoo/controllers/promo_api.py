# -*- coding: utf-8 -*-
"""Endpoint promo: daftar program, evaluasi keranjang, dan validasi kupon.

Ketiganya dipindahkan ke modul ini supaya aplikasi POS tidak perlu memanggil
dua modul untuk satu alur promo. Bentuk request dan response-nya dipertahankan
persis seperti versi sebelumnya, jadi klien yang sudah memakainya tidak perlu
diubah sama sekali.

Perhitungan yang mengikat ada di sini, bukan di klien: ambang qty/nominal,
jumlah klaim Buy X Get Y, batas maksimum diskon, dan sasaran diskon semuanya
dievaluasi memakai aturan Odoo sendiri, pada harga yang benar-benar ditagih
(pricelist + pajak). Klien yang menghitung promonya sendiri akan cepat berbeda
dari yang dilakukan kasir POS.

Modul loyalty tidak didaftarkan sebagai dependency -- lihat catatan di
models/product_product.py. Tanpa modul itu, endpoint di sini menjawab 400
dengan pesan yang jelas, bukan menjatuhkan seluruh API POS.
"""
import json
import logging

from odoo import fields, http
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.promotion_engine import (
    build_cart_data, compute_claim_count, describe_reward, match_rule,
    resolve_products, serialize_program, serialize_reward,
)

_logger = logging.getLogger(__name__)


class PromoApi(http.Controller):

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _cors_headers(self):
        return [
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, login, password, api_key, api-key, db"),
        ]

    def _resp(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, default=str),
            headers=self._cors_headers(),
            status=status,
        )

    def _ok(self, data, **extra):
        payload = {"success": True, "data": data}
        payload.update(extra)
        return self._resp(payload, 200)

    def _err(self, message, status=400):
        return self._resp(
            {"success": False, "message": message, "status": status}, status)

    def _authenticate(self):
        """-> None bila boleh, atau response penolakan.

        Dua kunci diterima: api_key milik user (sama seperti /send_request) dan
        kunci statis api_key_palawi (yang dipakai endpoint promo sebelumnya).
        Keduanya sudah memberi akses ke data yang sama di endpoint lain, dan
        menerima keduanya membuat klien lama tidak perlu diubah.
        """
        api_key = request.httprequest.headers.get("api-key") \
            or request.httprequest.headers.get("api_key")
        if not api_key:
            return self._err("No API key provided", 401)

        params = request.env["ir.config_parameter"].sudo()
        if api_key == params.get_param("api_key_palawi"):
            return None

        user = request.env["res.users"].sudo().search(
            [("api_key", "=", api_key)], limit=1)
        if user:
            return None

        return self._err("Invalid API key", 401)

    def _body(self):
        raw = request.httprequest.data or b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}"), None
        except Exception:
            return None, self._err("Invalid JSON body", 400)

    @staticmethod
    def _int(value, name, required=True, default=None):
        """-> (int|None, pesan error|None)"""
        if value in (None, "", False):
            if required:
                return None, "Missing required parameter '%s'" % name
            return default, None
        try:
            return int(value), None
        except (TypeError, ValueError):
            return None, "Invalid '%s', must be an integer" % name

    @staticmethod
    def _csv(value, default=None):
        if not value or str(value).strip().lower() == "all":
            return default
        return [part.strip() for part in str(value).split(",") if part.strip()]

    def _loyalty_ready(self):
        return "loyalty.program" in request.env and "loyalty.card" in request.env

    def _resolve_config(self, pos_config_id):
        config = request.env["pos.config"].sudo().browse(pos_config_id)
        if not config.exists():
            raise UserError("POS Config ID %s does not exist" % pos_config_id)
        return config

    def _resolve_pricelist(self, pricelist_id, config):
        pricelist = request.env["product.pricelist"].sudo().browse(pricelist_id)
        if not pricelist.exists():
            raise UserError("Pricelist ID %s does not exist" % pricelist_id)
        if config.use_pricelist:
            allowed_ids = config.available_pricelist_ids.ids
            if allowed_ids and pricelist.id not in allowed_ids:
                raise UserError(
                    "Pricelist '%s' is not available on POS '%s'"
                    % (pricelist.name, config.name))
        return pricelist

    def _pricelist_dict(self, pricelist, is_default=False):
        return {
            'id': pricelist.id,
            'name': pricelist.name,
            'is_default': is_default,
            'company_id': pricelist.company_id.id if pricelist.company_id else False,
            'currency': {
                'id': pricelist.currency_id.id,
                'name': pricelist.currency_id.name,
                'symbol': pricelist.currency_id.symbol,
            } if pricelist.currency_id else None,
            'item_count': len(pricelist.item_ids),
        }

    def _browse_pricelist(self, pricelist_id):
        pricelist = request.env["product.pricelist"].sudo().browse(pricelist_id)
        if not pricelist.exists():
            raise UserError("Pricelist ID %s does not exist" % pricelist_id)
        return pricelist

    def _find_partner(self, partner_id):
        if not partner_id:
            return None
        partner = request.env["res.partner"].sudo().browse(partner_id)
        return partner if partner.exists() else None

    def _programs_for_config(self, config, program_types=None):
        """Program yang tersedia pada satu POS, langsung dari mesin Odoo.

        pos.config._get_program_ids() (addons/pos_loyalty) sudah menerapkan
        pos_ok, batasan pos_config_ids, rentang tanggal, batasan pricelist dan
        max_usage, jadi tidak satu pun aturan itu ditulis ulang di sini.
        """
        programs = config.sudo()._get_program_ids().filtered('active')
        if program_types:
            programs = programs.filtered(lambda p: p.program_type in program_types)
        return programs

    def _validate_coupon_code(self, config, code, partner_id=False, pricelist_id=False):
        """Diserahkan ke pos.config.use_coupon_code bawaan Odoo.

        Di sanalah kedaluwarsa, kepemilikan partner, poin, batasan pricelist
        dan validitas program diperiksa -- dengan hasil yang sama seperti
        kasir POS.
        """
        result = config.sudo().use_coupon_code(
            code,
            fields.Datetime.now().isoformat(),
            partner_id or False,
            pricelist_id or False,
        )

        if not result.get('successful'):
            return {
                'valid': False,
                'code': code,
                'message': result.get('payload', {}).get('error_message', 'Invalid coupon'),
            }

        payload = result.get('payload', {})
        coupon = request.env['loyalty.card'].sudo().browse(payload.get('coupon_id'))
        program = request.env['loyalty.program'].sudo().browse(payload.get('program_id'))
        points = payload.get('points', 0.0)

        return {
            'valid': True,
            'code': code,
            'program_id': program.id,
            'program_name': program.name,
            'program_type': program.program_type,
            'coupon_id': coupon.id,
            'coupon_partner_id': payload.get('coupon_partner_id'),
            'points': points,
            'expiration_date': coupon.expiration_date.isoformat() if coupon.expiration_date else False,
            'has_source_order': payload.get('has_source_order'),
            # Hanya reward yang poinnya benar-benar mencukupi
            'claimable_reward_ids': [
                reward.id for reward in program.reward_ids if reward.required_points <= points
            ],
        }

    # ------------------------------------------------------------------
    # 1. Daftar program aktif
    # ------------------------------------------------------------------

    @http.route("/api/pos/promotions", type="http", auth="none",
                methods=["GET", "OPTIONS"], csrf=False)
    def get_promotions(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True}, 200)

        denied = self._authenticate()
        if denied:
            return denied
        if not self._loyalty_ready():
            return self._err("Module 'loyalty' is not installed", 400)

        pos_config_id, error = self._int(kw.get("pos_config_id"), "pos_config_id")
        if error:
            return self._err(error, 400)

        program_types = self._csv(kw.get("program_type"))

        try:
            config = self._resolve_config(pos_config_id)
            programs = self._programs_for_config(config, program_types)
            return self._ok([serialize_program(program) for program in programs])
        except (UserError, AccessError, ValidationError) as e:
            return self._err(str(e), 400)
        except Exception as e:
            _logger.exception("PROMO LIST FAILED pos_config_id=%s", pos_config_id)
            return self._err(str(e), 500)

    # ------------------------------------------------------------------
    # 2. Evaluasi keranjang
    # ------------------------------------------------------------------

    @http.route("/api/pos/promotions/match", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    def match_promotions(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True}, 200)

        denied = self._authenticate()
        if denied:
            return denied
        if not self._loyalty_ready():
            return self._err("Module 'loyalty' is not installed", 400)

        body, error = self._body()
        if error:
            return error

        pos_config_id, message = self._int(body.get("pos_config_id"), "pos_config_id")
        if message:
            return self._err(message, 400)
        pricelist_id, message = self._int(
            body.get("pricelist_id"), "pricelist_id", required=False)
        if message:
            return self._err(message, 400)
        partner_id, message = self._int(
            body.get("partner_id"), "partner_id", required=False)
        if message:
            return self._err(message, 400)

        cart_items = body.get("cart") or body.get("products") or []
        if not isinstance(cart_items, list):
            return self._err("'cart' must be a list of items", 400)

        coupon_codes = list(body.get("coupon_codes") or [])
        if body.get("coupon_code"):
            coupon_codes.append(body.get("coupon_code"))

        try:
            config = self._resolve_config(pos_config_id)
            company = config.company_id

            product_ids = []
            for item in cart_items:
                pid = item.get('product_id')
                if not pid:
                    continue
                try:
                    product_ids.append(int(pid))
                except (TypeError, ValueError):
                    return self._err("product_id must be integers", 400)

            product_map = resolve_products(request.env, product_ids, company)
            partner = self._find_partner(partner_id)

            # Harga dasar diambil dari pricelist bila disebut, supaya ambang
            # promo dievaluasi pada harga yang benar-benar ditagih.
            price_resolver = None
            if pricelist_id:
                pricelist = self._resolve_pricelist(pricelist_id, config)

                def price_resolver(product, qty, _pl=pricelist, _partner=partner):
                    return _pl._get_product_price(product, qty, _partner or False)

            # Ambang dan diskon berjalan pada jumlah termasuk pajak, sama
            # dengan yang ditagih dan yang ditampilkan POS. price_resolver
            # sengaja tetap tanpa pajak: pembuatan order juga memberi harga
            # produk reward seperti itu, jadi keduanya sepakat soal nilai
            # sebuah produk gratis.
            fiscal_position = config.default_fiscal_position_id

            def subtotal_resolver(product, qty, price, _company=company,
                                  _fp=fiscal_position, _partner=partner):
                taxes = product.taxes_id.filtered_domain(
                    request.env['account.tax']._check_company_domain(_company))
                if not taxes:
                    return qty * price
                mapped_taxes = _fp.map_tax(taxes) if _fp else taxes
                return mapped_taxes.compute_all(
                    price, _company.currency_id, qty,
                    product=product, partner=_partner or False,
                )['total_included']

            cart_data = build_cart_data(
                cart_items, product_map, price_resolver, subtotal_resolver)

            # Kode kupon divalidasi lebih dulu: program yang dipicu kode baru
            # ikut bermain ketika kodenya memang disertakan.
            valid_coupons = {}
            invalid_codes = []
            for code in coupon_codes:
                result = self._validate_coupon_code(
                    config, code, partner_id, pricelist_id)
                if result.get('valid'):
                    valid_coupons[result['program_id']] = result
                else:
                    invalid_codes.append({'code': code, 'message': result.get('message')})

            programs = self._programs_for_config(config)

            matched_programs = []
            claimable_rewards = []
            for program in programs:
                coupon = valid_coupons.get(program.id)

                # Program berkode diam sampai kodenya diberikan
                if program.trigger == 'with_code' and not coupon:
                    continue

                matched_rules = []
                claim_count = 0
                for rule in program.rule_ids:
                    rule_matches = match_rule(rule, cart_data)
                    matched_rules.extend(rule_matches)
                    for match in rule_matches:
                        claim_count = max(
                            claim_count, compute_claim_count(rule, match['matched_qty']))

                if not matched_rules and program.rule_ids and not coupon:
                    continue

                matched_programs.append(serialize_program(program, matched_rules))

                points = coupon['points'] if coupon else 0.0
                coupon_id = coupon['coupon_id'] if coupon else None
                for reward in program.reward_ids:
                    if coupon and reward.required_points > points:
                        continue
                    # claim_count hanya menggandakan produk gratis. Diskon
                    # order-level diklaim sekali, berapa pun unit yang lolos.
                    reward_claims = (claim_count or 1) if reward.reward_type == 'product' else 1
                    claimable_rewards.append(describe_reward(
                        reward, cart_data,
                        claim_count=reward_claims,
                        coupon_id=coupon_id,
                        points=points,
                        price_resolver=price_resolver,
                    ))

            return self._ok({
                "matched_programs": matched_programs,
                "claimable_rewards": claimable_rewards,
                "invalid_codes": invalid_codes,
                "cart_subtotal": sum(item['subtotal'] for item in cart_data),
            })
        except (UserError, AccessError, ValidationError) as e:
            return self._err(str(e), 400)
        except Exception as e:
            _logger.exception("PROMO MATCH FAILED pos_config_id=%s", pos_config_id)
            return self._err(str(e), 500)

    # ------------------------------------------------------------------
    # 3. Validasi kupon
    # ------------------------------------------------------------------

    @http.route("/api/pos/coupons/validate", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    def validate_coupon(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True}, 200)

        denied = self._authenticate()
        if denied:
            return denied
        if not self._loyalty_ready():
            return self._err("Module 'loyalty' is not installed", 400)

        body, error = self._body()
        if error:
            return error

        pos_config_id, message = self._int(body.get("pos_config_id"), "pos_config_id")
        if message:
            return self._err(message, 400)
        partner_id, message = self._int(
            body.get("partner_id"), "partner_id", required=False)
        if message:
            return self._err(message, 400)
        pricelist_id, message = self._int(
            body.get("pricelist_id"), "pricelist_id", required=False)
        if message:
            return self._err(message, 400)

        code = (body.get("code") or body.get("coupon_code") or "").strip()
        if not code:
            return self._err("Missing required parameter 'code'", 400)

        try:
            config = self._resolve_config(pos_config_id)
            return self._ok(self._validate_coupon_code(
                config, code, partner_id, pricelist_id))
        except (UserError, AccessError, ValidationError) as e:
            return self._err(str(e), 400)
        except Exception as e:
            _logger.exception("COUPON VALIDATE FAILED code=%s", code)
            return self._err(str(e), 500)

    # ------------------------------------------------------------------
    # 5. Daftar kupon milik pelanggan
    # ------------------------------------------------------------------

    @http.route("/api/pos/coupons", type="http", auth="none",
                methods=["GET", "OPTIONS"], csrf=False)
    def list_coupons(self, **kw):
        """Kupon yang dimiliki satu pelanggan pada satu POS.

        partner_id WAJIB, dan hanya kupon milik pelanggan itu yang dikembalikan.
        Kupon tanpa pemilik adalah kupon bawa-tunjuk: siapa pun yang tahu
        kodenya bisa memakainya, jadi mendaftarkannya lewat API sama saja
        dengan membagikan seluruh kode yang masih berlaku.
        """
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True}, 200)

        denied = self._authenticate()
        if denied:
            return denied
        if not self._loyalty_ready():
            return self._err("Module 'loyalty' is not installed", 400)

        pos_config_id, message = self._int(kw.get("pos_config_id"), "pos_config_id")
        if message:
            return self._err(message, 400)
        partner_id, message = self._int(kw.get("partner_id"), "partner_id")
        if message:
            return self._err(message, 400)

        program_types = self._csv(kw.get("program_type"))

        try:
            config = self._resolve_config(pos_config_id)
            partner = self._find_partner(partner_id)
            if not partner:
                return self._err("Partner ID %s does not exist" % partner_id, 404)

            programs = self._programs_for_config(config, program_types)
            if not programs:
                return self._ok([])

            cards = request.env['loyalty.card'].sudo().search([
                ('program_id', 'in', programs.ids),
                ('partner_id', '=', partner.id),
            ], order='id desc')

            today = fields.Date.context_today(request.env['loyalty.card'].sudo())
            data = []
            for card in cards:
                program = card.program_id
                expired = bool(card.expiration_date and card.expiration_date < today)
                # Reward yang poinnya benar-benar mencukupi. Kupon dengan poin
                # kurang tetap ditampilkan supaya pelanggan tahu ia punya, dan
                # berapa lagi yang kurang.
                claimable = program.reward_ids.filtered(
                    lambda reward: reward.required_points <= card.points)
                data.append({
                    'coupon_id': card.id,
                    'code': card.code,
                    'points': card.points,
                    'points_display': card.points_display,
                    'point_name': card.point_name or '',
                    'expiration_date': card.expiration_date.isoformat() if card.expiration_date else None,
                    'is_expired': expired,
                    'usable': bool(claimable) and not expired,
                    'program_id': program.id,
                    'program_name': program.name,
                    'program_type': program.program_type or '',
                    'claimable_reward_ids': claimable.ids,
                    'rewards': [serialize_reward(reward) for reward in program.reward_ids],
                })

            return self._ok(data)
        except (UserError, AccessError, ValidationError) as e:
            return self._err(str(e), 400)
        except Exception as e:
            _logger.exception("COUPON LIST FAILED partner_id=%s", partner_id)
            return self._err(str(e), 500)

    # ------------------------------------------------------------------
    # 4. Pricelist
    # ------------------------------------------------------------------

    @http.route("/api/pos/pricelists", type="http", auth="none",
                methods=["GET", "OPTIONS"], csrf=False)
    def get_pricelists(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True}, 200)

        denied = self._authenticate()
        if denied:
            return denied

        pos_config_id, message = self._int(
            kw.get("pos_config_id"), "pos_config_id", required=False)
        if message:
            return self._err(message, 400)
        company_id, message = self._int(
            kw.get("company_id"), "company_id", required=False)
        if message:
            return self._err(message, 400)

        if not pos_config_id and not company_id:
            return self._err(
                "Missing required parameter 'pos_config_id' (or 'company_id')", 400)

        try:
            if pos_config_id:
                # "Harga per lokasi" dipetakan ke pricelist POS: memilih POS
                # berarti memilih tokonya, dan pricelist toko itu yang berlaku.
                config = self._resolve_config(pos_config_id)
                default = config.pricelist_id
                pricelists = config.available_pricelist_ids if config.use_pricelist else default
                data = [
                    self._pricelist_dict(pricelist, is_default=(pricelist.id == default.id))
                    for pricelist in pricelists
                ]
            else:
                company = request.env['res.company'].sudo().browse(company_id)
                if not company.exists():
                    return self._err("Company ID %s does not exist" % company_id, 400)
                pricelists = request.env['product.pricelist'].sudo().with_company(
                    company_id).search([
                        '|', ('company_id', '=', False), ('company_id', '=', company_id),
                    ], order='name asc')
                data = [self._pricelist_dict(pricelist) for pricelist in pricelists]
            return self._ok(data)
        except (UserError, AccessError, ValidationError) as e:
            return self._err(str(e), 400)
        except Exception as e:
            _logger.exception("PRICELIST LIST FAILED")
            return self._err(str(e), 500)

    @http.route("/api/pos/pricelists/prices", type="http", auth="none",
                methods=["POST", "OPTIONS"], csrf=False)
    def get_pricelist_prices(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._resp({"success": True}, 200)

        denied = self._authenticate()
        if denied:
            return denied

        body, error = self._body()
        if error:
            return error

        pricelist_id, message = self._int(body.get("pricelist_id"), "pricelist_id")
        if message:
            return self._err(message, 400)
        partner_id, message = self._int(
            body.get("partner_id"), "partner_id", required=False)
        if message:
            return self._err(message, 400)
        pos_config_id, message = self._int(
            body.get("pos_config_id"), "pos_config_id", required=False)
        if message:
            return self._err(message, 400)

        items = body.get("items") or []
        if not isinstance(items, list) or not items:
            return self._err("'items' must be a non-empty list", 400)

        try:
            config = self._resolve_config(pos_config_id) if pos_config_id else None
            pricelist = self._resolve_pricelist(pricelist_id, config) if config \
                else self._browse_pricelist(pricelist_id)

            company_id = pricelist.company_id.id or (
                config.company_id.id if config else request.env.company.id)
            product_model = request.env['product.product'].sudo().with_company(company_id)
            template_model = request.env['product.template'].sudo().with_company(company_id)
            partner = self._find_partner(partner_id)

            results = []
            for item in items:
                raw_id = item.get('product_id')
                if not raw_id:
                    continue
                try:
                    raw_id = int(raw_id)
                except (TypeError, ValueError):
                    return self._err("Invalid 'product_id' %s" % item.get('product_id'), 400)

                try:
                    qty = float(item.get('qty', 1.0))
                except (TypeError, ValueError):
                    qty = 1.0

                product = product_model.browse(raw_id)
                if not product.exists():
                    template = template_model.browse(raw_id)
                    if not template.exists():
                        return self._err("Product ID %s does not exist" % raw_id, 404)
                    product = template.product_variant_id
                    if not product:
                        return self._err("Product ID %s has no variant" % raw_id, 400)

                # Perhitungan inti: aturan pricelist tidak pernah ditulis ulang di sini.
                price = pricelist._get_product_price(product, qty, partner or False)
                list_price = product.lst_price or product.list_price

                results.append({
                    'product_id': raw_id,
                    'variant_id': product.id,
                    'name': product.display_name,
                    'qty': qty,
                    'list_price': list_price,
                    'price': price,
                    'discount_amount': max(list_price - price, 0.0),
                    'currency': {
                        'id': pricelist.currency_id.id,
                        'name': pricelist.currency_id.name,
                        'symbol': pricelist.currency_id.symbol,
                    } if pricelist.currency_id else None,
                })

            return self._ok({
                'pricelist': self._pricelist_dict(pricelist),
                'items': results,
            })
        except (UserError, AccessError, ValidationError) as e:
            return self._err(str(e), 400)
        except Exception as e:
            _logger.exception("PRICELIST PRICES FAILED pricelist_id=%s", pricelist_id)
            return self._err(str(e), 500)
