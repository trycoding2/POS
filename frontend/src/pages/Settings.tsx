// Settings (spec #32/#45): shop profile, WhatsApp templates, backup/restore, reset data.
import React, { useEffect, useState } from 'react';
import { api, deviceId } from '../api/client';
import { useStore } from '../store';

export default function Settings() {
  const st = useStore();
  const [settings, setSettings] = useState<Record<string, string>>({ ...st.settings });
  const [busy, setBusy] = useState('');
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setSettings(p => ({ ...p, [k]: e.target.value }));
  const save = async () => {
    try { await api.put('/api/settings', settings); st.toast('Settings saved', 'ok'); st.load?.(); window.location.reload(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const download = async (kind: 'backup' | 'full-export') => {
    setBusy(kind);
    try {
      const blob = await api.get<Blob>(`/api/system/${kind}?device_id=${deviceId}`);
      const url = URL.createObjectURL(blob as any); const a = document.createElement('a');
      a.href = url; a.download = `kirana-${kind}-${new Date().toISOString().slice(0, 10)}.json`; a.click(); URL.revokeObjectURL(url);
      st.toast(`${kind} downloaded`, 'ok');
    } catch (e: any) { st.toast(e.message, 'bad'); }
    setBusy('');
  };
  const restore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    if (!confirm('Restoring will REPLACE all current data on this device with the backup. Continue?')) return;
    setBusy('restore');
    try {
      const text = await file.text();
      const r = await api.post<any>('/api/system/restore', JSON.parse(text), { 'X-Confirm-Restore': 'yes' });
      st.toast(`Restored ${r.restored ?? 'all'} records — reloading`, 'ok'); setTimeout(() => location.reload(), 800);
    } catch (err: any) { st.toast(err.message, 'bad'); }
    setBusy('');
  };
  const wipe = async () => {
    if (!confirm('DANGER: This deletes ALL sales, purchases, khata, products and settings on this device. Products/suppliers/customers are archived to an export first. Are you sure?')) return;
    if (!confirm('Really sure? This cannot be undone.')) return;
    setBusy('wipe');
    try { await api.post('/api/system/reset-data', {}, { 'X-Confirm-Reset': 'yes' }); st.toast('All transactional data cleared', 'ok'); setTimeout(() => location.reload(), 800); }
    catch (e: any) { st.toast(e.message, 'bad'); }
    setBusy('');
  };
  const s = (k: string, d = '') => settings[k] ?? st.settings[k] ?? d;
  return <div style={{ maxWidth: 760 }}>
    <h2 style={{ marginTop: 0 }}>Settings</h2>
    <div className="card">
      <h3>Shop</h3>
      <div className="row" style={{ gap: 10 }}>
        <div style={{ flex: 2 }}><label>Shop name</label><input value={s('shop.name')} onChange={set('shop.name')} /></div>
        <div style={{ flex: 1 }}><label>Currency symbol</label><input value={s('currency.symbol', 'Rs')} onChange={set('currency.symbol')} /></div>
      </div>
      <div className="row" style={{ gap: 10 }}>
        <div style={{ flex: 1 }}><label>Phone</label><input value={s('shop.phone')} onChange={set('shop.phone')} /></div>
        <div style={{ flex: 2 }}><label>Address</label><input value={s('shop.address')} onChange={set('shop.address')} /></div>
      </div>
    </div>
    <div className="card">
      <h3>WhatsApp templates {'{customer}, {amount}, {balance}, {due_date}, {shop}'}</h3>
      <label>Sale receipt</label><input value={s('wa.tpl.sale')} onChange={set('wa.tpl.sale')} />
      <label>Dasti reminder</label><input value={s('wa.tpl.dasti_reminder')} onChange={set('wa.tpl.dasti_reminder')} />
      <label>Khata balance reminder</label><input value={s('wa.tpl.khata_reminder')} onChange={set('wa.tpl.khata_reminder')} />
      <label>Supplier order received</label><input value={s('wa.tpl.order_received')} onChange={set('wa.tpl.order_received')} />
    </div>
    <div className="row spread"><p className="muted">Changes apply after saving.</p><button className="primary" onClick={save}>Save settings</button></div>
    <div className="card">
      <h3>Data safety (spec #45)</h3>
      <p className="muted">Backups are full JSON snapshots stored locally; “full export” is a human-readable dump for spreadsheets. Restore replaces everything on this device.</p>
      <div className="row">
        <button disabled={!!busy} onClick={() => download('backup')}>{busy === 'backup' ? '…' : '⬇ Download backup'}</button>
        <button disabled={!!busy} onClick={() => download('full-export')}>{busy === 'full-export' ? '…' : '⬇ Full export'}</button>
        <label className="buttonlike" disabled={!!busy}>⬆ Restore from backup<input type="file" accept=".json" hidden onChange={restore} disabled={!!busy} /></label>
        <span style={{ flex: 1 }} />
        <button className="danger" disabled={!!busy} onClick={wipe}>{busy === 'wipe' ? '…' : 'Reset all data'}</button>
      </div>
    </div>
  </div>;
}
