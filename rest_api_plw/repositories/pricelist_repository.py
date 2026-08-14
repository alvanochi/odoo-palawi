# -*- coding: utf-8 -*-
from odoo.exceptions import UserError


class PricelistRepository:
    def __init__(self, env):
        self.env = env

    def _resolve_config(self, pos_config_id):
        config = self.env['pos.config'].sudo().browse(pos_config_id)
        if not config.exists():
            raise UserError(f"POS Config ID {pos_config_id} does not exist")
        return config

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

    def find_pricelists_for_config(self, pos_config_id):
        """Pricelists usable on a POS.

        "Price per location" maps onto POS/company pricelists: picking the POS
        picks the store, and the store's pricelist decides the price.
        """
        config = self._resolve_config(pos_config_id)
        default = config.pricelist_id

        if config.use_pricelist:
            pricelists = config.available_pricelist_ids
        else:
            pricelists = default

        return [self._pricelist_dict(pl, is_default=(pl.id == default.id)) for pl in pricelists]

    def find_pricelists_for_company(self, company_id):
        company = self.env['res.company'].sudo().browse(company_id)
        if not company.exists():
            raise UserError(f"Company ID {company_id} does not exist")

        pricelists = self.env['product.pricelist'].sudo().with_company(company_id).search([
            '|', ('company_id', '=', False), ('company_id', '=', company_id)
        ], order='name asc')
        return [self._pricelist_dict(pl) for pl in pricelists]

    def resolve_pricelist(self, pricelist_id, config=None):
        """Validate a pricelist id, optionally against what a POS allows."""
        pricelist = self.env['product.pricelist'].sudo().browse(pricelist_id)
        if not pricelist.exists():
            raise UserError(f"Pricelist ID {pricelist_id} does not exist")

        if config is not None and config.use_pricelist:
            allowed_ids = config.available_pricelist_ids.ids
            if allowed_ids and pricelist.id not in allowed_ids:
                raise UserError(
                    f"Pricelist '{pricelist.name}' is not available on POS '{config.name}'"
                )
        return pricelist

    def compute_prices(self, pricelist_id, items, partner_id=False, pos_config_id=None):
        config = self._resolve_config(pos_config_id) if pos_config_id else None
        pricelist = self.resolve_pricelist(pricelist_id, config)

        company_id = pricelist.company_id.id or (config.company_id.id if config else self.env.company.id)
        product_model = self.env['product.product'].sudo().with_company(company_id)
        template_model = self.env['product.template'].sudo().with_company(company_id)
        partner = self.env['res.partner'].sudo().browse(partner_id) if partner_id else None

        results = []
        for item in items:
            raw_id = item.get('product_id')
            if not raw_id:
                continue
            try:
                raw_id = int(raw_id)
            except (TypeError, ValueError):
                raise UserError(f"Invalid 'product_id' {item.get('product_id')}")

            try:
                qty = float(item.get('qty', 1.0))
            except (TypeError, ValueError):
                qty = 1.0

            product = product_model.browse(raw_id)
            if not product.exists():
                template = template_model.browse(raw_id)
                if not template.exists():
                    raise UserError(f"Product ID {raw_id} does not exist")
                product = template.product_variant_id
                if not product:
                    raise UserError(f"Product ID {raw_id} has no variant")

            # Core computation: never re-implement pricelist rules here.
            price = pricelist._get_product_price(
                product, qty, partner if partner and partner.exists() else False
            )
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

        return {
            'pricelist': self._pricelist_dict(pricelist),
            'items': results,
        }
