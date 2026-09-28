// Suppliers (spec #18/#19): list, profile with ledger/timeline, temp-seller conversion.
import React, { useState } from 'react';
import { api, type Supplier } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced } from '../components/ui';

export default function Suppliers() {
  const st = useStore();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const { data } = useDebounced(() => api.get<Supplier[]>(`/api/suppliers?q=${encodeURIComponent(q)}&filter=${filter}`), [q, filter]);
  const [editing, setEditing] = useState<Partial<Supplier> | null>(null);
  const [detail, setDetail] = useState<any | null>(null);

  const save = async (s: Partial<Supplier>) => {
    try {
      if (s.id) await api.put(`/api/suppliers/${s.id}`, s); else await api.post('/api/suppliers', s);
      st.toast('Supplier saved', 'ok'); setEditing(null);
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const open = async (s: Supplier) => {
    try { setDetail(await api.get<any>(`/api/suppliers/${s.id}`)); } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Suppliers</h2>
      <button className="primary" onClick={() => setEditing({})}>+ New supplier</button>
    </div>
    <div className="row" style={{ marginBottom: 10 }}>
      <input autoFocus style={{ flex: 1 }} placeholder="Search supplier / company / phone..." value={q} onChange={e => setQ(e.target.value)} />
      {['all', 'outstanding'].map(f => <button key={f} className={filter === f ? 'primary' : ''} onClick={() => setFilter(f)}>{f}</button>)}
    </div>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Terms</th><th>Payable</th><th>Status</th><th></th></tr></thead>
        <tbody>{(data || []).map(s => (
          <tr key={s.id}>
            <td><a style={{ cursor: 'pointer' }} onClick={() => open(s)}>{s.name}</a></td>
            <td>{s.company || '-'}</td><td>{s.phone || '-'}</td><td>{s.payment_terms || '-'}</td>
            <td style={(s.balance ?? 0) > 0 ? { color: 'var(--danger)', fontWeight: 700 } : undefined}>{st.money(s.balance)}</td>
            <td>{s.is_active ? <StatusBadge s="active" /> : <StatusBadge s="cancelled" />}</td>
            <td><button onClick={() => setEditing(s)}>Edit</button></td>
          </tr>))}
          {(data || []).length === 0 && <tr><td colSpan={7} className="muted" style={{ textAlign: 'center', padding: 20 }}>No suppliers yet. Quick cash purchases from temporary sellers are recorded under "Temporary / Unknown" and can be converted later (spec #19).</td></tr>}
        </tbody></table>
    </div>
    {editing && <SupplierForm initial={editing} onCancel={() => setEditing(null)} onSave={save} />}
    {detail && <Modal title={detail.supplier?.name || detail.name} onClose={() => setDetail(null)} width={700}>
      <div className="grid kpis" style={{ marginBottom: 10 }}>
        <Kv label="Payable" v={st.money(detail.payable ?? detail.balance)} /><Kv label="Total purchases" v={st.money(detail.total_purchases)} />
        <Kv label="Total paid" v={st.money(detail.total_paid)} /><Kv label="Returns" v={st.money(detail.total_returns)} />
      </div>
      <h4>Ledger / timeline (spec #53)</h4>
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        <table><thead><tr><th>Date</th><th>Type</th><th>Ref</th><th>Payable +</th><th>Payable -</th><th>By</th></tr></thead>
          <tbody>{(detail.timeline || []).slice(0, 80).map((t: any, i: number) => (
            <tr key={i}><td>{t.at}</td><td>{t.type}</td><td>{t.ref || '-'}</td>
              <td>{t.debit ? st.money(t.debit) : '-'}</td><td>{t.credit ? st.money(t.credit) : '-'}</td><td>{t.user || '-'}</td></tr>))}
            {(detail.timeline || []).length === 0 && <tr><td colSpan={6} className="muted">No transactions yet.</td></tr>}</tbody></table>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
        <button className="primary" onClick={() => { setEditing(detail.supplier || detail); setDetail(null); }}>Edit</button>
      </div>
    </Modal>}
  </div>;
}

function Kv({ label, v }: { label: string; v: string }) {
  return <div className="card kpi"><div className="v" style={{ fontSize: 17 }}>{v}</div><div className="l">{label}</div></div>;
}

function SupplierForm({ initial, onCancel, onSave }: { initial: Partial<Supplier>; onCancel: () => void; onSave: (s: Partial<Supplier>) => void }) {
  const [f, setF] = useState<Partial<Supplier>>(initial);
  const inp = (k: keyof Supplier) => <input value={(f as any)[k] ?? ''} onChange={e => setF(p => ({ ...p, [k]: e.target.value }))} />;
  return <Modal title={f.id ? `Edit: ${f.name}` : 'New supplier'} onClose={onCancel} width={460}>
    <Field label="Name *"><input autoFocus value={f.name || ''} onChange={e => setF(p => ({ ...p, name: e.target.value }))} /></Field>
    <div className="row" style={{ gap: 10 }}>
      <div style={{ flex: 1 }}><Field label="Company">{inp('company')}</Field></div>
      <div style={{ flex: 1 }}><Field label="Phone">{inp('phone')}</Field></div>
    </div>
    <Field label="Address">{inp('address')}</Field>
    <div className="row" style={{ gap: 10 }}>
      <Field label="Contact person">{inp('contact_person')}</Field>
      <Field label="Payment terms">{inp('payment_terms')}</Field>
    </div>
    {!f.id && <Field label="Opening payable balance"><input type="number" value={(f as any).opening_balance ?? ''} onChange={e => setF(p => ({ ...p, opening_balance: Number(e.target.value) } as any))} /></Field>}
    <Field label="Notes">{inp('notes')}</Field>
    {f.id != null && <label><input type="checkbox" checked={f.is_active !== false} onChange={e => setF(p => ({ ...p, is_active: e.target.checked }))} /> Active</label>}
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onCancel}>Cancel</button>
      <button className="primary" disabled={!f.name} onClick={() => onSave(f)}>Save</button>
    </div>
  </Modal>;
}
