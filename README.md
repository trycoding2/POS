# Karyana Manager

Complete Pakistani Karyana / General Store management system: POS, inventory, Khata,
Dasti, suppliers, purchases & orders, returns, cash/accounts, expenses, owner
withdrawals, reports, tamper-evident audit trail, notifications/WhatsApp, offline-first
local database with a cloud sync queue, backups and role/permission management.

**Golden rule:** every product, every rupee, every balance and every important action
has a traceable history. Financial transactions are never deleted — they are voided,
reversed or returned with a reason.

## Architecture

| Layer     | Tech                                             |
|-----------|--------------------------------------------------|
| Backend   | Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic    |
| Local DB  | SQLite (offline-first; PostgreSQL URL configurable) |
| Frontend  | React + TypeScript + Vite (POS-optimised UI)     |
| Desktop   | Tauri 2 wrapper (see `frontend/src-tauri` notes) |
| PDF/Excel | ReportLab / openpyxl                             |
| Tests     | Pytest (backend E2E incl. the spec business flow)|

```
backend/          FastAPI app (app/main.py wires ~110 endpoints)
  app/core/       config, security (scrypt password hashing, tokens), DB session
  app/models/     SQLAlchemy entities (auth, catalog, parties, transactions, system)
  app/services/   atomic business operations (sales, purchases, ledger, audit,
                  inventory movements, receipts, reports, backup, sync, notify…)
  app/routers/    auth, catalog, pos routers (+ main.py for the rest)
  tests/          end-to-end suite replicating the full shop-owner flow
frontend/         React SPA — Login/Setup wizard, POS, Dashboard, all modules
docs/             user & operations documentation
```

## Quick start (development)

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then set KARYANA_SECRET_KEY to a random value
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev                 # http://localhost:5173 (proxies /api to :8000)
```

First launch opens the **Setup Wizard**: store name, owner account, currency,
opening cash, payment accounts. Everything else is configured later in Settings.

## Production (single shop)

```bash
cd frontend && npm run build           # outputs dist/
# Serve dist/ with any static server (nginx/caddy) on the shop PC, proxying
# /api to the backend, OR point your browser at the backend and use Tauri:
cd frontend && npx tauri init          # once; then `npx tauri build`
```

Run the backend as a service (systemd example in `docs/operations.md`).

## Tests

```bash
cd backend && python -m pytest tests -q      # 18 E2E tests, isolated temp DB
cd frontend && npm run build                 # strict TypeScript + production build
```

## Key integration boundaries (require external credentials)

* **Cloud sync/backup** — engine, queue, idempotency and conflict statuses are fully
  implemented locally; set `KARYANA_CLOUD_URL` + `KARYANA_CLOUD_API_KEY` to activate.
* **WhatsApp** — notification center, queue, retry/fail statuses and templates work
  offline; delivery requires the official WhatsApp Business Platform credentials
  (`KARYANA_WHATSAPP_*`). Sales never block on notification failures.
* **Thermal printing** — receipts render as printable HTML/PDF; printer drivers are
  an OS-level configuration.

## Documentation

See `docs/`:

| File | Contents |
|---|---|
| `docs/users-manual.md` | Full module-by-module user guide + task cheat-sheet |
| `docs/permissions.md` | Roles, granular permission keys, approval thresholds |
| `docs/operations.md` | Backup/restore, systemd/nginx service, Windows, health checks |
| `docs/integrations.md` | WhatsApp Cloud API, cloud sync hub, thermal printing, barcode scanners |
| `docs/data-import-export.md` | CSV formats and validation rules |
| `docs/testing.md` | Pytest suite map + 5-minute manual smoke test |

## Desktop (Tauri 2)

`frontend/src-tauri/` contains the complete Tauri shell (config, Rust source that
launches/stops the bundled backend, capabilities). The sandbox used for
development has no Rust toolchain, so compile installers on any build machine:

```bash
cd frontend && npm install && npx tauri build   # see src-tauri/BUILDING.md
```
