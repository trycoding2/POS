// Help / System Information (spec #19, #76): real system state + setup & integration instructions.
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';

interface SysInfo { app: string; version: string; device_id: string; offline_ready: boolean; sync_pending: number; cloud_configured: boolean; whatsapp_configured: boolean }

export default function Help() {
  const st = useStore();
  const [info, setInfo] = useState<SysInfo | null>(null);
  useEffect(() => { api.get<SysInfo>('/api/system/info').then(setInfo).catch(() => {}); }, []);

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Help &amp; System Information</h2>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))' }}>
        <div className="card">
          <b>System status</b>
          {!info ? <p className="muted">Loading…</p> : <table><tbody>
            <tr><td>Application</td><td>{info.app} v{info.version}</td></tr>
            <tr><td>This device</td><td>{info.device_id}</td></tr>
            <tr><td>Offline mode</td><td><span className="badge ok">Ready — all transactions save locally</span></td></tr>
            <tr><td>Cloud sync</td><td>{info.cloud_configured ? <span className="badge ok">Configured</span> : <span className="badge info">Not configured (local only)</span>}</td></tr>
            <tr><td>Unsynced records</td><td>{info.sync_pending}</td></tr>
            <tr><td>WhatsApp API</td><td>{info.whatsapp_configured ? <span className="badge ok">Configured</span> : <span className="badge info">Not configured</span>}</td></tr>
          </tbody></table>}
        </div>

        <div className="card">
          <b>Quick start</b>
          <ol style={{ lineHeight: 1.8 }}>
            <li>Add products under <b>Products</b> (name, cost, selling price, barcode).</li>
            <li>Record opening stock via a <b>Purchase</b> (supplier or “random seller”) or stock adjustment.</li>
            <li>Sell in <b>POS</b>: scan barcode → auto-adds ×1; search → pick → enter quantity.</li>
            <li>Credit customers get a <b>Khata</b>; one-day credit uses <b>Dasti</b>.</li>
            <li>Collect money from the customer’s Khata page or POS payment screen.</li>
            <li>Pay suppliers from <b>Suppliers → Pay</b>; watch payables on the Dashboard.</li>
            <li>Every action above is written to the <b>Audit Log</b> with who/when/device/reason.</li>
          </ol>
        </div>

        <div className="card">
          <b>Barcode scanner</b>
          <p>Any USB/HID scanner that types like a keyboard works out of the box. Keep the POS search box focused;
             a scan is detected automatically and adds the product once per scan (5 scans = qty 5). No popup interrupts the cashier.</p>
          <b>Receipt printing</b>
          <p>After each sale use <i>Print</i> (thermal 80mm via browser print) or <i>PDF</i>. Printing failure never loses the transaction —
             it stays in Sales and can be reprinted any time.</p>
        </div>

        <div className="card">
          <b>Cloud sync configuration</b>
          <p>Set these environment variables for the local server and restart:</p>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{`CLOUD_URL=https://your-server.example\nCLOUD_API_KEY=<shared secret>`}</pre>
          <p>The built-in sync engine then pushes queued changes automatically (idempotent, UUID-keyed — retries never duplicate sales).</p>
          <b>WhatsApp reminders</b>
          <p>Configure a WhatsApp Business API endpoint (official Cloud API or a gateway such as 360dialog/Twilio):</p>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{`WHATSAPP_API_URL=https://graph.facebook.com/v20.0/<phone_number_id>/messages\nWHATSAPP_API_TOKEN=<permanent token>`}</pre>
          <p>Until credentials are set, reminder buttons queue messages and clearly report that the service is not configured — nothing is faked.</p>
        </div>

        <div className="card">
          <b>Security model</b>
          <ul style={{ lineHeight: 1.7 }}>
            <li>Passwords are hashed (bcrypt) — never stored in plain text.</li>
            <li>Permissions are enforced on the server for every request; UI hiding is cosmetic only.</li>
            <li>Audit log is append-only and hash-chained — tampering is detectable (“Verify integrity chain”).</li>
            <li>Important records are never deleted: void/cancel/reversal records keep the full story.</li>
            <li>Devices can be revoked remotely by the owner; revoked devices are blocked instantly.</li>
          </ul>
        </div>

        <div className="card">
          <b>Backup &amp; restore</b>
          <p>Use <b>Backup &amp; Sync → Backup now</b> (also automatic daily if enabled in Settings). Backups store a SHA-256 checksum; verify before restoring.
             Restore requires typing RESTORE and keeps a pre-restore safety copy automatically.</p>
          <p className="muted">Need more? Ask the owner to open Settings — currency, language, receipts, Dasti, low-stock alerts and shortcuts are all live settings.</p>
        </div>
      </div>
    </div>
  );
}
