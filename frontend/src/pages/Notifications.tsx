// WhatsApp notifications center (spec #31/#70): queue log, retry failed sends.
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';
import { StatusBadge } from '../components/ui';

export default function Notifications() {
  const st = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const [status, setStatus] = useState('all');
  const load = () => api.get<any[]>(`/api/notifications?status=${status}`).then(setRows).catch(e => st.toast(e.message, 'bad'));
  useEffect(() => { load(); }, [status]); // eslint-disable-line
  const retry = async (n: any) => {
    try { await api.post(`/api/notifications/${n.id}/retry`); st.toast('Queued for retry — deep link opens in WhatsApp Web/Desktop', 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const processNow = async () => {
    try { const r = await api.post<any>('/api/system/process-notifications'); st.toast(`Processed ${r.sent ?? 0} message(s)`, 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>WhatsApp Notifications</h2>
      <div className="row">
        {['all', 'pending', 'sent', 'failed'].map(s => <button key={s} className={status === s ? 'primary' : ''} onClick={() => setStatus(s)}>{s}</button>)}
        <button className="primary" onClick={processNow}>Process queue now</button>
      </div>
    </div>
    <p className="muted">Messages are prepared locally and opened via WhatsApp deep links on this device — no paid API required (spec #70).</p>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Date</th><th>Type</th><th>To</th><th>Phone</th><th>Message</th><th>Status</th><th>Tries</th><th></th></tr></thead>
        <tbody>{rows.map(n => (
          <tr key={n.id}><td>{(n.created_at || '').slice(0, 16).replace('T', ' ')}</td><td>{n.type}</td><td>{n.customer || '—'}</td><td>{n.phone || '—'}</td>
            <td style={{ maxWidth: 320 }} className="muted">{(n.message || '').slice(0, 120)}</td>
            <td><StatusBadge s={n.status} /></td><td>{n.attempts ?? 0}</td>
            <td>{(n.status === 'failed' || n.status === 'pending') && <button onClick={() => retry(n)}>Retry</button>}</td></tr>))}
          {rows.length === 0 && <tr><td colSpan={8} className="muted" style={{ textAlign: 'center', padding: 20 }}>No notifications queued.</td></tr>}</tbody></table>
    </div>
  </div>;
}
