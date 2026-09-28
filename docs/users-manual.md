# Karyana Manager — User Manual

A complete management system for Pakistani karyana / general stores: POS, Khata,
Dasti, inventory, suppliers, purchases, cash accounts, expenses, returns, reports,
audit trail and offline-first cloud sync.

**Golden rule of the system:** every product, every rupee, every balance and every
important action has a traceable history. Financial records are never deleted —
they are voided, reversed or returned **with a reason**, and the original record
stays visible forever.

---

## 1. First launch — Setup Wizard

On first run the wizard asks for:

1. Store name, address, phone (used on receipts)
2. Owner account (name + strong password — this is the only full-access login)
3. Currency (default `Rs.` PKR; symbol, decimals and separators configurable later)
4. Opening cash in the main till (recorded as an audited opening transaction)
5. Default payment accounts (Main Cash, Bank, Easypaisa, JazzCash — editable)

Everything optional can be skipped and completed later in **Settings**.

## 2. Logging in

Each employee gets their own username/password (Users & Employees page).
Cashiers should NOT share the owner login — the audit log records *who* did *what*.
Failed logins are also recorded. Sessions expire; devices can be revoked by the owner.

## 3. POS / Sales (the cashier's screen)

- The search box is auto-focused. Type any part of a name, SKU, barcode or brand —
  suggestions appear instantly. Use **↑ / ↓** to move, **Enter** to select, **Esc** to clear.
- **Barcode scanner:** just scan. USB scanners act like keyboards; the product is
  added with quantity 1 immediately. Scan the same item 5 times → quantity 5.
  No popup interrupts you.
- **Manual selection:** after choosing from search results a small quantity box opens
  (configurable per settings); type the number and press Enter.
- Cart lines: click a line to change quantity, price (if permitted), discount or remove it.
- Payment buttons:
  - **Cash** — enter tendered amount, change is calculated automatically.
  - **Khata** — charge the sale to a saved customer's credit account (checks credit limit).
  - **Dasti** — temporary short-term credit for anyone (optional name/phone, due date).
  - **Bank / Wallet** — record against the chosen account.
  - **Split** — combine e.g. Rs.1,000 cash + Rs.500 Khata in one sale.
- **Hold / Resume** — park a half-entered sale (queue list) and resume it later.
- **Complete Sale** prints/offers the receipt. If printing fails the sale is still
  safely stored — reprint from the sale's detail page anytime.
- Large discounts or price changes may require a **manager PIN** (approval system).

Keyboard shortcuts (F1 search, F2 customer, F3 discount, F6 payment, F7 new sale,
F9 print …) are configurable in Settings → POS.

### What a sale changes automatically
Stock decreases (movement record), revenue posts, cash/account increases, customer
receivable increases if on credit, profit recalculates, an audit entry is written,
and the transaction is queued for cloud sync. All of this happens in **one atomic
database transaction** — it either fully succeeds or fully rolls back.

## 4. Products & Inventory

- **Products**: create/edit name, SKU, barcode, category, brand, unit, cost price,
  retail/wholesale price, min/max stock, batch & expiry tracking, supplier.
  Price changes are never overwritten silently — old price, new price, who and why
  are kept in price history.
- **Inventory dashboard**: total stock value, low stock, out of stock, expiring soon,
  expired, damaged, fast/slow/dead movers.
- **Stock adjustments** (damage, expiry, correction): require a reason and permission;
  large adjustments may need approval. Every adjustment creates a movement record.
- Open any product to see its full **traceability**: movements, price history and
  related transactions.

## 5. Customers, Khata & Dasti

- **Customers**: name, phones, address, credit limit, opening balance, WhatsApp
  preference. Profile shows current balance, totals, last purchase/payment, the
  complete ledger and timeline. Import/export via CSV (Settings → Data).
- **Khata** (long-term credit): dashboard shows total receivable, today's credit and
  collections, overdue list. Receive payments (full/partial) against a customer;
  every payment posts to cash and to the customer ledger separately. Balances are
  always derived from history: opening ± sales − payments − returns ± adjustments.
- **Dasti** (short-term credit): standalone creation or straight from POS. Shows
  amount, due date, status. Pay fully/partially, extend the due date (audited),
  send reminders. Settled Dastis keep their full history.

## 6. Suppliers & Purchases

- **Suppliers**: ledger of everything bought, paid, returned; outstanding payable is
  derived from history. Temporary/unknown sellers ("biker", market) can be used for
  quick cash purchases without creating a permanent supplier — the transaction is
  still fully recorded, and the temporary seller can be converted later.
- **Purchases**: add items with cost price, free qty, batch/expiry, supplier invoice
  no., discount; pay now (cash/bank/wallet) and the remainder becomes supplier
  payable. Receiving a purchase increases stock with movement records.
- **Purchase Orders**: draft → sent/ordered → partially received → received.
  Ordered vs received vs remaining quantities are compared on each line.
- **Supplier payments**: pay from any account; reduces payable and posts to ledger.

## 7. Returns

- **Customer return**: find the original sale, pick lines/qty, reason, restock
  condition (good/damaged), refund method (cash / reduce Khata). Creates a reversal
  record — the original sale remains.
- **Supplier return**: reference the original purchase, debit the supplier, stock
  decreases with a movement record.

## 8. Cash, Accounts & Expenses

- Accounts: Main Cash, Secondary Cash, Bank, Easypaisa, JazzCash… Each money movement
  records account, direction, amount, reason and related transaction.
- Daily **cash count / discrepancy** entries are audited.
- **Expenses**: rent, electricity, salary, transport… categories are configurable.
- **Owner withdrawals** are recorded separately (they are NOT business expenses and
  do not distort net profit).

## 9. Reports

Sales (daily/weekly/monthly/custom, by product/category/employee/customer/payment),
inventory valuation & movers, customer receivables, supplier payables, and financial
(P&L: revenue, COGS, gross profit, expenses, net profit; cash flow). Every report
supports date range, filters, sorting, print and CSV export.

## 10. Notifications / WhatsApp

The notification center queues receipts, Khata/Dasti reminders, low-stock and expiry
alerts, daily owner summaries. Statuses: pending → sending → sent / failed → retry.
If WhatsApp delivery fails (or isn't configured yet) the business transaction still
succeeds — notifications never block a sale. See `docs/integrations.md` for setup.

## 11. Users, Roles & Permissions

Roles: Owner, Manager, Cashier, Stock Manager, Purchase Manager, Accountant (plus
custom roles). Permissions are granular (can sell, max discount %, change price,
void sale, adjust stock, see profit, manage users, export data, view audit…).
Sensitive actions can additionally require manager-PIN approval with configurable
thresholds.

## 12. Audit Log & Activity Monitor

Every important action writes a hash-chained audit entry: who, when, which device,
which record, before/after values, reason, related transaction. The chain is
tamper-evident — **Verify chain** recomputes every hash and flags any alteration.
Only owners can view/export it; employees cannot erase history.

The **Activity monitor** is a live feed (sales, payments, voids, price changes…)
filterable by user/module/action/date/device.

## 13. Backup, Sync & Devices

- Local backup: automatic scheduled + **Backup Now** button; each backup records
  date, size, version, status. Restore requires owner permission and a strong
  confirmation (never silent overwrite).
- Cloud sync: every transaction gets a unique ID and enters a sync queue
  (pending/uploading/synced/failed/conflict). Sync is idempotent — reconnecting
  never duplicates a sale or payment. Works fully offline; the UI shows an
  offline badge and pending-sync count.
- Devices: each machine has a device ID/name, last sync and last activity; the
  owner can revoke a stolen/left shop device instantly.

## 14. Common tasks cheat-sheet

| Task | Where |
|---|---|
| Fast cash sale | POS → scan/search → Cash → Complete |
| Give change | POS → type tendered amount (quick-keys available) |
| Credit to regular customer | POS → Customer → Khata button |
| Temporary credit | POS → Dasti button, or Dasti page |
| Receive Khata payment | Khata → customer → Receive payment |
| Buy stock on credit | Purchases → supplier → pay part, rest becomes payable |
| Quick market purchase | Purchases → Temporary seller |
| Record damage | Inventory → Adjust → Damage + reason |
| Return from customer | Returns → new customer return |
| Pay electricity bill | Expenses → category Rent/Electricity… |
| Owner takes cash | Cash → Owner withdrawal |
| Who changed this price? | Product → Price history |
| Why is stock short? | Product → Movements |
| Void a wrong sale | Sale detail → Void (+reason, needs permission) |
