# FOOM Sales Dashboard

Sales analytics dashboard for **Odoo 18.0**. Shows the rhythm of sales from the
hour level up to the year, for both order count and revenue.

![menu](static/description/icon.png)

## What the dashboard shows

| Section | Content |
|---|---|
| KPI cards | Total revenue, order count, average per order, unique customers, quantity sold, peak hour — each with growth against the preceding period |
| Hour × weekday heatmap | A 7 × 24 grid; toggle between order count and revenue; hover reveals exact figures |
| Revenue trend | Line chart by hour / day / week / month / year (chosen automatically from the period length) |
| Order count trend | Bar chart on its own axis — deliberately a separate chart, not a dual axis |
| Hourly profile | All 24 hours accumulated across the period |
| Rankings | Top products, top warehouses, top locations, top customers — each row clicks through to the underlying records |
| Raw data | List / pivot / graph views for deeper analysis and export |

## Installation

1. Extract the `foom_sales_dashboard/` folder into one of your Odoo addons paths,
   for example:

   ```
   /opt/odoo/custom_addons/foom_sales_dashboard
   ```

2. Restart the Odoo service, then go to **Apps → Update Apps List**.
3. Search for "FOOM Sales Dashboard" and click Install.

Or from the command line:

```bash
odoo-bin -d <database> -i foom_sales_dashboard --stop-after-init
```

To upgrade after a code change:

```bash
odoo-bin -d <database> -u foom_sales_dashboard --stop-after-init
```

The menu appears as **FOOM Sales** in the main menu.

## Data source

The dashboard reads **posted customer invoices and credit notes**
(`account.move` with `move_type` `out_invoice` / `out_refund` and `state = posted`)
through the read-only SQL view `foom_sales_report`. No core Odoo model is
inherited, so the risk of clashing with other addons is minimal.

Things worth knowing:

- **Revenue** uses `-account_move_line.balance`, the untaxed amount in the company
  currency. Odoo has already converted it, so multi-currency sales can be summed
  directly.
- **Credit notes are automatically negative**, so returns reduce revenue and quantity.
- **Order count** is `COUNT(DISTINCT move_id)` — one invoice with ten lines is still
  one order.
- Only product lines are counted (`display_type = 'product'`); section, note, tax
  and payment-term lines are ignored.
- Warehouse and source location come from the delivery stock moves — see below.

### Transaction time — please read this

Odoo's `invoice_date` is a Date field and carries no time of day. So the
"when are we busy" analysis uses a `date_ts` column resolved in this order:

1. `sale_order.date_order` — the date and time of the Sales Order behind that
   invoice line. This is the real transaction time.
2. `account_move.create_date` — when the invoice record was created, used only
   when the line is not linked to any Sales Order.

Which means: **if your invoices are created manually without a Sales Order, and
created in a batch at the end of the day, the heatmap will pile up at the batch
hour rather than the actual selling hours.** If that describes your instance,
replace the `COALESCE(...)` expression in `models/foom_sales_report.py`
(method `_select_clause`) with whichever datetime column really records the
transaction time.

All hour and weekday aggregation is converted from UTC to the timezone of the
logged-in Odoo user (`Preferences → Timezone`). Users without a timezone are
treated as UTC.

### Outlets = warehouse and source location

Outlets are separated by warehouse and stock location, so both come from the
delivery that **actually happened**, not from the warehouse chosen on the Sales
Order:

```
invoice line → sale order line → stock.move (state = 'done')
                                   → location_id      (source location)
                                   → picking_type_id → warehouse_id
```

Two consequences worth knowing:

- **Split deliveries.** One invoice line can be fulfilled by several deliveries.
  A report row has to stay one row or revenue would be double counted, so the
  **first** delivery wins. If an order ships from two locations, the second one
  is not represented.
- **"No Warehouse" / "No Location"** groups every line with no completed
  delivery behind it: service products, manual invoices with no sales order, and
  goods invoiced before they were shipped. A large bucket here is a signal, not
  a bug — check whether those invoices really bypass the stock flow.

The `team_id` (Sales Team) column is still in the SQL view and available in the
Raw data view for manual pivots, but it no longer drives any dashboard filter or
ranking. Its column existence is checked against `information_schema` when the
view is created, so instances whose `account.move` has no `team_id` still work.

## Access rights

| Group | Grants |
|---|---|
| FOOM Sales Dashboard / User | Open the dashboard and read sales data |
| FOOM Sales Dashboard / Manager | Same, reserved for future configuration |

Members of *Sales / User* and *Sales / Administrator* receive this group
automatically. The model is read-only (`1,0,0,0`) because it is an SQL view. A
global record rule restricts rows to the user's active companies.

## Module layout

```
foom_sales_dashboard/
├── __manifest__.py
├── models/foom_sales_report.py     SQL view + all dashboard aggregation
├── security/                       groups, access rights, multi-company rule
├── views/                          list/pivot/graph/search, client action, menus
├── static/lib/chartjs/             Chart.js 4.4.7 UMD (bundled in the module)
├── static/src/js/dashboard.js      OWL components
├── static/src/xml/dashboard.xml    OWL templates
├── static/src/scss/dashboard.scss  colour tokens and layout
├── tests/                          unit tests
└── .spec/features/sales-dashboard/ requirements, design, tasks
```

Chart.js is deliberately bundled inside the module rather than pulled from Odoo's
internal lib folder, because that path changes between Odoo versions.

## Performance notes

Every figure is computed as an SQL aggregation — no record iteration in Python —
and one dashboard refresh is one RPC call. For databases with millions of journal
lines, this index helps:

```sql
CREATE INDEX IF NOT EXISTS account_move_line_foom_idx
    ON account_move_line (move_id, display_type)
    WHERE display_type = 'product';
```

## Testing

```bash
odoo-bin -d <database> -u foom_sales_dashboard --test-enable --stop-after-init
# or
pytest -s --odoo-database=<database> --odoo-log-level=warn \
       addons/foom_sales_dashboard/tests
```

## Language

The UI source strings are English. To ship another language, run Odoo's
translation export on this module and translate the resulting `.po` file.
Code comments are written in Indonesian.

## License

LGPL-3.
