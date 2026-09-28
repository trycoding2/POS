# Permissions & Roles Reference

Permissions are stored per **role** (granular flags) and assigned to users via
their role. The backend enforces every permission server-side on each API call —
the frontend merely hides what a user can't do; hiding is never the security
boundary. Owners always have full access.

## Default roles

| Role | Intent |
|---|---|
| Owner | Everything, including users, settings, audit, restore, device revoke |
| Manager | Day-to-day operations + approved financial actions |
| Cashier | Selling, customers, payments received — nothing destructive |
| Stock Manager | Products, receiving, adjustments, counts |
| Purchase Manager | Suppliers, purchases, orders, supplier payments |
| Accountant | Reports, expenses, accounts, exports |

## Permission keys (Settings → Permissions editor)

### Sales & POS
- `sale.create` — complete sales in POS
- `sale.discount` — apply line/order discounts (see `max_discount_percent` below)
- `sale.change_price` — override selling price on a cart line
- `sale.void` — void a completed sale (requires reason; original kept)
- `sale.return` — process customer returns
- `sale.hold` — hold/resume carts

### Credit
- `khata.create` — make Khata (credit) sales
- `khata.payment` — receive customer payments
- `khata.adjust` — ledger adjustments (sensitive; approval-gated)
- `dasti.create` / `dasti.settle` — temporary credit lifecycle
- `customer.create` — add customers

### Inventory
- `product.view` / `product.manage` — catalog CRUD
- `stock.adjust` — manual movements (damage/expiry/correction; reason mandatory)
- `purchase.create` / `purchase.receive` — purchase lifecycle
- `order.manage` — purchase orders
- `supplier.create` — add suppliers
- `supplier.payment` — pay suppliers
- `supplier.return` — return goods to supplier

### Finance
- `expense.create` — record expenses
- `cash.manage` — account transfers, cash counts, owner withdrawals
- `finance.see_profit` — margin/profit columns in products & reports
- `finance.see_supplier_balances`
- `finance.see_customer_balances`

### Administration
- `user.manage` — create/edit users & roles
- `settings.manage` — change any store setting
- `data.export` — CSV exports (incl. audit where permitted)
- `audit.view` — read the audit log / activity feed
- `backup.manage` — run backups, list/restore them
- `device.manage` — authorize/revoke devices
- `notify.send` — trigger WhatsApp/notification sends manually

### Extra discount limit
Each role also carries `max_discount_percent` (0–100). Discounts beyond the
role's limit require manager-PIN approval regardless of other permissions.

## Approval thresholds (Settings → Approvals)

Actions matching these rules prompt for a manager PIN even when the acting
user technically has the permission:

- Discount % above the cashier's role limit
- Sale void / cancellation
- Stock adjustment whose value exceeds the configured amount
- Expense above threshold
- Supplier payment above threshold
- Customer balance adjustment
- Selling-price change above % move
- Manual cash adjustment

Every approval is itself an audit entry (requester, approver, action, reason).

## Data privacy mapping

Cashiers without `finance.see_customer_balances` see no balances; supplier
financials require `finance.see_supplier_balances`. Phone numbers and addresses
are only returned by endpoints the role can reach.
