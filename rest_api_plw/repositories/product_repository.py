# -*- coding: utf-8 -*-
from ..domain.entities.product import ProductEntity
from ..domain.entities.pos_category import PosCategoryEntity

class ProductRepository:
    def __init__(self, env):
        self.env = env

    def get_products_by_ids_and_company(self, product_ids, company):
        """Resolve ids to product.product records, keyed by the id that was asked for.

        Clients send either a product.product id or a product.template id (the
        catalog endpoints expose templates), so both are accepted. A template
        resolves to its default variant. Ids that do not exist are skipped.
        """
        if not product_ids:
            return {}

        company_id = company.id if hasattr(company, 'id') else company
        product_model = self.env["product.product"].sudo().with_company(company_id)
        template_model = self.env["product.template"].sudo().with_company(company_id)

        product_map = {}
        unresolved = []
        for product in product_model.browse(product_ids).exists():
            product_map[product.id] = product
        for pid in product_ids:
            if pid not in product_map:
                unresolved.append(pid)

        # Fall back to interpreting the remaining ids as templates
        for template in template_model.browse(unresolved).exists():
            variant = template.product_variant_id
            if variant:
                product_map[template.id] = variant

        return product_map

    def find_pos_products(self, company_id, config_pos_id=None, categ_id=None, pos_categ_id=None,
                          search=None, page=1, limit=10, base_url=""):
        # 1. Fetch and validate the POS config when one is given. Without it the
        # catalogue is company-wide and no POS-side restriction applies.
        pos_config = None
        if config_pos_id:
            try:
                config_pos_id = int(config_pos_id)
            except (TypeError, ValueError):
                raise Exception("Invalid 'pos_config_id'")

            pos_config = self.env["pos.config"].sudo().browse(config_pos_id)
            if not pos_config.exists():
                raise Exception(f"POS Config ID {config_pos_id} does not exist")

        # 2. Build search domain
        domain = [
            ("company_id", "=", company_id),
            ("available_in_pos", "=", True)
        ]

        if categ_id:
            try:
                domain.append(("categ_id", "=", int(categ_id)))
            except (TypeError, ValueError):
                raise Exception("Invalid 'categ_id'")

        if pos_categ_id:
            try:
                pos_categ_id = int(pos_categ_id)
            except (TypeError, ValueError):
                raise Exception("Invalid 'pos_categ_id'")

            pos_categ = self.env["pos.category"].sudo().browse(pos_categ_id)
            if not pos_categ.exists():
                raise Exception(f"POS Category ID {pos_categ_id} does not exist")

            # Validate if POS Category is allowed for config_pos_id
            if pos_categ.pos_ids and config_pos_id not in pos_categ.pos_ids.ids:
                raise Exception(f"POS Category ID {pos_categ_id} is not valid for POS Config ID {config_pos_id}")
            if pos_config.limit_categories and pos_config.iface_available_categ_ids and pos_categ_id not in pos_config.iface_available_categ_ids.ids:
                raise Exception(f"POS Category ID {pos_categ_id} is not valid for POS Config ID {config_pos_id}")

            domain.append(("pos_categ_ids", "in", [pos_categ_id]))

        if search:
            domain.append(("name", "ilike", str(search)))

        # 3. Search product templates
        templates = self.env["product.template"].sudo().with_company(company_id).search(domain)

        # 4. Filter products based on POS restrictions
        filtered_templates = []
        for tmpl in templates:
            is_allowed = True
            for pos_categ in tmpl.pos_categ_ids:
                if pos_categ.pos_ids and config_pos_id not in pos_categ.pos_ids.ids:
                    is_allowed = False
                    break

            if is_allowed and pos_config.limit_categories and pos_config.iface_available_categ_ids:
                allowed_categ_ids = pos_config.iface_available_categ_ids.ids
                prod_pos_categ_ids = tmpl.pos_categ_ids.ids
                if prod_pos_categ_ids and not any(cid in allowed_categ_ids for cid in prod_pos_categ_ids):
                    is_allowed = False

            if is_allowed:
                filtered_templates.append(tmpl)

        # 5. Apply pagination on the filtered list
        try:
            page = int(page) if page else 1
        except (TypeError, ValueError):
            page = 1
        try:
            limit = int(limit) if limit else 10
        except (TypeError, ValueError):
            limit = 10

        start = (page - 1) * limit
        end = start + limit
        paginated_templates = filtered_templates[start:end]

        # 6. Map to entities
        product_list = []
        for tmpl in paginated_templates:
            # Resolve Odoo product.category details
            category_data = {
                "id": tmpl.categ_id.id,
                "name": tmpl.categ_id.name
            } if tmpl.categ_id else None

            # Resolve Odoo pos.category details
            pos_categories_data = [
                {"id": pc.id, "name": pc.name} for pc in tmpl.pos_categ_ids
            ]

            # Resolve image URL if image exists
            image_url = ""
            if tmpl.image_128:
                image_url = f"{base_url}/api/pos/product/image/{tmpl.id}"

            # Resolve attributes
            attributes_data = []
            for line in tmpl.attribute_line_ids:
                attributes_data.append({
                    "name": line.attribute_id.name,
                    "values": [val.name for val in line.value_ids]
                })

            # Resolve variants
            variants_data = []
            for variant in tmpl.product_variant_ids:
                variants_data.append({
                    "id": variant.id,
                    "display_name": variant.display_name or variant.name,
                    "price": variant.lst_price or variant.list_price,
                    "stock_qty": variant.qty_available
                })

            product_list.append(ProductEntity(
                id=tmpl.id,
                name=tmpl.name,
                type=tmpl.type,
                is_storable=tmpl.is_storable,
                list_price=tmpl.list_price,
                standard_price=tmpl.standard_price,
                company_id=tmpl.company_id.id,
                stock_qty=tmpl.qty_available,
                image_url=image_url,
                category=category_data,
                pos_categories=pos_categories_data,
                attributes=attributes_data,
                variants=variants_data
            ))

        return product_list

    def find_pos_categories(self, company_id, config_pos_id=None, base_url=""):
        # 1. Build database search domain
        domain = [("company_id", "=", company_id)]

        if config_pos_id:
            try:
                config_pos_id = int(config_pos_id)
            except (TypeError, ValueError):
                raise Exception("Invalid 'pos_config_id'")

            # Fetch and validate POS config
            pos_config = self.env["pos.config"].sudo().browse(config_pos_id)
            if not pos_config.exists():
                raise Exception(f"POS Config ID {config_pos_id} does not exist")

            if pos_config.limit_categories and pos_config.iface_available_categ_ids:
                allowed_categ_ids = pos_config.iface_available_categ_ids.ids
                if allowed_categ_ids:
                    domain.append(("id", "in", allowed_categ_ids))

        # 2. Search pos categories
        categories = self.env["pos.category"].sudo().with_company(company_id).search(domain)

        # 3. Filter categories based on category-side pos_ids restrictions
        filtered_categories = []
        for categ in categories:
            if config_pos_id and config_pos_id not in categ.pos_ids.ids:
                continue
            filtered_categories.append(categ)

        # 4. Map to entities
        category_list = []
        for categ in filtered_categories:
            parent_data = {
                "id": categ.parent_id.id,
                "name": categ.parent_id.name
            } if categ.parent_id else None

            allowed_pos_data = [
                {"id": pc.id, "name": pc.name} for pc in categ.pos_ids
            ]

            image_url = ""
            if categ.image_128:
                image_url = f"{base_url}/web/image?model=pos.category&id={categ.id}&field=image_128"

            category_list.append(PosCategoryEntity(
                id=categ.id,
                name=categ.name,
                parent=parent_data,
                company_id=categ.company_id.id if categ.company_id else None,
                allowed_pos=allowed_pos_data,
                image_url=image_url
            ))

        return category_list