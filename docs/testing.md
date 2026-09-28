# Testing Guide

## Backend (pytest) — unit + full end-to-end business flow

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests -q
```

Current suite: **18 tests, all passing**, each run against an isolated temp
SQLite DB (see `tests/conftest.py`), covering the spec's acceptance scenarios:

| Area | What is verified |
|---|---|
| Setup/auth | wizard, login, failed-login audit, token auth, device binding |
| Spec §63 flow | product → supplier purchase (part-paid) → cash sale → Khata sale → Dasti → customer payment → damage adjustment → supplier payment, with every balance checked numerically |
| POS | cash w/ change, credit, partial, split payments, hold/resume, void+reason, discounts & approval, barcode lookup |
| Inventory | movement chain reconciles to current stock; low-stock/expiry alerts |
| Ledger | balances derived from history only (opening ± sales − payments − returns ± adjustments) |
| Finance | accounts in/out, expenses vs owner withdrawals, P&L figures |
| Audit | hash-chain integrity + tamper detection (`verify_chain`) |
| Sync | queue enqueue on every transaction, idempotent push (no duplicates), conflict status |
| RBAC | permission enforcement server-side per role |
| Returns | customer & supplier return reversals keep originals |
| Backup | create/list/restore round-trip |

Frontend build/type-check acts as the UI compile gate:

```bash
cd frontend && npm install && npm run build   # strict tsc + Vite production build
```

## Manual smoke test (5 minutes)

1. Start backend + frontend dev servers → complete Setup Wizard.
2. Create one product (cost 350 / sell 400 / min 10). Scan its barcode twice →
   cart shows ×2 with no popup. ✓ scan behaviour
3. Cash sale Rs.800 tendered 1000 → change 200; check Dashboard cash +800. ✓
4. New customer "Ahmed"; Khata sale; Ahmed pays part; Khata page shows both lines. ✓
5. POS → Dasti button; Dasti page shows it pending; settle it. ✓
6. Purchases → temporary seller cash purchase; stock rises. ✓
7. Inventory → adjust Damage −1 with reason; product movements show it. ✓
8. Reports → Daily Sales + P&L match the numbers above; Export CSV opens in Excel. ✓
9. Audit → search the sale ref; Verify chain = OK. Void a sale with reason; original stays. ✓
10. Settings → change currency symbol to "PKR "; receipts and POS update live. ✓

## Playwright (optional E2E UI)

Not wired in this offline environment; skeleton steps are listed in
`docs/users-manual.md` §14 cheat-sheet which mirrors the manual smoke test.
To add later: `npm i -D @playwright/test`, point `baseURL` at the Vite dev
server, script steps 2–5 above.

## Duplicate-prevention check

Create a sale while `KARYANA_CLOUD_URL` is unset (queue grows), then set it and
trigger sync twice — the record must appear on the hub exactly once (unique
client-generated IDs make retries idempotent). Covered by the sync tests.
