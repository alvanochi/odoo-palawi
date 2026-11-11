# Sales Dashboard

Sales analytics dashboard for **Odoo 18.0**, built on Point of Sale orders. Shows
the rhythm of sales from the hour level up to the year, for order count, revenue
and sales tax.

## What the dashboard shows

| Section | Content |
|---|---|
| KPI cards | Total revenue, sales tax, order count, average per order, unique customers, quantity sold, peak hour — each with growth against the preceding period |
| Hour × weekday heatmap | A 7 × 24 grid; toggle between order count and revenue |
| Revenue trend | Line chart by hour / day / week / month / year (automatic from period length) |
| Order count trend | Bar chart on its own axis |
| Hourly profile | All 24 hours accumulated across the period |
| Sales tax by type | Tax total per tax (for example PNBP, PBJT), recomputed with `compute_all` |
| Rankings | Top products and top customers, each row opens the underlying records |
| Raw data | List / pivot / graph views for analysis and export |

Filters: date range (presets or custom), granularity, company and outlet.

## Installation

```bash
odoo-bin -d <database> -i sales_dashboard --stop-after-init   # install
odoo-bin -d <database> -u sales_dashboard --stop-after-init   # upgrade
```

Depends on `account` and `point_of_sale`. The menu appears as **Sales Dashboard**.

### Renaming from the old module name

If the database still has the previous technical name installed, rename it before
upgrading (back up first). If Odoo already created an empty `sales_dashboard`
module record, delete that one first:

```sql
UPDATE ir_module_module SET name = 'sales_dashboard' WHERE name = 'foom_sales_dashboard';
UPDATE ir_model_data    SET module = 'sales_dashboard' WHERE module = 'foom_sales_dashboard';
```

## Data source

The model `sales.report` is a read-only SQL view over `pos.order.line`.

- Orders in state **paid**, **done** or **invoiced** are counted.
- **Outlet** is the POS config of the order's session (`pos.session.config_id`).
- **Transaction time** is `pos.order.date_order`, converted to the timezone of
  the user for hour and weekday aggregation.
- **Revenue** is `price_subtotal` (untaxed). **Sales tax** is
  `price_subtotal_incl - price_subtotal`. Refund orders are negative.
- **Order count** is `COUNT(DISTINCT order_id)`.
- **Tax by type**: lines are grouped by their combination of taxes in SQL, then
  each group is recomputed with `account.tax.compute_all` so compound taxes are
  split per tax. It can differ from the KPI by rounding.

## Access

Groups *Sales Dashboard / User* and *Manager*. POS users and POS managers get them
automatically. Multi-company is enforced with a record rule.

## Testing

```bash
odoo-bin -d <database> -u sales_dashboard --test-enable --test-tags /sales_dashboard --stop-after-init
```
