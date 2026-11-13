# POS Union Econique Integration (Odoo 18)

Sends paid POS orders to the **Union Kuliner Econique** API
(`POST /api/kuliner/login`, `POST /api/kuliner/transaction`).

This module is standalone. It has its own configuration model, menu and access group,
and does **not** depend on or share data with the payment gateway modules
(`pos_payment_gateway`). Depends only on `point_of_sale` and `mail`.

## How it works

```
order paid (cashier screen or REST API)
  -> pos.order.write(state=paid)        model-level hook
  -> pos.econique.transaction (pending) queue + log
  -> cron every 5 minutes (also triggered right when the entry is created)
       -> login (token cached, logs in again on 401)
       -> POST /api/kuliner/transaction
       -> sent | retry (network, 5xx) | failed
```

- The hook is on `pos.order`, not in the POS UI. Orders paid through `rest_api_odoo`
  (`/api/pos/order/pay`) are sent too, because both write `state = paid`.
- Payment in the POS is **never** blocked or failed by this integration.
- One order = one transaction (unique `order_id`), so nothing is sent twice.
- Temporary failures are retried after 2, 4, 8 ... up to 60 minutes, until
  `Max Attempts`, then `Failed`. Validation errors (4xx) go straight to `Failed`.
- Refunds and zero-total orders are recorded as `Skipped` (the API has no refund endpoint).

## Where to configure (per POS config)

**Point of Sale > Configuration > Econique Integration** (needs the group
*Econique Integration Manager*; it implies *Point of Sale: User*). Create one record per
POS config:

| Setting | Field |
|---|---|
| POS config this applies to | **POS Config** (one active record per POS) |
| Enabled or disabled | **Auto Send** toggle, or archive the record (Action > Archive) |
| Production or staging | **Environment** (fills **Base URL**: `https://api.econique.co.id` / `https://stg-api.econique.id`; editable) |
| API login | **API Username**, **API Password** |
| Token | Not typed in. **Test Login** gets and stores it, **Clear Token** forgets it, **Token Obtained At** shows when it was last obtained. A send logs in by itself when there is no token or it returns 401. |
| Tenant | **Tenant Code**, **Tenant Name** |
| Retry and timeout | **Max Attempts**, **Timeout (seconds)** |
| Basic Auth on login | **Login with Basic Auth**, optional **Basic Auth Username/Password** (empty = same as the API login) |
| Mapping rules | **Mapping Rules** tab |
| Payment methods | **Payment Methods** tab (Odoo payment method to `payment_type` / provider / issuer) |

When a POS config has no active Econique record, or **Auto Send** is off, orders are not
queued and nothing is sent. Entries already queued stay pending while **Auto Send** is
off and continue when it is turned on again. Changes to the record are tracked in the
chatter; the API password is never written to the chatter or logs.

Monitor in **Point of Sale > Configuration > Econique Transactions** (buttons:
*Send Now*, *Reset to Pending*, *Skip*; the Request and Response tabs show exactly what
was sent and received), or through the **Transactions** button on a configuration.

## Setup

1. Install: `odoo-bin -d <db> -i pos_econique_union --stop-after-init`.
2. Add your user to the group **Econique Integration Manager**.
3. Create the configuration as described above and click **Test Login**.
4. Fill in the **Payment Methods** tab.
5. Pay a test order on staging and check **Econique Transactions**.

Orders paid before the module was installed are not sent automatically.

## Field mapping (adjustable per configuration)

| Econique field | Odoo source |
|---|---|
| `invoice_number` | `pos_reference` (or the order name) |
| `tenant_code`, `tenant_name` | configuration |
| `voucher_code` | coupon code of a reward line, otherwise `null` |
| `transaction_date`, `payment_date` | `date_order` / payment date, company time zone (default Asia/Jakarta) |
| `bruto` | sum of `price_unit * qty` of item lines |
| `discount` | percent (max 100) of line discounts + reward lines relative to bruto |
| `service_fee` | `Service Fee (%)` x (bruto - discount) |
| `ppn` | order `amount_tax` |
| `netto` | `bruto - discount - service_fee - ppn` (matches the example in the documentation) |
| `payment_type`, `payment_provider`, `payment_issuer` | payment method mapping table; without a mapping: cash = `Cash`, otherwise the method name; issuer = Default payment_issuer (`PT PHI`) |
| `payment_transactions_id` | payment `transaction_id`, then payment name, then `pos_reference` |
| `items[].product_code` | product Internal Reference / Barcode / ID |
| `items[].price_code`, `price_name` | fixed values, or the pricelist ID and name |

Reward/discount lines (negative value) are not sent as items; their value goes into
`discount`. A fractional qty is sent as 1 item worth the whole line because `amount`
is an Int. An order with more than one payment is sent with its largest payment (the
API has a single set of payment fields).

## Ambiguities in the Econique documentation (and what this module does)

- The example request uses `payment_vendor`, the field table uses `payment_issuer`:
  both are sent (can be turned off).
- Login is said to use Basic Auth without naming the credentials: a Basic header is sent
  with the API username/password (can be turned off or overridden with the Basic Auth
  fields).
- `amount` in the example item holds an amount of money, but the table defines it as the
  item quantity: the module follows the table (qty).
- `discount_nominal` per item is computed for the whole line
  (`unit_price * qty * percent`), not per unit.
- The documentation does not say how the API answers when an `invoice_number` is sent twice.

## Adjusting the rules

All payload building is in `pos.econique.transaction._build_payload()` (collects the
Odoo data) and `services/union_payload.py` (formulas, no Odoo dependency). Override
either when the Econique rules change.

## Tests

The existing tests only cover the formulas and the HTTP client (HTTP is mocked); they do
not touch order data:

```bash
odoo-bin -d <db> -u pos_econique_union --test-enable --test-tags /pos_econique_union --stop-after-init
```
