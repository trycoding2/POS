// Backup & Sync (spec #43-#47): local backups, restore with strong confirmation, sync queue, devices.
import React, { useEffect, useState } from 'react';
import { api, fmtDate } from '../api/client';
import { useStore } from '../store';
import { Field, Kpi, Modal, StatusBadge, useConfirm } from '../components/ui';

interface BackupRow { id: number; file_path: string; size_bytes: number; sha256?: string; kind: string; status: string; created_at?: string }
interface SyncStatus { pending: number; failed: number; conflicts: number; cloud_configured: boolean; recent: any[] }
interface Device { id: number; device_id: string; name: string; authorized: boolean; last_sync?: string | null; last_activity?: string | null }

export default function Backup() {
  const st = useStore();
  const [backups, setBackups] = useState<BackupRow[]>([]);
  const [sync, setSync] = useState<SyncStatus | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState<BackupRow | null>(null);
  const [confirmFn, confirmNode] = useConfirm();

  const load = () => {
    api.get<BackupRow[]>('/api/backups').then(setBackups).catch(() => {});
    api.get<SyncStatus>('/api/sync/status').then(setSync).catch(() => {});
    if (st.can('users.manage')) api.get<Device[]>('/api/devices').then(setDevices).catch(() => {});
  };
  useEffect(load, []); // eslint-disable-line

  const doBackup = async () => {
    setBusy(true);
    try { const r = await api.post<BackupRow>('/api/backups/create'); st.toast(`Backup created (${Math.round((r.size_bytes ?? 0) / 1024)} KB, sha ${String(r.sha256).slice(0, 8)}…).`, 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
    setBusy(false);
  };

  const doSync = async () => {
    setBusy(true);
    try { const r: any = await api.post('/api/sync/run'); st.toast(r?.message || `Sync run: ${JSON.stringify(r?.result ?? r)}`, 'info'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
    setBusy(false);
  };

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Backup &amp; Sync</h2>
      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Unsynced records" value={sync?.pending ?? '—'} />
        <Kpi label="Sync failures" value={sync?.failed ?? '—'} tone={(sync?.failed ?? 0) > 0 ? 'var(--danger)' : undefined} />
        <Kpi label="Conflicts" value={sync?.conflicts ?? '—'} tone={(sync?.conflicts ?? 0) > 0 ? 'var(--danger)' : undefined} />
        <Kpi label="Cloud" value={sync?.cloud_configured ? 'Configured' : 'Local only'} />
      </div>
      <p className="muted" style={{ fontSize: 13 }}>
        The application is offline-first: every transaction saves locally first and never depends on internet.
        Cloud sync activates automatically once <code>CLOUD_URL</code> and <code>CLOUD_API_KEY</code> are configured in the environment —
        until then data stays on this device plus encrypted local backups below. Sync is idempotent (UUID-keyed) so retries never duplicate records.
      </p>

      <div className="row spread"><b>Local backups</b>
        <div className="row">
          <button onClick={doSync} disabled={busy}>Run sync now</button>
          <button className="primary" onClick={doBackup} disabled={busy}>Backup now</button>
        </div>
      </div>
      <table>
        <thead><tr><th>When</th><th>File</th><th className="right">Size</th><th>Status</th><th></th></tr></thead>
        <tbody>{backups.map(b => (
          <tr key={b.id}>
            <td className="muted">{fmtDate(b.created_at)}</td>
            <td>{String(b.file_path).split('/').pop()}</td>
            <td className="right">{Math.round((b.size_bytes ?? 0) / 1024)} KB</td>
            <td><StatusBadge s={b.status} /></td>
            <td className="right">
              <a href={`/api/backups/${b.id}/download`} className="btnlink">Download</a>{' '}
              <button onClick={async () => {
                try { const v = await api.get<any>(`/api/backups/${b.id}/verify`); st.toast(v.ok || v.valid ? '✔ Backup checksum verified.' : '✖ Checksum mismatch!', v.ok || v.valid ? 'ok' : 'bad'); }
                catch (e: any) { st.toast(e.message, 'bad'); }
              }}>Verify</button>{' '}
              <button className="danger" onClick={() => setRestoring(b)}>Restore</button>
            </td>
          </tr>
        ))}{!backups.length && <tr><td colSpan={5} className="muted">No backups yet — click “Backup now”.</td></tr>}</tbody>
      </table>

      {devices.length > 0 && <>
        <div className="row spread" style={{ marginTop: 18 }}><b>Devices</b></div>
        <table>
          <thead><tr><th>Device ID</th><th>Name</th><th>Status</th><th>Last activity</th><th></th></tr></thead>
          <tbody>{devices.map(d => (
            <tr key={d.id}>
              <td>{d.device_id}</td><td>{d.name}</td>
              <td><StatusBadge s={d.authorized ? 'active' : 'revoked'} /></td>
              <td className="muted">{fmtDate(d.last_activity)}</td>
              <td className="right">{d.authorized
                ? <button className="danger" onClick={async () => {
                    if (!await confirmFn(`Revoke ${d.device_id}? Its sessions will be blocked immediately.`)) return;
                    try { await api.post(`/api/devices/${d.id}/revoke`); st.toast('Device revoked.', 'ok'); load(); } catch (e: any) { st.toast(e.message, 'bad'); }
                  }}>Revoke</button>
                : <button onClick={async () => { try { await api.post(`/api/devices/${d.id}/restore`); load(); } catch (e: any) { st.toast(e.message, 'bad'); } }}>Re-authorize</button>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </>}

      {sync && sync.recent?.length > 0 && <>
        <div className="row spread" style={{ marginTop: 18 }}><b>Recent sync queue</b></div>
        <table>
          <thead><tr><th>Entity</th><th>Status</th><th>Retries</th><th>Error</th><th>Created</th></tr></thead>
          <tbody>{sync.recent.slice(0, 15).map((r: any) => (
            <tr key={r.id}><td>{r.entity_type}</td><td><StatusBadge s={r.status} /></td><td>{r.retries}</td>
              <td className="muted">{r.error || ''}</td><td className="muted">{fmtDate(r.created_at)}</td></tr>
          ))}</tbody>
        </table>
      </>}

      {restoring && <RestoreModal backup={restoring} onClose={() => setRestoring(null)} onDone={() => { setRestoring(null); load(); }} />}
      {confirmNode}
    </div>
  );
}

function RestoreModal({ backup, onClose, onDone }: { backup: BackupRow; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const doIt = async () => {
    setBusy(true);
    try {
      const r: any = await api.post(`/api/backups/${backup.id}/restore`, { confirm_text: text });
      st.toast(r?.message || 'Restore complete — restart the app to be safe.', 'ok');
      onDone();
    } catch (e: any) { st.toast(e.message, e.committed ? 'warn' as any : 'bad'); }
    setBusy(false);
  };
  return (
    <Modal title="Restore from backup" onClose={onClose} width={460}>
      <p><b>Warning:</b> restoring replaces ALL current data with the backup from {fmtDate(backup.created_at)}.</p>
      <p className="muted">Type <code>RESTORE</code> exactly to enable the button (spec #47 — never silently overwrite).</p>
      <Field label="Confirmation"><input autoFocus value={text} onChange={e => setText(e.target.value)} /></Field>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={onClose}>Cancel</button>
        <button className="danger" disabled={text !== 'RESTORE' || busy} onClick={doIt}>{busy ? 'Restoring…' : 'Restore now'}</button>
      </div>
    </Modal>
  );
}
