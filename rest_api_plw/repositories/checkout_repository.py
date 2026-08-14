# -*- coding: utf-8 -*-
import json
import uuid

from odoo import fields
from odoo.exceptions import UserError
from ..domain.entities.checkout import CheckoutResultEntity
from ..domain.services.reward_calculator import compute_discount_amount

class TableOccupiedException(Exception):
    def __init__(self, message, existing_bill_id):
        super().__init__(message)
        self.existing_bill_id = existing_bill_id

class CheckoutRepository:
    def __init__(self, env):
        self.env = env

    def find_active_tables(self, company_id, pos_id=None):
        # 1. Search floors for the company.
        # restaurant.floor has no company_id in Odoo 18: a floor belongs to a
        # company only through the POS configs it is linked to.
        config_domain = [("company_id", "=", company_id)]
        if pos_id:
            try:
                config_domain.append(("id", "=", int(pos_id)))
            except ValueError:
                pass

        config_ids = self.env["pos.config"].sudo().with_company(company_id).search(config_domain).ids
        floors = self.env["restaurant.floor"].sudo().with_company(company_id).search([
            ("pos_config_ids", "in", config_ids)
        ]) if config_ids else self.env["restaurant.floor"]

        # 2. Search active tables on those floors
        tables = self.env["restaurant.table"].sudo().with_company(company_id).search([
            ("floor_id", "in", floors.ids),
            ("active", "=", True)
        ])

        # 3. Build table list output
        table_list = []
        for table in tables:
            table_list.append({
                "id": table.id,
                "table_number": table.table_number,
                "seats": table.seats,
                "floor": {
                    "id": table.floor_id.id,
                    "name": table.floor_id.name
                }
            })
        return table_list

    def _compute_line_amounts(self, taxes, price_unit, qty, company, fiscal_position, partner, product):
        """-> (price_subtotal excl. tax, price_subtotal_incl).

        pos.order.line.price_subtotal / price_subtotal_incl are plain stored
        fields: the POS UI computes them client-side, so creating orders
        server-side we must run the tax engine ourselves. Mirrors
        pos.order.line._compute_amount_line_all().
        """
        if not taxes:
            total = price_unit * qty
            return total, total

        mapped_taxes = fiscal_position.map_tax(taxes) if fiscal_position else taxes
        result = mapped_taxes.compute_all(
            price_unit, company.currency_id, qty,
            product=product, partner=partner or False,
        )
        return result['total_excluded'], result['total_included']

    def _build_reward_lines(self, company, pos_config, pricelist, rewards, cart_data, coupon_info):
        """Turn requested rewards into order lines, priced server-side.

        Returns (lines, discount_total, rewards_applied, coupon_data). The
        client only ever sends reward_id: amounts are recomputed here so a
        crafted payload cannot invent a discount.

        Reward lines carry no tax, matching Odoo's default where the reward's
        discount_line_product_id has none. Amounts are tax-inclusive, so the
        discount equals what the customer sees; the order's amount_tax is not
        reduced by it. Businesses that need tax-adjusted discounts have to set
        loyalty.reward.tax_ids and extend this.
        """
        if not rewards:
            return [], 0.0, [], {}

        allowed_reward_ids = pos_config.sudo()._get_program_ids().reward_ids.ids
        coupon_points = coupon_info.get('points', 0.0) if coupon_info else 0.0
        coupon_id = coupon_info.get('coupon_id') if coupon_info else None
        coupon_program_id = coupon_info.get('program_id') if coupon_info else None

        cart_by_product = {item['product'].id: item for item in cart_data}

        lines = []
        rewards_applied = []
        discount_total = 0.0
        points_spent = 0.0

        for entry in rewards:
            reward_id = entry.get('reward_id') if isinstance(entry, dict) else entry
            try:
                reward_id = int(reward_id)
            except (TypeError, ValueError):
                raise UserError(f"Invalid 'reward_id' {reward_id}")

            reward = self.env['loyalty.reward'].sudo().browse(reward_id)
            if not reward.exists():
                raise UserError(f"Reward ID {reward_id} does not exist")
            if reward.id not in allowed_reward_ids:
                raise UserError(
                    f"Reward '{reward.description}' is not available on POS '{pos_config.name}'"
                )

            program = reward.program_id
            if program.trigger == 'with_code':
                if not coupon_info or coupon_program_id != program.id:
                    raise UserError(
                        f"Reward '{reward.description}' requires a valid coupon code"
                    )
            if coupon_info and coupon_program_id == program.id:
                if reward.required_points > coupon_points:
                    raise UserError(
                        f"Not enough points on this coupon for reward '{reward.description}'"
                    )

            # Groups the reward's lines together, and links them to the coupon
            identifier_code = uuid.uuid4().hex[:12]
            line_coupon_id = coupon_id if coupon_program_id == program.id else False
            base_vals = {
                "is_reward_line": True,
                "reward_id": reward.id,
                "reward_identifier_code": identifier_code,
                "coupon_id": line_coupon_id,
                "points_cost": reward.required_points or 0.0,
            }

            if reward.reward_type == 'discount':
                amount = compute_discount_amount(reward, cart_data, coupon_points)
                if amount <= 0:
                    continue
                if not reward.discount_line_product_id:
                    reward._create_missing_discount_line_products()
                lines.append((0, 0, dict(base_vals, **{
                    "product_id": reward.discount_line_product_id.id,
                    "qty": 1,
                    "price_unit": -amount,
                    "price_subtotal": -amount,
                    "price_subtotal_incl": -amount,
                })))
                discount_total += amount
                rewards_applied.append({
                    "reward_id": reward.id,
                    "program_id": program.id,
                    "description": reward.description,
                    "reward_type": "discount",
                    "amount": amount,
                })
            else:
                free_product = self._resolve_reward_product(reward, entry)
                if not free_product.available_in_pos:
                    raise UserError(
                        f"Reward product '{free_product.display_name}' is not available in POS"
                    )
                free_qty = reward.reward_product_qty or 1.0
                unit_price = free_product.lst_price or free_product.list_price
                if pricelist:
                    unit_price = pricelist._get_product_price(free_product, free_qty)

                in_cart = cart_by_product.get(free_product.id)
                if in_cart:
                    # The product is already paid for in the cart, so the reward
                    # discounts units already there rather than adding new ones.
                    free_qty = min(free_qty, in_cart['qty'])
                    amount = unit_price * free_qty
                    if amount <= 0:
                        continue
                    if not reward.discount_line_product_id:
                        reward._create_missing_discount_line_products()
                    lines.append((0, 0, dict(base_vals, **{
                        "product_id": reward.discount_line_product_id.id,
                        "qty": 1,
                        "price_unit": -amount,
                        "price_subtotal": -amount,
                        "price_subtotal_incl": -amount,
                    })))
                    discount_total += amount
                else:
                    amount = 0.0
                    lines.append((0, 0, dict(base_vals, **{
                        "product_id": free_product.id,
                        "qty": free_qty,
                        "price_unit": 0.0,
                        "price_subtotal": 0.0,
                        "price_subtotal_incl": 0.0,
                    })))

                rewards_applied.append({
                    "reward_id": reward.id,
                    "program_id": program.id,
                    "description": reward.description,
                    "reward_type": "product",
                    "product_id": free_product.id,
                    "product_name": free_product.display_name,
                    "qty": free_qty,
                    "amount": amount,
                })

            if line_coupon_id:
                points_spent += reward.required_points or 0.0

        coupon_data = {}
        if coupon_id and points_spent:
            coupon_data[coupon_id] = {
                "program_id": coupon_program_id,
                "points": -points_spent,
                "line_codes": [
                    line[2]["reward_identifier_code"] for line in lines
                    if line[2].get("coupon_id") == coupon_id
                ],
            }

        return lines, discount_total, rewards_applied, coupon_data

    def _resolve_reward_product(self, reward, entry):
        """Which product a 'free product' reward hands out."""
        candidates = reward.reward_product_ids
        if not candidates:
            raise UserError(f"Reward '{reward.description}' has no reward product configured")

        requested = entry.get('product_id') if isinstance(entry, dict) else None
        if requested:
            try:
                requested = int(requested)
            except (TypeError, ValueError):
                raise UserError(f"Invalid reward 'product_id' {requested}")
            product = candidates.filtered(lambda p: p.id == requested)
            if not product:
                raise UserError(
                    f"Product ID {requested} is not one of the reward products for "
                    f"'{reward.description}'"
                )
            return product[0]

        if len(candidates) > 1:
            raise UserError(
                f"Reward '{reward.description}' offers several products, "
                f"'product_id' is required to pick one"
            )
        return candidates[0]

    def process_checkout(self, pos_id, customer_name, customer_phone, table_id, table_number,
                         detail_product, pricelist_id=None, coupon_code=None, rewards=None,
                         auto_open_session=False):
        # 1. Verify POS configuration exists
        pos_config = self.env["pos.config"].sudo().browse(pos_id)
        if not pos_config.exists():
            raise UserError(f"POS Config ID {pos_id} does not exist")

        company = pos_config.company_id

        # 2. Check/resolve active POS session.
        # The newest one wins, matching /api/pos/sessions/active, because a
        # cashier may have left an earlier session open.
        session = self.env["pos.session"].sudo().with_company(company).search([
            ("config_id", "=", pos_config.id),
            ("state", "=", "opened")
        ], order="start_at desc, id desc", limit=1)

        if not session:
            # Opening a session on the client's behalf hides the fact that the
            # cashier never opened one, so it is opt-in only.
            fallback = self.env["pos.session"].sudo().with_company(company).search([
                ("config_id", "=", pos_config.id),
                ("state", "=", "opening_control")
            ], order="start_at desc, id desc", limit=1)
            if fallback and auto_open_session:
                # In Odoo 18 action_pos_session_open() only seeds the cash
                # balance; set_opening_control is what actually opens it.
                fallback.set_opening_control(0, '')
                if fallback.state != 'opened':
                    raise UserError(
                        f"Could not open POS session for '{pos_config.name}' automatically. "
                        f"Please open it from the Odoo backend."
                    )
                session = fallback
            else:
                raise UserError(
                    f"No active/open POS session found for POS Config ID {pos_config.name}. Please open the session first from Odoo backend."
                )

        # 2b. Resolve the pricelist that decides the prices charged
        pricelist = False
        if pricelist_id:
            pricelist = self.env["product.pricelist"].sudo().browse(int(pricelist_id))
            if not pricelist.exists():
                raise UserError(f"Pricelist ID {pricelist_id} does not exist")
            if pos_config.use_pricelist and pos_config.available_pricelist_ids:
                if pricelist.id not in pos_config.available_pricelist_ids.ids:
                    raise UserError(
                        f"Pricelist '{pricelist.name}' is not available on POS '{pos_config.name}'"
                    )

        # 3. Resolve Customer Partner (link by phone/name or create)
        partner = False
        if customer_phone:
            partner = self.env["res.partner"].sudo().with_company(company).search([("phone", "=", str(customer_phone))], limit=1)
            if not partner and customer_name:
                partner = self.env["res.partner"].sudo().with_company(company).search([("name", "=", str(customer_name))], limit=1)
        elif customer_name:
            partner = self.env["res.partner"].sudo().with_company(company).search([("name", "=", str(customer_name))], limit=1)

        if not partner and (customer_name or customer_phone):
            partner = self.env["res.partner"].sudo().with_company(company).create({
                "name": customer_name or "POS Customer",
                "phone": customer_phone or False,
                "company_id": company.id
            })

        # 4. Resolve Restaurant Table
        table = False
        floors = self.env["restaurant.floor"].sudo().with_company(company).search([("pos_config_ids", "in", [pos_config.id])])

        if table_id:
            try:
                target_table = self.env["restaurant.table"].sudo().with_company(company).browse(int(table_id))
                if target_table.exists() and target_table.floor_id.id in floors.ids:
                    table = target_table
            except ValueError:
                pass

        if not table and table_number:
            table = self.env["restaurant.table"].sudo().with_company(company).search([
                ("floor_id", "in", floors.ids),
                ("table_number", "=", str(table_number))
            ], limit=1)

        # 5. Loop and validate products in checkout list
        order_lines = []
        amount_total = 0.0
        amount_tax = 0.0
        cart_data = []   # feeds the reward calculation below

        # POS applies the fiscal position configured on the POS itself
        fiscal_position = pos_config.default_fiscal_position_id

        for line_item in detail_product:
            prod_id = line_item.get("product_id")
            variant_id = line_item.get("variant_id")
            qty = float(line_item.get("qty", 1.0))

            if not prod_id:
                raise UserError("Missing 'product_id' in detail_product item")
            try:
                prod_id = int(prod_id)
            except ValueError:
                raise UserError(f"Invalid 'product_id' {prod_id}")

            # Resolve template and variant product
            # 1. First, check if prod_id refers to a valid product.template in this company (or shared)
            prod_tmpl = self.env["product.template"].sudo().with_company(company).search([
                ("id", "=", prod_id),
                ("company_id", "in", (company.id, False)),
                ("available_in_pos", "=", True)
            ], limit=1)

            if prod_tmpl.exists():
                product_template = prod_tmpl
                if variant_id:
                    try:
                        variant_product = self.env["product.product"].sudo().with_company(company).browse(int(variant_id))
                    except ValueError:
                        variant_product = self.env["product.product"]
                else:
                    variant_product = self.env["product.product"]
            else:
                # 2. If not found as a template, check if it's a product.product (variant) directly
                prod_var = self.env["product.product"].sudo().with_company(company).search([
                    ("id", "=", prod_id),
                    ("company_id", "in", (company.id, False)),
                    ("available_in_pos", "=", True)
                ], limit=1)

                if prod_var.exists():
                    product_template = prod_var.product_tmpl_id
                    variant_product = prod_var
                else:
                    # Fallback to browse if no company restriction matches (to raise a friendly error later)
                    prod_var = self.env["product.product"].sudo().with_company(company).browse(prod_id)
                    if prod_var.exists():
                        product_template = prod_var.product_tmpl_id
                        variant_product = prod_var
                    else:
                        prod_tmpl = self.env["product.template"].sudo().with_company(company).browse(prod_id)
                        if prod_tmpl.exists():
                            product_template = prod_tmpl
                            if variant_id:
                                try:
                                    variant_product = self.env["product.product"].sudo().with_company(company).browse(int(variant_id))
                                except ValueError:
                                    variant_product = self.env["product.product"]
                            else:
                                variant_product = self.env["product.product"]
                        else:
                            raise UserError(f"Product ID {prod_id} does not exist")

            # Check if product has multiple variants
            has_multiple_variants = product_template.product_variant_count > 1
            if has_multiple_variants:
                if not variant_product or not variant_product.exists():
                    raise UserError(
                        f"Product '{product_template.name}' (ID {product_template.id}) has multiple variants. A valid 'variant_id' is required."
                    )
                if variant_product.product_tmpl_id.id != product_template.id:
                    raise UserError(
                        f"Variant ID {variant_product.id} does not belong to product '{product_template.name}'"
                    )
                product = variant_product
            else:
                if not variant_product or not variant_product.exists():
                    product = product_template.product_variant_id
                else:
                    if variant_product.product_tmpl_id.id != product_template.id:
                        raise UserError(
                            f"Variant ID {variant_product.id} does not belong to product '{product_template.name}'"
                        )
                    product = variant_product

            if not product or not product.exists():
                raise UserError(f"Could not resolve a valid product variant for product ID {prod_id}")

            # Validate company mismatch
            if product.company_id and product.company_id.id != company.id:
                raise UserError(
                    f"Product '{product.name}' (ID {prod_id}) company does not match POS company"
                )

            # Validate available in POS
            if not product.available_in_pos:
                raise UserError(f"Product '{product.name}' (ID {prod_id}) is not set as Available in POS")

            # Validate allowed categories under this POS config
            if pos_config.limit_categories:
                allowed_categ_ids = pos_config.iface_available_categ_ids.ids
                prod_pos_categ_ids = product.pos_categ_ids.ids
                if not any(cid in allowed_categ_ids for cid in prod_pos_categ_ids):
                    raise UserError(
                        f"Product '{product.name}' (ID {prod_id}) does not belong to any of the allowed POS categories for POS '{pos_config.name}'"
                    )

            # Validate Allowed POS category filters
            for pos_categ in product.pos_categ_ids:
                if pos_categ.pos_ids and pos_config.id not in pos_categ.pos_ids.ids:
                    raise UserError(
                        f"Product '{product.name}' (ID {prod_id}) uses POS Category '{pos_categ.name}' which is restricted from POS config '{pos_config.name}'"
                    )

            if pricelist:
                price_unit = pricelist._get_product_price(product, qty, partner or False)
            else:
                price_unit = product.lst_price or product.list_price

            line_taxes = product.taxes_id.filtered_domain(
                self.env['account.tax']._check_company_domain(company))
            subtotal, subtotal_incl = self._compute_line_amounts(
                line_taxes, price_unit, qty, company, fiscal_position, partner, product)

            amount_total += subtotal_incl
            amount_tax += subtotal_incl - subtotal

            # Promo thresholds and discounts run on the tax-inclusive amount,
            # i.e. what the customer actually sees and pays.
            cart_data.append({
                "product": product,
                "qty": qty,
                "price": price_unit,
                "subtotal": subtotal_incl,
            })

            note = line_item.get("note") or ""

            order_lines.append((0, 0, {
                "product_id": product.id,
                "qty": qty,
                "price_unit": price_unit,
                "tax_ids": [(6, 0, line_taxes.ids)],
                "price_subtotal": subtotal,
                "price_subtotal_incl": subtotal_incl,
                "customer_note": note,
                "note": note,
            }))

        if not order_lines:
            raise UserError("No valid products to check out")

        # 5b. Rewards. The client's numbers are never trusted: every reward is
        # re-resolved and re-priced here from the cart we just validated.
        coupon_info = None
        if coupon_code:
            coupon_info = pos_config.sudo().use_coupon_code(
                coupon_code, fields.Datetime.now().isoformat(),
                partner.id if partner else False,
                pricelist.id if pricelist else False,
            )
            if not coupon_info.get("successful"):
                raise UserError(
                    coupon_info.get("payload", {}).get("error_message", "Invalid coupon code")
                )
            coupon_info = coupon_info.get("payload", {})

        reward_lines, discount_total, rewards_applied, coupon_data = self._build_reward_lines(
            company, pos_config, pricelist, rewards or [], cart_data, coupon_info
        )
        order_lines.extend(reward_lines)
        amount_total -= discount_total
        if amount_total < 0:
            amount_total = 0.0

        # 6. Create POS Order in draft state.
        # Payment is confirmed separately by mark_order_as_paid(), so the order
        # stays unpaid here: stock must not leave before the money is in.
        pos_ref = f"API-{session.id}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{int(fields.Datetime.now().timestamp())}"
        order_vals = {
            "session_id": session.id,
            "company_id": company.id,
            "partner_id": partner.id if partner else False,
            "amount_total": amount_total,
            "amount_tax": amount_tax,
            "amount_paid": 0.0,
            "amount_return": 0.0,
            "pos_reference": pos_ref,
            "lines": order_lines,
            "state": "draft",
        }
        if table:
            order_vals["table_id"] = table.id
        if pricelist:
            order_vals["pricelist_id"] = pricelist.id

        # tracking_number (the number shown to the customer and on the KDS) is
        # computed from sequence_number, which must be unique per session.
        # Odoo's POS UI maintains this counter; creating orders server-side we
        # have to advance it ourselves or every order gets the same number.
        session.sudo().sequence_number += 1
        order_vals["sequence_number"] = session.sequence_number

        order = self.env["pos.order"].sudo().with_company(company).create(order_vals)

        # 6b. Deduct coupon points and write loyalty history. Without this the
        # same voucher could be redeemed over and over. Points are spent when
        # the order is placed, not when it is paid, so an abandoned order holds
        # its coupon until the order is cancelled.
        if coupon_data:
            order.sudo().confirm_coupon_programs(coupon_data)

        # 7. Create the poskas.bill fronting this order, plus one line per
        # order line (reward lines included, so the bill total matches).
        bill_name = f"Bill - {customer_name or 'Customer'}"
        if table:
            bill_name += f" (Meja {table.table_number})"
        elif table_number:
            bill_name += f" (Meja {table_number})"

        bill_vals = {
            "name": bill_name,
            "config_id": pos_config.id,
            "name_customer": customer_name or "Customer",
            "state": "open",
            "type_order": "dine_in",
            "pos_order_id": order.id,
        }
        if table:
            bill_vals["table_id"] = table.id
            bill_vals["table_ref"] = ""
        else:
            bill_vals["table_id"] = False
            bill_vals["table_ref"] = str(table_number) if table_number else ""

        bill = self.env["poskas.bill"].sudo().with_company(company).create(bill_vals)

        for line in order.lines:
            self.env["poskas.bill.line"].sudo().with_company(company).create({
                "bill_id": bill.id,
                "product_id": line.product_id.id,
                "qty": line.qty,
                "price_unit": line.price_unit,
                "discount_percent": 0.0,
                "note": line.customer_note or line.note or "",
            })

        bill._compute_amount_total()

        # order_name is still the placeholder '/' here: pos.order only draws a
        # receipt number from the sequence when state flips to 'paid', which
        # mark_order_as_paid() does. Clients should key on order_id or
        # tracking_number until the order is paid.
        return CheckoutResultEntity(
            order_id=order.id,
            order_name=order.name,
            amount_total=order.amount_total,
            table_number=order.table_id.table_number if order.table_id else None,
            customer_name=order.partner_id.name if order.partner_id else None,
            bill_id=bill.id,
            session_id=session.id,
            state=order.state,
            tracking_number=order.tracking_number or None,
            pricelist={
                "id": pricelist.id,
                "name": pricelist.name,
            } if pricelist else None,
            discount_total=discount_total,
            rewards_applied=rewards_applied,
        )

    def _find_order(self, order_id_or_ref):
        """Resolve an order by database id, receipt name, or pos_reference."""
        try:
            order_id = int(order_id_or_ref)
            domain = [
                "|", "|",
                ("id", "=", order_id),
                ("name", "=", str(order_id_or_ref)),
                ("pos_reference", "=", str(order_id_or_ref)),
            ]
        except (TypeError, ValueError):
            domain = [
                "|",
                ("name", "=", str(order_id_or_ref)),
                ("pos_reference", "=", str(order_id_or_ref)),
            ]

        order = self.env["pos.order"].sudo().search(domain, limit=1)
        if not order.exists():
            raise UserError(f"POS Order '{order_id_or_ref}' does not exist")
        return order

    def create_payment_evidence(self, order_id_or_ref, payload):
        """Attach the payment gateway's raw callback to an order."""
        order = self._find_order(order_id_or_ref)

        if isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)

        evidence = self.env["pos.order.payment.evidence"].sudo().create({
            "order_id": order.id,
            "payload": payload_str,
        })
        return evidence.id

    def _resolve_payment_method(self, order, payment_method_id=None, required=False):
        """Resolve a payment method and ensure it belongs to this POS config."""
        pos_config = order.session_id.config_id

        if payment_method_id in (None, "", False):
            if required:
                raise UserError("Missing required parameter 'payment_method_id'")
            payment_method = pos_config.payment_method_ids[:1]
            if not payment_method:
                raise UserError(
                    f"POS '{pos_config.name}' has no configured payment method"
                )
            return payment_method

        try:
            payment_method_id = int(payment_method_id)
        except (TypeError, ValueError):
            raise UserError("Invalid 'payment_method_id', must be an integer")

        payment_method = self.env["pos.payment.method"].sudo().browse(payment_method_id)
        if not payment_method.exists():
            raise UserError(f"Payment Method ID {payment_method_id} does not exist")
        if payment_method not in pos_config.payment_method_ids:
            raise UserError(
                f"Payment method '{payment_method.name}' is not available on POS '{pos_config.name}'"
            )
        return payment_method

    def _create_pos_stock_picking(self, order):
        """Create/complete POS stock movement immediately for an order.

        The custom checkout contract moves stock at mark_paid time even when
        the POS config is set to update stock at session closing. Refunds must
        mirror that behaviour, so this intentionally calls the stock helper
        directly instead of pos.order._create_order_picking(), which may defer
        the movement until session closing.
        """
        company = order.company_id
        pos_config = order.session_id.config_id
        picking_type = pos_config.picking_type_id
        if not picking_type:
            return self.env["stock.picking"]

        partner = order.partner_id
        if partner and partner.property_stock_customer:
            destination_id = partner.property_stock_customer.id
        elif not picking_type.default_location_dest_id:
            destination_id = (
                self.env["stock.warehouse"]
                .sudo()
                .with_company(company)
                ._get_partner_locations()[0]
                .id
            )
        else:
            destination_id = picking_type.default_location_dest_id.id

        if not destination_id:
            return self.env["stock.picking"]

        pickings = (
            self.env["stock.picking"]
            .sudo()
            .with_company(company)
            ._create_picking_from_pos_order_lines(
                destination_id, order.lines, picking_type, order.partner_id
            )
        )
        all_pickings = pickings | pickings.backorder_ids
        all_pickings.write({
            "pos_session_id": order.session_id.id,
            "pos_order_id": order.id,
            "origin": order.name,
        })
        return pickings

    def mark_order_as_paid(self, order_id_or_ref, payment_method_id=None):
        """Second phase of checkout: money confirmed, so settle the order.

        Registers the selected payment, releases the stock and closes the bill.
        Safe to call twice: an order already paid returns its existing payment
        without creating duplicate payment or stock movements.
        """
        order = self._find_order(order_id_or_ref)

        if order.state != "draft":
            existing_payment = order.payment_ids[:1]
            return {
                "id": existing_payment.id if existing_payment else None,
                "payment_method_id": existing_payment.payment_method_id.id if existing_payment else None,
                "payment_method_name": existing_payment.payment_method_id.name if existing_payment else None,
                "amount": existing_payment.amount if existing_payment else order.amount_paid,
            }

        company = order.company_id
        payment_method = self._resolve_payment_method(
            order, payment_method_id=payment_method_id, required=False
        )

        # 1. Settle the order. Native pos.order.write() draws the receipt
        # number from the sequence here, because state flips to 'paid'.
        order.write({
            "state": "paid",
            "amount_paid": order.amount_total,
        })

        # 2. Register the chosen payment method so the POS session balances
        # and any later refund can refer to the real method used.
        payment = self.env["pos.payment"].sudo().with_company(company).create({
            "pos_order_id": order.id,
            "amount": order.amount_total,
            "payment_method_id": payment_method.id,
            "payment_date": fields.Datetime.now(),
        })

        # 3. Force real-time inventory deduction (create stock.picking).
        self._create_pos_stock_picking(order)

        # 4. Close the bill fronting this order
        bills = self.env["poskas.bill"].sudo().with_company(company).search([
            ("pos_order_id", "=", order.id)
        ])
        if bills:
            bills.write({"state": "paid"})

        return {
            "id": payment.id,
            "payment_method_id": payment_method.id,
            "payment_method_name": payment_method.name,
            "amount": payment.amount,
        }

    def refund_order(self, order_id_or_ref, payment_method_id, reason=None):
        """Fully refund the remaining refundable quantity of a paid order.

        Odoo represents a POS refund as a new negative pos.order whose lines
        point back to the original lines through refunded_orderline_id. The
        negative order is then paid with a negative pos.payment using the
        payment method selected by the caller, and its negative stock lines
        generate the return picking.

        This endpoint intentionally performs a full remaining refund. Partial
        item refunds need reward/loyalty proration rules and are kept out of
        this first API contract to avoid over-refunding discounted orders.
        """
        order = self._find_order(order_id_or_ref)

        if order.state != "paid":
            raise UserError(
                f"POS Order '{order.name}' must be in state 'paid' to be refunded; current state is '{order.state}'"
            )
        if not order.session_id or order.session_id.state != "opened":
            raise UserError(
                f"POS session '{order.session_id.name if order.session_id else '-'}' must still be open to refund this paid order"
            )
        if not order.has_refundable_lines:
            raise UserError(f"POS Order '{order.name}' has no refundable quantity remaining")

        payment_method = self._resolve_payment_method(
            order, payment_method_id=payment_method_id, required=True
        )
        company = order.company_id

        # Native Odoo refund helper copies all remaining refundable quantities
        # and links every negative line back to its original order line. It
        # initially chooses pos.config.current_session_id; below we force the
        # exact original still-open session to keep this API deterministic.
        refund_orders = order.sudo().with_company(company)._refund()
        refund_order = refund_orders[:1]
        if not refund_order or not refund_order.exists():
            raise UserError("Odoo did not create a refund order")
        if not refund_order.lines:
            raise UserError(f"POS Order '{order.name}' has no refundable lines remaining")

        # The native helper uses pos.config.current_session_id. This API is
        # intentionally stricter: for a paid-but-not-posted order we keep the
        # refund inside the exact same still-open session as the original.
        if refund_order.session_id != order.session_id:
            refund_order.write({"session_id": order.session_id.id})

        if reason and "general_note" in refund_order._fields:
            note = str(reason).strip()
            if note:
                refund_order.general_note = f"Refund reason: {note}"

        # amount_total is negative on a refund order. A negative payment means
        # money leaves the selected POS payment method.
        refund_order.add_payment({
            "name": f"Refund {order.name}",
            "pos_order_id": refund_order.id,
            "amount": refund_order.amount_total,
            "payment_method_id": payment_method.id,
            "payment_date": fields.Datetime.now(),
        })
        refund_order.action_pos_order_paid()

        # Negative POS lines create a return picking. Call the stock helper
        # directly so the return is immediate, matching this module's mark_paid
        # behaviour even when the POS config normally updates stock at closing.
        self._create_pos_stock_picking(refund_order)
        refund_order._compute_total_cost_in_real_time()

        payment = refund_order.payment_ids[:1]
        return {
            "original_order_id": order.id,
            "original_order_name": order.name,
            "refund_order_id": refund_order.id,
            "refund_order_name": refund_order.name,
            "refund_pos_reference": refund_order.pos_reference or None,
            "state": refund_order.state,
            "amount_total": refund_order.amount_total,
            "amount_paid": refund_order.amount_paid,
            "session_id": refund_order.session_id.id,
            "payment": {
                "id": payment.id if payment else None,
                "payment_method_id": payment_method.id,
                "payment_method_name": payment_method.name,
                "amount": payment.amount if payment else refund_order.amount_total,
            },
            "picking_ids": refund_order.picking_ids.ids,
            "reason": str(reason).strip() if reason else None,
        }

    def move_bill_table(self, config_pos_id, bill_id, raw_table_id):
        # 1. Lookup and validate the open bill
        bill = self.env["poskas.bill"].sudo().browse(bill_id)
        if not bill.exists():
            raise UserError("Bill not found")
        if bill.state != "open":
            raise UserError("Bill is not open")

        # POS Config Validation (Error 400): The target poskas.bill must belong to the specified config_pos_id
        if bill.config_id.id != config_pos_id:
            raise UserError(f"Bill ID {bill_id} does not belong to POS Config ID {config_pos_id}")

        company = bill.company_id

        # 2. Resolve destination table and validate
        table = False
        table_ref = ""

        if isinstance(raw_table_id, int):
            target_table = self.env["restaurant.table"].sudo().with_company(company).browse(raw_table_id)
            if target_table.exists():
                table = target_table
            else:
                # If table ID was int but table record doesn't exist, treat it as a table_ref string
                table_ref = str(raw_table_id)
        else:
            table_ref = str(raw_table_id).strip()

        # POS Config Validation (Error 400): The destination restaurant.table must belong to a floor linked to the specified config_pos_id
        if table:
            pos_config = self.env["pos.config"].sudo().with_company(company).browse(config_pos_id)
            allowed_floor_ids = pos_config.floor_ids.ids
            if table.floor_id.id not in allowed_floor_ids:
                raise UserError(f"Table '{table.table_number}' (ID {table.id}) is not configured for POS Config '{pos_config.name}'")

        # 3. Check if target table is already occupied
        domain = [
            ("config_id", "=", config_pos_id),
            ("state", "=", "open"),
            ("id", "!=", bill.id)
        ]
        if table:
            domain.append(("table_id", "=", table.id))
        else:
            domain.append(("table_ref", "=", table_ref))

        existing = self.env["poskas.bill"].sudo().with_company(company).search(domain, limit=1)
        if existing:
            raise TableOccupiedException(
                "Target table already has open bill",
                existing_bill_id=existing.id
            )

        # 4. Write new table to bill
        vals = {}
        if table:
            vals["table_id"] = table.id
            vals["table_ref"] = ""
        else:
            vals["table_id"] = False
            vals["table_ref"] = table_ref

        # Update the bill name if it matches the "Bill - Customer (Meja X)" format
        old_name = bill.name or ""
        if old_name.startswith("Bill - "):
            customer_part = old_name.split(" (Meja ")[0] if " (Meja " in old_name else old_name
            new_name = customer_part
            if table:
                new_name += f" (Meja {table.table_number})"
            elif table_ref:
                new_name += f" (Meja {table_ref})"
            vals["name"] = new_name

        bill.write(vals)

        # 5. If a pos.order is linked, write the new table to the POS order
        if bill.pos_order_id:
            bill.pos_order_id.write({
                "table_id": table.id if table else False
            })

        # 6. Return serialized bill
        return self._serialize_bill(bill)

    def _serialize_bill(self, bill):
        return {
            "id": str(bill.id),
            "name": bill.name or "",
            "table_id": str(bill.table_id.id) if bill.table_id else "",
            "name_customer": bill.name_customer or "",
            "state": bill.state or "open",
            "write_date": fields.Datetime.to_string(bill.write_date) if bill.write_date else None,
            "amount_total": bill.amount_total or 0.0,
            "is_dp": bool(bill.is_dp),
            "dp_amount": bill.dp_amount or 0.0,
            "name_waiters": bill.name_waiters,
            "amount_due": bill.amount_due or 0.0,
            "type_order": bill.type_order or "dine_in",
            "items": [
                {
                    "id": str(line.id),
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name or "",
                    "product_category": line.product_id.categ_id.name if line.product_id.categ_id else "",
                    "qty": line.qty or 0.0,
                    "price_unit": line.price_unit or 0.0,
                    "discount_percent": line.discount_percent or 0.0,
                    "note": line.note or "",
                    "subtotal": line.subtotal or 0.0,
                }
                for line in bill.line_ids
            ],
        }