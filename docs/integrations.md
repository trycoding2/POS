# Integrations — WhatsApp, Cloud Sync, Printing & Barcode

These features are implemented up to their **credential boundary**: everything
local (queues, statuses, retries, templates, idempotency) is built and tested.
You only need to supply the external service credentials below. No business
transaction ever blocks on an integration failure.

---

## 1. WhatsApp (official Business Platform / Cloud API)

**Why official only:** unofficial libraries break accounts and violate WhatsApp
ToS. This app uses Meta's Cloud API.

### What already works without any credential
- Notification center with statuses: pending → sending → sent / failed / retry / cancelled
- Templates: sale receipt, payment receipt, Khata reminder, Dasti reminder,
  low-stock & expiry alerts, daily owner summary
- Retry queue; failures surface as dashboard alerts, never blocking POS
- `wa.me` deep-link fallback: with no API configured, "Send WhatsApp" opens a
  pre-filled chat link so the cashier can send manually — clearly labelled as
  manual mode in Settings → Notifications.

### To enable automated sending
1. Create a Meta developer account → WhatsApp Business Platform app → get a
   **Phone Number ID** and permanent access token. Verify your business number.
2. Add to `backend/.env`:
   ```
   KARYANA_WHATSAPP_API_URL=https://graph.facebook.com/v20.0
   KARYANA_WHATSAPP_API_TOKEN=EAAG...
   KARYANA_WHATSAPP_PHONE_NUMBER_ID=123456789012345
   ```
3. Settings → Notifications → Test send to your own number.
4. Template messages must match approved template names for marketing/utility
   categories; transactional receipts/reminders use utility templates.

The sender worker reads these settings at runtime — restart not required after
changing them in Settings.

## 2. Cloud sync / remote backup

Local behaviour (queue, unique IDs, idempotent push, conflict status, offline
badge) is complete. To sync across shops/devices:

1. Deploy a second Karyana Manager instance as the cloud hub (PostgreSQL via
   `KARYANA_DATABASE_URL=postgresql+psycopg://…`) behind HTTPS.
2. On each shop device set:
   ```
   KARYANA_CLOUD_URL=https://cloud.example.com
   KARYANA_CLOUD_API_KEY=<per-device key issued by the hub>
   ```
3. The header sync chip turns green when the queue drains. Conflicts (same
   record edited on two devices) are marked `conflict` and listed under
   Backup & Sync → Requires attention for the owner to resolve.

## 3. Receipt printing

Receipts render as print-ready HTML (any paper width: 58 mm / 80 mm thermal, or
A4 invoice) and PDF via ReportLab (`GET /api/sales/{id}/receipt.pdf`).

- **Thermal printer:** install the OS driver (Epson TM / Xprinter / PosPal all
  work), then either use the browser print dialog from the POS (Ctrl+P sends
  straight to the default printer) or configure a raw-socket/USB CUPS queue and
  point the Tauri build's print command at it. Paper width and every receipt
  field (logo, header/footer, show-balance, cashier name…) are in
  Settings → Receipts and take effect on the next printed receipt.
- If printing fails the sale is already committed — reprint anytime from the
  sale detail page.

## 4. Barcode scanners

No configuration needed for standard USB HID scanners (the vast majority —
Zebra, Honeywell, Urovo, generic Chinese brands): they type the code + Enter,
which the POS recognises and adds qty 1 instantly. Repeated scans stack
quantity. If your scanner types slowly, raise *Scan speed threshold* in
Settings → POS. Bluetooth scanners exposing SPP serial do need a vendor SDK —
out of scope, documented honestly.

## 5. Payments / wallets

Cash, Bank, Easypaisa and JazzCash are **record-keeping accounts** (you log the
money movement; the app does not connect to bank/wallet APIs). Real-time wallet
debit requires PSP credentials and is intentionally left as a boundary — the
account model already supports adding such methods in Settings → Payments.
