// Owner admin surfaces: devices, activity feed, backup center, sync status, CSV import/export (spec #31/#32/#45).
import React, { useEffect, useRef, useState } from 'react';
import { api, deviceId } from '../api/client';
import { useStore } from '../store';
import { Field, Modal, StatusBadge, useConfirm } from '../components/ui';

export default function Admin() {
  const st = useStore();
  const [tab, setTab] = useState<'devices' | 'activity' | 'backup' | 'data'>('devices');
  return <div>
    <h2 style={{ marginTop: 0 }}>Admin</h2>
    <div className="row" style={{ marginBottom: 12 }}>
      {(['devices', 'activity', 'backup', 'data'] as const).map(t =>
        <button key={t} className={tab === t ? 'primary' : ''} onClick={() => setTab(t)}>{t}</button>)}
    </div>
    {tab === 'devices' && <Devices />}
    {tab === 'activity' && <Activity />}
    {tab === 'backup' && <Backups />}
    {tab === 'data' && <DataIO />}
  </div>;
}

function Devices() {
  const st = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const load = () => api.get<any[]>('/api/devices').then(setRows).catch(e => st.toast(e.message, 'bad'));
  useEffect(() => { load(); }, []);
  const act = async (id: number, op: 'revoke' | 'restore') => {
    try { await api.post(`/api/devices/${id}/${op}`); st.toast(`Device ${op}d`, 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
    <p className="muted" style={{ padding: '0 12px' }}>Every login registers a device here. Revoking forces that device to sign out immediately (spec #45).</p>
    <table><thead><tr><th>Name</th><th>Last seen</th><th>Status</th><th></th></tr></thead>
      <tbody>{rows.map(d => <tr key={d.id}><td>{d.name}{d.device_id === deviceId ? <span className="badge info"> this device</span> : null}</td>
        <td className="muted">{d.last_seen ? new Date(d.last_seen).toLocaleString() : '—'}</td>
        <td><StatusBadge s={d.revoked ? 'revoked' : 'active'} /></td>
        <td>{d.revoked ? <button onClick={() => act(d.id, 'restore')}>Restore</button> : <button className="danger" onClick={() => act(d.id, 'revoke')}>Revoke</button>}</td></tr>)}</tbody></table>
  </div>;
}

function Activity() {
  const st = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const [scope, setScope] = useState<'mine' | 'all'>('all');
  useEffect(() => {
    api.get<any[]>(`/api/activity${scope === 'mine' ? '?user_id=' + (st.user?.id ?? 0) : ''}`).then(setRows).catch(e => st.toast(e.message, 'bad'));
  }, [scope, st.user?.id]);
  return <div>
    <div className="row" style={{ marginBottom: 8 }}>
      <button className={scope === 'all' ? 'primary' : ''} onClick={() => setScope('all')} disabled={!st.can('audit.view')}>All staff</button>
      <button className={scope === 'mine' ? 'primary' : ''} onClick={() => setScope('mine')}>My activity</button>
    </div>
    <div className="card"><table><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>
      <tbody>{rows.map((a, i) => <tr key={i}><td className="muted">{new Date(a.at).toLocaleString()}</td>
        <td>{a.user}</td><td>{a.text ?? a.action} {a.entity ? `· ${a.entity}` : ''} {a.entity_ref ? `(${a.entity_ref})` : ''}</td></tr>)}</tbody></table></div>
  </div>;
}

function Backups() {
  const st = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const [busy, setBusy] = useState('');
  const [confirm, confirmNode] = useConfirm();
  const load = () => api.get<any[]>('/api/backups').then(setRows).catch(e => st.toast(e.message, 'bad'));
  useEffect(() => { load(); }, []);
  const create = async () => { setBusy('create'); try { await api.post('/api/backups/create'); st.toast('Backup created & verified', 'ok'); load(); } catch (e: any) { st.toast(e.message, 'bad'); } setBusy(''); };
  const verify = async (id: number) => { try { const r = await api.get<any>(`/api/backups/${id}/verify`); st.toast(r.ok ? `Backup ${id} integrity OK (sha256 match)` : `Backup ${id} FAILED verification!`, r.ok ? 'ok' : 'bad'); } catch (e: any) { st.toast(e.message, 'bad'); } };
  const download = async (id: number) => {
    try { const blob = await api.get<Blob>(`/api/backups/${id}/download`); const url = URL.createObjectURL(blob as any);
      const a = document.createElement('a'); a.href = url; a.download = `kirana-backup-${id}.db`; a.click(); URL.revokeObjectURL(url); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const restore = async (id: number) => {
    if (!await confirm(`Restore backup #${id}? This REPLACES the current database on this device.`)) return;
    setBusy('restore');
    try { await api.post(`/api/backups/${id}/restore`, { confirm_text: 'RESTORE' }); st.toast('Restored — reloading', 'ok'); setTimeout(() => location.reload(), 900); }
    catch (e: any) { st.toast(e.message, 'bad'); }
    setBusy('');
  };
  return <div>
    <div className="row spread" style={{ marginBottom: 10 }}>
      <p className="muted">Local SQLite backups with sha256 integrity checks. Automatic hourly backup is controlled in Settings → Backup.</p>
      <button className="primary" disabled={!!busy} onClick={create}>{busy === 'create' ? 'Creating…' : '+ Create backup now'}</button>
    </div>
    <div className="card" style={{ padding: 0 }}>
      <table><thead><tr><th>#</th><th>When</th><th>Kind</th><th>Size</th><th>Status</th><th></th></tr></thead>
        <tbody>{rows.map(b => <tr key={b.id}><td>{b.id}</td><td className="muted">{b.created_at ? new Date(b.created_at).toLocaleString() : '—'}</td>
          <td>{b.kind}</td><td>{Math.round((b.size_bytes || 0) / 1024)} KB</td><td><StatusBadge s={b.status || 'completed'} /></td>
          <td className="row"><button onClick={() => verify(b.id)}>Verify</button><button onClick={() => download(b.id)}>Download</button>
            <button className="danger" disabled={!!busy} onClick={() => restore(b.id)}>Restore</button></td></tr>)}</tbody></table>
    </div>
    {confirmNode}
  </div>;
}

function DataIO() {
  const st = useStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const [what, setWhat] = useState<'products' | 'customers'>('products');
  const exportCsv = async (kind: 'products' | 'customers' | 'suppliers') => {
    try { const blob = await api.get<Blob>(`/api/export/${kind}`); const url = URL.createObjectURL(blob as any);
      const a = document.createElement('a'); a.href = url; a.download = `${kind}.csv`; a.click(); URL.revokeObjectURL(url); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const doImport = async (file: File) => {
    const fd = new FormData(); fd.append('file', file);
    try {
      const headers: Record<string, string> = {};
      const tok = localStorage.getItem('km_token'); if (tok) headers.Authorization = 'Bearer ' + tok;
      const res = await fetch(((import.meta.env.VITE_API_URL as string) || '') + `/api/import/${what}`, { method: 'POST', headers, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Import failed.');
      st.toast(`Imported ${data.imported ?? 0}, skipped ${data.skipped ?? 0}${data.errors?.length ? ' — ' + data.errors[0] : ''}`, data.errors?.length ? 'warn' : 'ok');
    } catch (e: any) { st.toast(e.message, 'bad'); }
    if (fileRef.current) fileRef.current.value = '';
  };
  return <div>
    <div className="card" style={{ maxWidth: 560 }}>
      <h3 style={{ marginTop: 0 }}>CSV Export</h3>
      <p className="muted">Spreadsheet-friendly exports — open in Excel/Google Sheets, edit, and re-import below.</p>
      <div className="row">
        <button onClick={() => exportCsv('products')}>⬇ Products</button>
        <button onClick={() => exportCsv('customers')}>⬇ Customers</button>
        <button onClick={() => exportCsv('suppliers')}>⬇ Suppliers</button>
      </div>
    </div>
    <div className="card" style={{ maxWidth: 560, marginTop: 12 }}>
      <h3 style={{ marginTop: 0 }}>Bulk Import (spec #31)</h3>
      <div className="row" style={{ marginBottom: 8 }}>
        <label className="row" style={{ gap: 6 }}><input type="radio" checked={what === 'products'} onChange={() => setWhat('products')} /> Products</label>
        <label className="row" style={{ gap: 6 }}><input type="radio" checked={what === 'customers'} onChange={() => setWhat('customers')} /> Customers</label>
      </div>
      <input ref={fileRef} type="file" accept=".csv" onChange={e => e.target.files?.[0] && doImport(e.target.files[0])} />
      <p className="muted" style={{ fontSize: 13 }}>Products CSV columns: name, sku, barcode, unit, category, brand, cost_price, retail_price, wholesale_price, stock_qty, min_stock.<br />Customers CSV: name, phone, alt_phone, address, credit_limit, opening_balance.</p>
    </div>
  </div>;
}
