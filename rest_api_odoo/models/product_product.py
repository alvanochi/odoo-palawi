# -*- coding: utf-8 -*-
"""Penanda promo pada produk, dihitung dari program loyalty bawaan Odoo.

Katalog aplikasi POS dibaca lewat /send_request?model=product.product, yang
hanya melakukan search_read biasa. Karena itu penanda promo dibuat sebagai
FIELD pada product.product, bukan endpoint baru: tidak ada kontrak API baru
yang harus dijaga, dan field mana yang ikut terkirim sepenuhnya ditentukan
konfigurasi GET Fields di connection.api -- tidak ada satu pun field yang
dipaksa masuk ke response.

Sumber kebenarannya tetap loyalty.rule / loyalty.reward milik Odoo; tidak ada
aturan promo yang ditulis ulang di sini. Pencocokan produk memakai
_get_valid_product_domain() dan _get_discount_product_domain() yang sama persis
dengan yang dipakai POS, jadi badge di katalog tidak akan pernah menjanjikan
promo yang ditolak mesin loyalty saat pembayaran.

Modul loyalty SENGAJA tidak didaftarkan sebagai dependency. rest_api_odoo
melayani seluruh aplikasi POS -- bill, order, pembayaran, session -- dan
menambah dependency berarti mencabut modul loyalty ikut mencabut semuanya.
Setiap sentuhan ke model loyalty di bawah ini dijaga, dan tanpa modul itu
seluruh flag hanya bernilai kosong.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Serializer yang sama dipakai endpoint promo, supaya bentuk 'rewards' dan
# 'rules' di katalog identik dengan yang dikembalikan /api/pos/promotions.
from ..services.promotion_engine import serialize_reward, serialize_rule

# Peran sebuah produk di dalam satu program.
ROLE_TRIGGER = 'trigger'        # membelinya yang memicu/mengumpulkan promo
ROLE_REWARD = 'reward'          # produk ini yang didapat gratis
ROLE_DISCOUNTED = 'discounted'  # diskon program jatuh pada produk ini

PROMO_CONTEXT_KEYS = ('promo_pos_config_id', 'pos_config_id')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # Semua flag di bawah SENGAJA compute_sudo=False.
    #
    # Cakupan perusahaan diambil dari env.companies, dan env.companies jatuh ke
    # user.company_ids. Dengan compute_sudo=True user itu adalah OdooBot, bukan
    # pemanggil API -- program milik PT. Palawi lalu terlewat dan produknya
    # tidak ber-badge padahal sedang promo. Hak baca loyalty tetap aman karena
    # _get_promotion_programs() memakai sudo() secara eksplisit di dalamnya.

    # Tidak ada field relasi ke loyalty.program di sini, dan itu disengaja:
    # Many2many('loyalty.program') membuat modul loyalty menjadi dependency di
    # level registry, sehingga mencabut loyalty ikut mematikan seluruh API POS.
    # ID program tetap terbaca lewat promotion_details[].program_id.

    # -- flag utama -------------------------------------------------------
    #
    # Promo yang MENYEBUT produk ini. Diskon order-level sengaja tidak masuk
    # sini: satu diskon "10% untuk seluruh order" akan membuat setiap produk di
    # katalog ber-badge promo, dan flag yang selalu true tidak menolong siapa
    # pun. Program seperti itu dilaporkan terpisah lewat has_order_promotion.
    has_promotion = fields.Boolean(
        string='Has Promotion', compute='_compute_promotion_flags',
        search='_search_has_promotion', compute_sudo=False,
        help='Produk ini disebut langsung oleh sebuah program loyalty aktif, '
             'baik sebagai pemicu, hadiah, maupun sasaran diskon.')

    has_order_promotion = fields.Boolean(
        string='Has Order-level Promotion', compute='_compute_promotion_flags',
        search='_search_has_order_promotion', compute_sudo=False,
        help='Ada program aktif yang berlaku untuk order apa pun, sehingga ikut '
             'mengenai produk ini tanpa menyebutnya secara khusus.')

    promotion_count = fields.Integer(
        string='Promotion Count', compute='_compute_promotion_flags',
        compute_sudo=False)

    promotion_labels = fields.Char(
        string='Promotion Labels', compute='_compute_promotion_flags',
        compute_sudo=False, help='Nama program, dipisah koma. Siap dipakai badge.')

    promotion_types = fields.Char(
        string='Promotion Types', compute='_compute_promotion_flags',
        compute_sudo=False,
        help="program_type Odoo, dipisah koma: promotion, buy_x_get_y, "
             "loyalty, gift_card, ewallet, coupons, promo_code, "
             "next_order_coupons.")

    promotion_roles = fields.Char(
        string='Promotion Roles', compute='_compute_promotion_flags',
        compute_sudo=False,
        help='Peran produk ini pada promo-promonya: trigger, reward, discounted.')

    promotion_details = fields.Json(
        string='Promotion Details', compute='_compute_promotion_flags',
        compute_sudo=False,
        help='Rincian program yang menyebut produk ini, termasuk syarat dan hadiahnya.')

    order_promotion_details = fields.Json(
        string='Order Promotion Details', compute='_compute_promotion_flags',
        compute_sudo=False,
        help='Rincian program order-level yang ikut mengenai produk ini.')

    # -- program yang dipertimbangkan -------------------------------------

    @api.model
    def _loyalty_is_available(self):
        """Modul loyalty terpasang? Lihat catatan dependency di atas."""
        return 'loyalty.program' in self.env

    def _promotion_company_ids(self):
        """Perusahaan yang relevan untuk produk-produk ini."""
        company_ids = set(self.mapped('company_id').ids)
        # Produk tanpa company dipakai bersama semua perusahaan, jadi yang
        # menentukan adalah perusahaan yang boleh dilihat pemanggil.
        company_ids.update(self.env.companies.ids or self.env.company.ids)
        return list(company_ids)

    @api.model
    def _promotion_pos_config(self):
        for key in PROMO_CONTEXT_KEYS:
            config_id = self.env.context.get(key)
            if config_id:
                try:
                    config = self.env['pos.config'].sudo().browse(int(config_id))
                except (TypeError, ValueError):
                    continue
                if config.exists():
                    return config
        return self.env['pos.config']

    def _get_promotion_programs(self):
        """Program loyalty aktif yang perlu diperiksa untuk produk-produk ini.

        Bila pemanggil menyebut satu POS (context promo_pos_config_id, yang
        diisi controller dari query param pos_config_id), penyaringannya
        diserahkan ke pos.config._get_program_ids() milik pos_loyalty --
        fungsi yang sama yang dipakai kasir. Ia sudah menerapkan pos_ok,
        batasan pos_config_ids, rentang tanggal, pricelist dan max_usage,
        jadi tidak ada satu pun aturan itu yang ditulis ulang di sini.

        Tanpa POS yang disebut, cakupannya adalah program milik perusahaan
        yang boleh dilihat pemanggil, disaring tanggal.
        """
        if not self._loyalty_is_available():
            # Daftar kosong, bukan recordset: model loyalty.program memang tidak
            # ada di registry ketika modulnya tidak terpasang.
            return []

        Program = self.env['loyalty.program'].sudo()

        config = self._promotion_pos_config()
        if config and hasattr(config, '_get_program_ids'):
            return config.sudo()._get_program_ids().filtered('active')

        domain = [
            ('active', '=', True),
            '|', ('company_id', '=', False),
            ('company_id', 'in', self._promotion_company_ids()),
        ]
        # pos_ok datang dari pos_loyalty. Tanpa modul itu tidak ada yang bisa
        # disaring, dan seluruh program dianggap layak tampil.
        if 'pos_ok' in Program._fields:
            domain.insert(1, ('pos_ok', '=', True))

        today = fields.Date.today()
        return Program.search(domain).filtered(lambda program: (
            (not program.date_from or program.date_from <= today)
            and (not program.date_to or program.date_to >= today)
        ))

    # -- pemetaan produk <-> program --------------------------------------

    def _map_promotion_programs(self, programs):
        """-> ({product_id: {program_id: {role, ...}}}, program order-level)."""
        matches = {}
        order_level = programs.browse()

        def tag(products, program, role):
            for product in products:
                matches.setdefault(product.id, {}).setdefault(program.id, set()).add(role)

        for program in programs:
            is_order_level = not program.rule_ids

            for rule in program.rule_ids:
                domain = rule._get_valid_product_domain()
                if not domain:
                    # Aturan tanpa batasan produk berarti "produk apa pun".
                    is_order_level = True
                    continue
                tag(self.filtered_domain(domain), program, ROLE_TRIGGER)

            for reward in program.reward_ids:
                if reward.reward_type == 'product':
                    reward_ids = set(reward.reward_product_ids.ids)
                    tag(self.filtered(lambda p: p.id in reward_ids), program, ROLE_REWARD)
                elif reward.reward_type == 'discount':
                    # 'order' mendiskon seluruh keranjang dan 'cheapest' memilih
                    # satu baris saat pembayaran; keduanya tidak menyebut produk
                    # tertentu, jadi tidak boleh menandai katalog.
                    if reward.discount_applicability == 'specific':
                        domain = reward._get_discount_product_domain()
                        if domain:
                            tag(self.filtered_domain(domain), program, ROLE_DISCOUNTED)
                        else:
                            is_order_level = True
                    else:
                        is_order_level = True

            if is_order_level:
                order_level |= program

        return matches, order_level

    def _promotion_detail(self, program, roles):
        """Satu program, dalam bentuk yang dipakai badge dan halaman detail."""
        rules = program.rule_ids
        code_rule = rules.filtered(lambda rule: rule.mode == 'with_code')[:1]
        minimum_qty = min(rules.mapped('minimum_qty') or [0])
        minimum_amount = min(rules.mapped('minimum_amount') or [0.0])

        return {
            'program_id': program.id,
            'program_name': program.name,
            'program_type': program.program_type or '',
            'trigger': program.trigger or '',
            'applies_on': program.applies_on or '',
            'roles': roles,
            'date_from': program.date_from.isoformat() if program.date_from else None,
            'date_to': program.date_to.isoformat() if program.date_to else None,
            # Program berkode tidak berjalan otomatis: pelanggan harus
            # menyebut kodenya, dan UI sebaiknya mengatakan itu.
            'requires_code': bool(code_rule),
            'code': (code_rule.code or None) if code_rule else None,
            'minimum_qty': minimum_qty,
            'minimum_amount': minimum_amount,
            # Aturan lengkap, bukan hanya ambang terkecilnya. Promo seperti
            # "beli A + B gratis C" hanya bisa dibaca dari sini: produk mana
            # yang memicu ada di rules[].product_ids, dan berapa unit yang
            # dibutuhkan dari reward_point_amount/reward_point_mode berbanding
            # rewards[].required_points.
            'rules': [serialize_rule(rule) for rule in rules],
            'rewards': [serialize_reward(reward) for reward in program.reward_ids],
        }

    @api.depends_context(*PROMO_CONTEXT_KEYS, 'company', 'allowed_company_ids')
    def _compute_promotion_flags(self):
        programs = self._get_promotion_programs()
        if not programs:
            for product in self:
                product.has_promotion = False
                product.has_order_promotion = False
                product.promotion_count = 0
                product.promotion_labels = False
                product.promotion_types = False
                product.promotion_roles = False
                product.promotion_details = []
                product.order_promotion_details = []
            return

        matches, order_level = self._map_promotion_programs(programs)

        for product in self:
            # Program milik perusahaan lain tidak berlaku untuk produk milik
            # satu perusahaan tertentu, walaupun keduanya terbaca oleh user
            # multi-company yang sama.
            def _same_company(program, product=product):
                return (not program.company_id or not product.company_id
                        or program.company_id == product.company_id)

            by_program = matches.get(product.id, {})
            product_programs = programs.filtered(
                lambda p: p.id in by_program and _same_company(p))
            product_order_programs = order_level.filtered(_same_company)

            roles = sorted({
                role
                for program in product_programs
                for role in by_program[program.id]
            })

            product.has_promotion = bool(product_programs)
            product.promotion_count = len(product_programs)
            product.promotion_labels = ", ".join(product_programs.mapped('name'))
            product.promotion_types = ",".join(dict.fromkeys(
                program.program_type or '' for program in product_programs))
            product.promotion_roles = ",".join(roles)
            product.has_order_promotion = bool(product_order_programs)
            product.promotion_details = [
                product._promotion_detail(program, sorted(by_program[program.id]))
                for program in product_programs
            ]
            product.order_promotion_details = [
                product._promotion_detail(program, ['order'])
                for program in product_order_programs
            ]

    # -- pencarian --------------------------------------------------------

    @api.model
    def _promotion_specific_product_ids(self):
        """ID produk yang disebut langsung oleh program aktif."""
        if not self._loyalty_is_available():
            return []

        Product = self.env['product.product'].sudo()
        product_ids = set()

        for program in self._get_promotion_programs():
            for rule in program.rule_ids:
                domain = rule._get_valid_product_domain()
                if domain:
                    product_ids.update(Product.search(domain).ids)
            for reward in program.reward_ids:
                if reward.reward_type == 'product':
                    product_ids.update(reward.reward_product_ids.ids)
                elif (reward.reward_type == 'discount'
                        and reward.discount_applicability == 'specific'):
                    domain = reward._get_discount_product_domain()
                    if domain:
                        product_ids.update(Product.search(domain).ids)

        return list(product_ids)

    @staticmethod
    def _promotion_search_wants_true(operator, value):
        if operator not in ('=', '!='):
            raise UserError(_(
                "Promotion flags can only be searched with '=' or '!='."))
        return (operator == '=') == bool(value)

    def _search_has_promotion(self, operator, value):
        wants_true = self._promotion_search_wants_true(operator, value)
        product_ids = self._promotion_specific_product_ids()
        return [('id', 'in' if wants_true else 'not in', product_ids)]

    def _search_has_order_promotion(self, operator, value):
        wants_true = self._promotion_search_wants_true(operator, value)
        # Program order-level tidak menyebut produk: entah semuanya kena, entah
        # tidak satu pun. Jadi jawabannya satu domain konstan.
        programs = self._get_promotion_programs()
        exists = False
        if programs:
            _matches, order_level = self.browse()._map_promotion_programs(programs)
            exists = bool(order_level)
        return [(1, '=', 1)] if exists == wants_true else [(0, '=', 1)]
