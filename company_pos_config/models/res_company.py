# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    pos_config_id = fields.Char(string='Selected POS Config ID', default='')
    pos_config_name = fields.Char(string='Selected POS Config Name', default='')
    server_domain = fields.Char(string='Backend API Server Domain/URL', default='')
    offline_mode = fields.Boolean(string='Forces App into Offline Mode', default=False)
    offline_mode_pin = fields.Char(string='Offline Mode PIN', default='')
    db_name = fields.Char(string='Backend DB Name', default='')
    db_user = fields.Char(string='Backend DB Username', default='')
    db_pass = fields.Char(string='Backend DB Password', default='')
    primary_color = fields.Char(string='App Theme Primary Color', default='#279CB4')
    secondary_color = fields.Char(string='App Theme Secondary Color', default='#FF9800')
    logo_uri = fields.Char(string='Content URI of Store Logo Image', default='')
    store_name = fields.Char(string='Display Name of the Store', default='POS')
    receipt_title = fields.Char(string='Title Printed at Top of Receipts', default='')
    receipt_address = fields.Text(string='Store Address Printed on Receipts', default='')
    wifi_name = fields.Char(string='SSID Shown on Receipt', default='')
    wifi_pass = fields.Char(string='WiFi Password Shown on Receipt', default='')
    soc_ig = fields.Char(string='Instagram Handle', default='')
    soc_tiktok = fields.Char(string='TikTok Handle', default='')
    soc_fb = fields.Char(string='Facebook Page', default='')
    qris_submerchant_id = fields.Char(string='QRIS Sub-merchant ID', default='')
    ip_printer_external = fields.Char(string='LAN Kitchen Printer IP(s)', default='')
    pos_discount_product_id = fields.Char(string='Odoo Product ID (Discount)', default='')
    wifi_profiles_json = fields.Text(string='Saved WiFi Profiles', default='[]')
    printer_paper_width = fields.Selection([
        ('58', '58mm'),
        ('80', '80mm')
    ], string='Receipt Paper Width', default='58')
