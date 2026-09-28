# Operations — Backup, Restore, Sync & systemd

## Where data lives

Everything is inside `KARYANA_DATA_DIR` (default `backend/data/`):

```
data/
  karyana.db          the SQLite database (single source of truth)
  backups/            timestamped .db backup files (+ .meta.json per backup)
  uploads/            receipt logos, purchase attachments
```

Back up by simply copying the folder while the app is idle, or use the built-in
Backup page (`POST /api/backups`, list, restore).

## Manual cold backup (belt-and-braces)

```bash
cd backend
sqlite3 data/karyana.db ".backup '/secure/offsite/karyana-$(date +%F).db'"
```

`.backup` uses the SQLite online-backup API — safe even with the app running.
Copy off the shop PC daily (USB drive taken home, or a cloud storage client
watching the folder). Keep at least 7 daily + 4 monthly copies.

## Restore

**UI:** Backup page → pick a backup → Restore → type `RESTORE` to confirm
(owner permission required). The current DB is automatically saved as a
pre-restore safety backup first; nothing is silently overwritten.

**CLI (if the app won't start):**

```bash
cd backend
mv data/karyana.db data/karmacy-pre-restore-$(date +%F).db.bak   # keep the wreck
cp /secure/offsite/karyana-2026-09-28.db data/karyana.db
systemctl restart karyana        # or relaunch uvicorn
```

Then log in as owner and run **Verify audit chain** (Audit page) to confirm the
restored file is intact.

## Cloud sync

The sync engine runs fully offline-first: every transaction enqueues a row in
`sync_queue` with a unique ID; statuses are pending → uploading → synced /
failed / conflict. Retry is automatic with backoff; IDs make retries idempotent
so reconnecting never duplicates sales/payments.

To activate, set in `backend/.env`:

```
KARYANA_CLOUD_URL=https://your-cloud-server
KARYANA_CLOUD_API_KEY=<issued by the server>
```

and point the queue push/pull endpoints at any Karyana Manager cloud instance
(see `docs/integrations.md`). Without these, the app still records everything
locally and shows the pending count in the header — no data is lost.

## Devices

Each install identifies itself with `KARYANA_DEVICE_ID` (Settings on the device
too). Owner sees name/last-sync/last-activity per device and can **revoke** one
instantly — its tokens stop working on the next request.

## Running as a service (Linux, systemd)

`/etc/systemd/system/karyana.service`:

```ini
[Unit]
Description=Karyana Manager backend
After=network.target

[Service]
User=karyana
WorkingDirectory=/opt/karyana/backend
EnvironmentFile=/opt/karyana/backend/.env
ExecStart=/opt/karyana/backend/.venv/bin/uvicorn app.main:app \
          --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now karyana
```

Serve the built frontend (`frontend/dist/`) from nginx and proxy `/api` to
`127.0.0.1:8000`:

```nginx
location /api/ { proxy_pass http://127.0.0.1:8000; }
```

Keep both bound to localhost only — the shop PC should not expose the API to
the internet directly.

## Windows (single till PC)

Run the Tauri desktop build (it launches the bundled backend); or create a
Task Scheduler job at logon:

```
cmd /c "cd C:\karyana\backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000"
```

## Health checks

- `GET /api/health` → `{"status":"ok", ...}` (also reports sync pending count)
- Header chips show online/offline and unsynced-record counts.
- Backup failures appear as dashboard alerts and notification entries.
