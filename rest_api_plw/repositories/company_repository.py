# -*- coding: utf-8 -*-
import json

class CompanyRepository:
    def __init__(self, env):
        self.env = env

    def resolve_allowed_company(self, user_id, company_id=None):
        """Return the res.company record the caller may act on, or None.

        A requested company is honoured only when it is one of the user's
        allowed companies; otherwise the user's default company is used.
        """
        user = self.env['res.users'].sudo().browse(user_id)
        if not user.exists() or not user.company_ids:
            return None

        try:
            company_id = int(company_id) if company_id else 0
        except (TypeError, ValueError):
            company_id = 0

        if company_id and company_id in user.company_ids.ids:
            return self.env['res.company'].sudo().browse(company_id)
        return user.company_id or user.company_ids[0]

    def find_allowed_companies(self, user_id):
        """Lightweight company list for a company picker.

        Distinct from get_companies_config_by_user_id, which returns the full
        24-field POS preference block used at login time.
        """
        user = self.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return None

        default_company_id = user.company_id.id if user.company_id else False
        companies = []
        for company in user.company_ids:
            companies.append({
                'id': company.id,
                'name': company.name,
                'is_default': company.id == default_company_id,
                'currency': {
                    'id': company.currency_id.id,
                    'name': company.currency_id.name,
                    'symbol': company.currency_id.symbol,
                } if company.currency_id else None,
                'pos_config_id': company.pos_config_id or '',
                'pos_config_name': company.pos_config_name or '',
                'store_name': company.store_name or '',
                'logo_uri': company.logo_uri or '',
                'primary_color': company.primary_color or '',
                'secondary_color': company.secondary_color or '',
            })
        return companies

    def get_companies_config_by_user_id(self, user_id):
        user = self.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return []

        companies_data = []
        for company in user.company_ids:
            try:
                wifi_profiles = json.loads(company.wifi_profiles_json or '[]')
            except Exception:
                wifi_profiles = []

            companies_data.append({
                'company_id': company.id,
                'company_name': company.name,
                'pos_config_prefs': {
                    'POS_CONFIG_ID': company.pos_config_id or '',
                    'POS_CONFIG_NAME': company.pos_config_name or '',
                    'server_domain': company.server_domain or '',
                    'offline_mode': company.offline_mode or False,
                    'offline_mode_pin': company.offline_mode_pin or '',
                    'db_name': company.db_name or '',
                    'db_user': company.db_user or '',
                    'db_pass': company.db_pass or '',
                    'primary_color': company.primary_color or '',
                    'secondary_color': company.secondary_color or '',
                    'logo_uri': company.logo_uri or '',
                    'store_name': company.store_name or '',
                    'receipt_title': company.receipt_title or '',
                    'receipt_address': company.receipt_address or '',
                    'wifi_name': company.wifi_name or '',
                    'wifi_pass': company.wifi_pass or '',
                    'soc_ig': company.soc_ig or '',
                    'soc_tiktok': company.soc_tiktok or '',
                    'soc_fb': company.soc_fb or '',
                    'qris_submerchant_id': company.qris_submerchant_id or '',
                    'ip_printer_external': company.ip_printer_external or '',
                    'POS_DISCOUNT_PRODUCT_ID': company.pos_discount_product_id or '',
                    'wifi_profiles_json': wifi_profiles,
                    'printer_paper_width': company.printer_paper_width or '58',
                }
            })
        return companies_data
