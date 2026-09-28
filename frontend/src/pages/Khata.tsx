// Khata dashboard (spec #17): receivables KPIs + per-customer receive payment.
import React, { useEffect, useState } from 'react';
import { api, Customer } from '../api/client';
import { useStore } from '../store';
import { Kpi, Modal, Field, useDebounced } from '../components/ui';

export default function Khata() {
  const st = useStore();
  const [d, setD] = useState<any>(null);
  const [q, setQ] = useState('');
  const { data: custs } = useDebounced(() => api.get<Customer[]>(`/api/customers?q=${encodeURIComponent(q)}&filter=khata`), [q]);
  const [payFor, setPayFor] = useState<any | null>(null);
  useEffect(() => { api.get<any>('/api/khata/dashboard').then(setD).catch(() => {}); }, []);
  const rows = d?.customers ?? custs ?? [];
  return <div>
    <h2 style={{ marginTop: 0 }}>Khata - customer receivables</h2>
    <div className="grid kpis" style={{ marginBottom: 14 }}>
      <Kpi label="Total receivable" value={st.money(d?.total_receivable)} />
      <Kpi label="Today's credit" value={st.money(d?.today_credit)} />
      <Kpi label="Today's collections" value={st.money(d?.today_collections)} />
      <Kpi label="Overdue amount" value={st.money(d?.overdue_amount)} tone="#d32f2f" />
      <Kpi label="Customers overdue" value={d?.overdue_count ?? (d?.overdue_customers || []).length} tone="#d32f2f" />
    </div>
    <input autoFocus placeholder="Search khata customers..." value={q} onChange={e => setQ(e.target.value)} style={{ width: '100%', marginBottom: 10 }} />
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Customer</th><th>Phone</th><th>Balance</th><th>Credit limit</th><th>Last activity</th><th></th></tr></thead>
        <tbody>{rows.map((c: any) => (
          <tr key={c.id ?? c.customer_id}>
            <td>{c.name}</td><td>{c.phone || '-'}</td>
            <td style={{ color: 'var(--danger)', fontWeight: 700 }}>{st.money(c.balance)}</td>
            <td>{st.money(c.credit_limit)}</td><td className="muted">{c.last_activity || c.last_purchase || '-'}</td>
            <td className="row">
              {st.can('payment.receive') && <button className="primary" onClick={() => setPayFor(c)}>Receive payment</button>}
              {st.can('whatsapp.send') && <button onClick={async () => {
                try { await api.post(`/api/khata/reminders/${c.id ?? c.customer_id}`); st.toast('Reminder queued', 'ok'); } catch (e: any) { st.toast(e.message, 'bad'); }
              }}>Remind</button>}
            </td>
          </tr>))}
          {rows.length === 0 && <tr><td colSpan={6} className="muted" style={{ textAlign: 'center', padding: 20 }}>No outstanding khata balances.</td></tr>}
        </tbody></table>
    </div>
    {payFor && <PayModal c={payFor} onClose={() => setPayFor(null)} onDone={() => { setPayFor(null); api.get<any>('/api/khata/dashboard').then(setD).catch(() => {}); }} />}
  </div>;
}

function PayModal({ c, onClose, onDone }: { c: any; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [amount, setAmount] = useState('');
  const [accountId, setAccountId] = useState<number | ''>('');
  const [accounts, setAccounts] = useState<any[]>([]);
  const [note, setNote] = useState('');
  useEffect(() => { api.get<any[]>('/api/accounts').then(a => { setAccounts(a.filter(x => x.is_active)); if (a[0]) setAccountId(a[0].id); }).catch(() => {}); }, []);
  const submit = async () => {
    try {
      await api.post('/api/pos/customer-payments', { customer_id: c.id ?? c.customer_id, amount: Number(amount), account_id: accountId, notes: note });
      st.toast('Payment received - balance updated', 'ok'); onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title={`Receive payment - ${c.name}`} onClose={onClose} width={380}>
    <p className="muted">Outstanding: <b>{st.money(c.balance)}</b>. Payment posts to the ledger and the selected account (spec #14/#17).</p>
    <Field label="Amount"><input autoFocus type="number" value={amount} onChange={e => setAmount(e.target.value)} /></Field>
    <Field label="Into account"><select value={accountId} onChange={e => setAccountId(Number(e.target.value))}>
      {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
    <Field label="Note"><input value={note} onChange={e => setNote(e.target.value)} /></Field>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={!amount || !accountId} onClick={submit}>Record payment</button>
    </div>
  </Modal>;
}
