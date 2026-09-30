# -*- coding: utf-8 -*-
from . import auth_controller
from . import company_controller
from . import promotions_controller
from . import table_layout_controller
from . import product_controller
from . import checkout_controller
from . import pos_context_controller
from . import pos_order_controller
# promo_controller SENGAJA tidak dimuat.
#
# /api/pos/promotions, /promotions/match, /coupons/validate dan kedua endpoint
# pricelist sekarang dilayani rest_api_odoo (controllers/promo_api.py) dengan
# request dan response yang sama persis, supaya satu alur promo tidak perlu
# memanggil dua modul. Route yang sama didaftarkan dua modul membuat werkzeug
# memilih salah satunya secara tidak pasti, jadi sumber lamanya harus diam.
# Berkasnya sengaja dibiarkan ada sebagai rujukan sampai pemindahan ini
# terbukti jalan di staging.
# from . import promo_controller
