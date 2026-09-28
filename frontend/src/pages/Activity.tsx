// Live activity monitor + global audit search (spec #31/#32/#54) with tamper-check.
import React, { useEffect, useState } from 'react';
import { api, fmtDate, type AuditRow } from '../api/client';
import { useStore } from '../store';
import { Modal, StatusBadge } from '../components/ui';

export default function Activity() {
  const st = useStore();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [q, setQ] = useState('');
  const [module, setModule] = useState('');
  const [action, setAction] = useState('');
  const [userF, setUserF] = useState('');
  const [detail, setDetail] = useState<AuditRow | null>(null);
  const [verify, setVerify] = useState<{ ok: boolean; first_bad_row?: number | null } | null>(null);

  const load = () => {
    const p = new URLSearchParams();
    if (q) p.set('q', q);
    if (module) p.set('module', module);
    if (action) p.set('action', action);
    if (userF) p.set('user_id', userF);
    p.set('limit', '150');
    api.get<AuditRow[]>(`/api/activity?${p.toString()}`).then(setRows).catch(e => st.toast(e.message, 'bad'));
  };
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [q, module, action, userF]); // eslint-disable-line

  const modules = Array.from(new Set(rows.map(r => r.module))).sort();
  const actions = Array.from(new Set(rows.map(r => r.action))).sort();

  return (
    <div>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Audit Log &amp; Activity</h2>
        <button onClick={async () => {
          try { setVerify(await api.get('/api/audit/verify')); } catch (e: any) { st.toast(e.message, 'bad'); }
        }}>Verify integrity chain</button>
      </div>
      {verify && (
        <div className="card" style={{ marginBottom: 10, borderColor: verify.ok ? 'var(--ok)' : 'var(--danger)' }}>
          {verify.ok
            ? <span style={{ color: 'var(--ok)' }}>✔ Hash chain verified — no record has been tampered with.</span>
            : <span style={{ color: 'var(--danger)' }}>✖ Chain broken at row #{verify.first_bad_row}. Investigate immediately.</span>}
        </div>
      )}
      <div className="row" style={{ gap: 8, marginBottom: 10 }}>
        <input placeholder="Search user, ref (SALE-…), transaction…" value={q} onChange={e => setQ(e.target.value)} style={{ flex: 1 }} />
        <select value={module} onChange={e => setModule(e.target.value)}>
          <option value="">All modules</option>{modules.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={action} onChange={e => setAction(e.target.value)}>
          <option value="">All actions</option>{actions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <table>
        <thead><tr><th>When</th><th>User</th><th>Device</th><th>Module</th><th>Action</th><th>Entity / Ref</th><th className="right">Amount</th><th>Reason</th></tr></thead>
        <tbody>{rows.map(r => (
          <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => setDetail(r)}>
            <td className="muted">{fmtDate(r.at)}</td>
            <td>{r.user || '—'}{r.role ? <span className="muted"> ({r.role})</span> : ''}</td>
            <td className="muted">{r.device || '—'}</td>
            <td>{r.module}</td>
            <td><StatusBadge s={badAction(r.action) ? r.action : (r.action === 'create' ? 'ok' : r.action)} /></td>
            <td>{r.entity}{r.entity_ref ? ` · ${r.entity_ref}` : ''}</td>
            <td className="right">{r.amount != null ? st.money(r.amount) : ''}</td>
            <td className="muted">{r.reason || ''}</td>
          </tr>
        ))}{!rows.length && <tr><td colSpan={8} className="muted">No matching activity.</td></tr>}</tbody>
      </table>
      {detail && (
        <Modal title={`Audit entry #${detail.id}`} onClose={() => setDetail(null)} width={560}>
          <table><tbody>
            <tr><td className="muted">When</td><td>{fmtDate(detail.at)}</td></tr>
            <tr><td className="muted">Who</td><td>{detail.user} ({detail.role}) on device {detail.device}</td></tr>
            <tr><td className="muted">Module / Action</td><td>{detail.module} / {detail.action}</td></tr>
            <tr><td className="muted">Entity</td><td>{detail.entity} · {detail.entity_ref}</td></tr>
            {detail.related && <tr><td className="muted">Related transaction</td><td>{detail.related}</td></tr>}
            {detail.prev && <tr><td className="muted">Previous value</td><td><code>{String(detail.prev)}</code></td></tr>}
            {detail.new && <tr><td className="muted">New value</td><td><code>{String(detail.new)}</code></td></tr>}
            {detail.reason && <tr><td className="muted">Reason</td><td>{detail.reason}</td></tr>}
            {detail.amount != null && <tr><td className="muted">Financial effect</td><td>{st.money(detail.amount)}</td></tr>}
          </tbody></table>
          <p className="muted" style={{ fontSize: 12 }}>This entry is part of a hash-chained, append-only log. Employees cannot erase it.</p>
        </Modal>
      )}
    </div>
  );
}

const badAction = (a: string) => ['void', 'cancel', 'delete_request', 'reject', 'failed_login', 'permission_change'].includes(a);
