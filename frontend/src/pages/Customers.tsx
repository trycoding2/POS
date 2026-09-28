// Customers module (spec #16): list/filters, create/edit, profile with ledger + timeline.
import React, { useState } from 'react';
import { api, Customer } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced } from '../components/ui';

export default function Customers() {
  const st = useStore();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const { data } = useDebounced(() => api.get<Customer[]>(`/api/customers?q=${encodeURIComponent(q)}&filter=${filter}`), [q, filter]);
  const [editing, setEditing] = useState<Partial<Customer> | null>(null);
  const [detail, setDetail] = useState<any | null>(null);

  const save = async (c: Partial<Customer>) => {
    try {
      if (c.id) await api.put(`/api/customers/${c.id}`, c); else await api.post('/api/customers', c);
      st.toast('Customer saved', 'ok'); setEditing(null); setQ(x => x + ''); // refresh trigger
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  const open = async (c: Customer) => {
    try { setDetail(await api.get<any>(`/api/customers/${c.id}`)); } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Customers</h2>
      <button className="primary" onClick={() => setEditing({ is_khata: true, whatsapp_enabled: true })}>+ New customer</button>
    </div>
    <div className="row" style={{ marginBottom: 10 }}>
      <input autoFocus style={{ flex: 1 }} placeholder="Search name or phone…" value={q} onChange={e => setQ(e.target.value)} />
      {['all', 'khata', 'outstanding', 'overdue', 'recent'].map(f =>
        <button key={f} className={filter === f ? 'primary' : ''} onClick={() => setFilter(f)}>{f}</button>)}
    </div>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Name</th><th>Phone</th><th>Khata</th><th>Balance</th><th>Credit limit</th><th>Status</th><th></th></tr></thead>
        <tbody>{(data || []).map(c => (
          <tr key={c.id}>
            <td><a style={{ cursor: 'pointer' }} onClick={() => open(c)}>{c.name}</a></td>
            <td>{c.phone || '—'}</td><td>{c.is_khata ? '✅' : '—'}</td>
            <td style={(c.balance ?? 0) > 0 ? { color: 'var(--danger)', fontWeight: 700 } : undefined}>{st.money(c.balance)}</td>
            <td>{st.money(c.credit_limit)}</td>
            <td>{c.is_active ? <StatusBadge s="active" /> : <StatusBadge s="cancelled" />}</td>
            <td><button onClick={() => setEditing(c)}>Edit</button></td>
          </tr>))}
          {(data || []).length === 0 && <tr><td colSpan={7} className="muted" style={{ textAlign: 'center', padding: 20 }}>No customers found.</td></tr>}
        </tbody></table>
    </div>
    {editing && <CustomerForm initial={editing} onCancel={() => setEditing(null)} onSave={save} />}
    {detail && <Modal title={detail.customer?.name || detail.name} onClose={() => setDetail(null)} width={700}>
      <div className="grid kpis" style={{ marginBottom: 10 }}>
        <Kv label="Balance" v={st.money(detail.balance)} /><Kv label="Total purchases" v={st.money(detail.total_purchases)} />
        <Kv label="Total payments" v={st.money(detail.total_payments)} /><Kv label="Last purchase" v={detail.last_purchase || '—'} />
      </div>
      <p className="muted">{detail.customer?.phone || detail.phone} {detail.customer?.address || detail.address}</p>
      <h4>Ledger / timeline (spec #53)</h4>
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        <table><thead><tr><th>Date</th><th>Type</th><th>Ref</th><th>Debit</th><th>Credit</th><th>By</th></tr></thead>
          <tbody>{(detail.timeline || []).slice(0, 80).map((t: any, i: number) => (
            <tr key={i}><td>{t.at}</td><td>{t.type}</td><td>{t.ref || '—'}</td>
              <td>{t.debit ? st.money(t.debit) : '—'}</td><td>{t.credit ? st.money(t.credit) : '—'}</td><td>{t.user || '—'}</td></tr>))}
            {(detail.timeline || []).length === 0 && <tr><td colSpan={6} className="muted">No transactions yet.</td></tr>}</tbody></table>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
        {st.can('whatsapp.send') && <button onClick={async () => {
          try { await api.post(`/api/khata/reminders/${detail.customer?.id ?? detail.id}`); st.toast('Balance reminder queued for WhatsApp', 'ok'); }
          catch (e: any) { st.toast(e.message, 'bad'); }
        }}>Send WhatsApp reminder</button>}
        <button className="primary" onClick={() => { setEditing(detail.customer || detail); setDetail(null); }}>Edit</button>
      </div>
    </Modal>}
  </div>;
}

function Kv({ label, v }: { label: string; v: string }) {
  return <div className="card kpi"><div className="v" style={{ fontSize: 17 }}>{v}</div><div className="l">{label}</div></div>;
}

function CustomerForm({ initial, onCancel, onSave }: { initial: Partial<Customer>; onCancel: () => void; onSave: (c: Partial<Customer>) => void }) {
  const [f, setF] = useState<Partial<Customer>>(initial);
  const inp = (k: keyof Customer, type = 'text') => <input type={type} value={(f as any)[k] ?? ''} onChange={e => setF(p => ({ ...p, [k]: e.target.value }))} />;
  return <Modal title={f.id ? `Edit: ${f.name}` : 'New customer'} onClose={onCancel} width={460}>
    <Field label="Name *"><input autoFocus value={f.name || ''} onChange={e => setF(p => ({ ...p, name: e.target.value }))} /></Field>
    <div className="row" style={{ gap: 10 }}>
      <div style={{ flex: 1 }}><Field label="Phone">{inp('phone', 'tel')}</Field></div>
      <div style={{ flex: 1 }}><Field label="Alternate phone">{inp('alt_phone', 'tel')}</Field></div>
    </div>
    <Field label="Address">{inp('address')}</Field>
    <div className="row" style={{ gap: 10 }}>
      <Field label="Credit limit">{inp('credit_limit', 'number')}</Field>
      {!f.id && <Field label="Opening balance">{inp('opening_balance', 'number')}</Field>}
    </div>
    <Field label="Notes">{inp('notes')}</Field>
    <div className="row" style={{ gap: 14 }}>
      <label><input type="checkbox" checked={!!f.is_khata} onChange={e => setF(p => ({ ...p, is_khata: e.target.checked }))} /> Khata customer</label>
      <label><input type="checkbox" checked={f.whatsapp_enabled !== false} onChange={e => setF(p => ({ ...p, whatsapp_enabled: e.target.checked }))} /> WhatsApp OK</label>
      {f.id != null && <label><input type="checkbox" checked={f.is_active !== false} onChange={e => setF(p => ({ ...p, is_active: e.target.checked }))} /> Active</label>}
    </div>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onCancel}>Cancel</button>
      <button className="primary" disabled={!f.name} onClick={() => onSave(f)}>Save</button>
    </div>
  </Modal>;
}
