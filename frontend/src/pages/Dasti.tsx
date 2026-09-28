// Dasti - temporary short-term credit (spec #15). Separate from long-term Khata.
import React, { useEffect, useState } from 'react';
import { api, Dasti as D } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useConfirm } from '../components/ui';

export default function Dasti() {
  const st = useStore();
  const [rows, setRows] = useState<D[]>([]);
  const [status, setStatus] = useState('open');
  const [creating, setCreating] = useState(false);
  const [payFor, setPayFor] = useState<D | null>(null);
  const [confirmAsk, confirmNode] = useConfirm();
  const load = () => api.get<D[]>(`/api/dastis?status=${status}`).then(setRows).catch(e => st.toast(e.message, 'bad'));
  useEffect(() => { load(); }, [status]); // eslint-disable-line

  const extend = async (d: D) => {
    const days = prompt('Extend due date of ' + d.ref + ' by how many days?', '1');
    if (!days) return;
    try { await api.post(`/api/dastis/${d.id}/extend`, { days: Number(days), reason: 'Due-date extension' }); st.toast('Dasti extended - original record kept', 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const cancel = async (d: D) => {
    const ok = await confirmAsk('Cancel ' + d.ref + ' (' + st.money(d.outstanding) + ')? The original dasti stays in history as cancelled with a reason (spec #33).');
    if (!ok) return;
    const reason = prompt('Reason:') || 'Cancelled';
    try { await api.post(`/api/dastis/${d.id}/cancel`, { reason }); st.toast('Dasti cancelled with audit trail', 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Dasti - temporary credit</h2>
      <div className="row">
        {['open', 'settled', 'all'].map(s => <button key={s} className={status === s ? 'primary' : ''} onClick={() => setStatus(s)}>{s}</button>)}
        <button className="primary" onClick={() => setCreating(true)}>+ New Dasti</button>
      </div>
    </div>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Ref</th><th>Customer</th><th>Phone</th><th>Amount</th><th>Paid</th><th>Outstanding</th><th>Due</th><th>Status</th><th></th></tr></thead>
        <tbody>{rows.map(d => (
          <tr key={d.id}>
            <td>{d.ref}</td><td>{d.customer_name || 'Unnamed'}</td><td>{d.phone || '-'}</td>
            <td>{st.money(d.amount)}</td><td>{st.money(d.paid_amount)}</td>
            <td style={(d as any).overdue ? { color: 'var(--danger)', fontWeight: 700 } : undefined}>{st.money(d.outstanding)}{(d as any).overdue ? ' (OVERDUE)' : ''}</td>
            <td>{d.due_date || '-'}</td><td><StatusBadge s={d.status} /></td>
            <td className="row">
              {d.status !== 'settled' && d.status !== 'cancelled' && <>
                {st.can('payment.receive') && <button className="primary" onClick={() => setPayFor(d)}>Receive</button>}
                <button onClick={() => extend(d)}>Extend</button>
                <button className="danger" onClick={() => cancel(d)}>Cancel</button>
              </>}
            </td>
          </tr>))}
          {rows.length === 0 && <tr><td colSpan={9} className="muted" style={{ textAlign: 'center', padding: 20 }}>No dasti records.</td></tr>}
        </tbody></table>
    </div>
    {creating && <CreateModal onClose={() => setCreating(false)} onDone={() => { setCreating(false); load(); }} />}
    {payFor && <PayModal d={payFor} onClose={() => setPayFor(null)} onDone={() => { setPayFor(null); load(); }} />}
    {confirmNode}
  </div>;
}

function CreateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [f, setF] = useState({ customer_name: '', phone: '', amount: '', items_text: '', due_days: String(st.settings['dasti.default_due_days'] ?? '1'), notes: '' });
  const submit = async () => {
    try {
      await api.post('/api/dastis', {
        customer_name: f.customer_name || undefined, phone: f.phone || undefined,
        amount: f.amount ? Number(f.amount) : undefined,
        items: f.items_text ? [{ description: f.items_text, qty: 1, unit_price: Number(f.amount) || 0 }] : [],
        due_days: Number(f.due_days) || 1, notes: f.notes || undefined,
      });
      st.toast('Dasti created with full audit trail', 'ok'); onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title="New Dasti (temporary credit)" onClose={onClose} width={420}>
    <p className="muted">Customer name and phone are optional for dasti (spec #15).</p>
    <div className="row" style={{ gap: 10 }}>
      <Field label="Customer name"><input autoFocus value={f.customer_name} onChange={e => setF(p => ({ ...p, customer_name: e.target.value }))} /></Field>
      <Field label="Phone"><input value={f.phone} onChange={e => setF(p => ({ ...p, phone: e.target.value }))} /></Field>
    </div>
    <Field label="Amount *"><input type="number" value={f.amount} onChange={e => setF(p => ({ ...p, amount: e.target.value }))} /></Field>
    <Field label="Items description (optional)"><input value={f.items_text} onChange={e => setF(p => ({ ...p, items_text: e.target.value }))} placeholder="e.g. 1kg sugar, 1L oil" /></Field>
    <div className="row" style={{ gap: 10 }}>
      <Field label="Due in (days)"><input type="number" value={f.due_days} onChange={e => setF(p => ({ ...p, due_days: e.target.value }))} /></Field>
      <Field label="Notes"><input value={f.notes} onChange={e => setF(p => ({ ...p, notes: e.target.value }))} /></Field>
    </div>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={!f.amount} onClick={submit}>Create Dasti</button>
    </div>
  </Modal>;
}

function PayModal({ d, onClose, onDone }: { d: D; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [amount, setAmount] = useState(String(d.outstanding));
  const [accountId, setAccountId] = useState<number | ''>('');
  const [accounts, setAccounts] = useState<any[]>([]);
  useEffect(() => { api.get<any[]>('/api/accounts').then(a => { setAccounts(a.filter(x => x.is_active)); if (a[0]) setAccountId(a[0].id); }).catch(() => {}); }, []);
  const submit = async () => {
    try {
      await api.post(`/api/dastis/${d.id}/pay`, { amount: Number(amount), account_id: accountId });
      st.toast('Dasti payment recorded', 'ok'); onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title={`Receive dasti payment - ${d.ref}`} onClose={onClose} width={360}>
    <p className="muted">Outstanding: <b>{st.money(d.outstanding)}</b></p>
    <Field label="Amount"><input autoFocus type="number" value={amount} onChange={e => setAmount(e.target.value)} /></Field>
    <Field label="Into account"><select value={accountId} onChange={e => setAccountId(Number(e.target.value))}>
      {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={!amount || !accountId} onClick={submit}>Record payment</button>
    </div>
  </Modal>;
}
