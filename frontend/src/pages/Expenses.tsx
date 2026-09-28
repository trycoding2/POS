// Expenses (spec #27/#28): categories, entry with account paid from, owner approval workflow,
// and clear separation from owner withdrawals.
import React, { useState } from 'react';
import { api, type Account } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced } from '../components/ui';

export default function Expenses() {
  const st = useStore();
  const [tab, setTab] = useState<'expenses' | 'withdrawals'>('expenses');
  const { data: cats } = useDebounced(() => api.get<{ id: number; name: string }[]>('/api/expense-categories'), []);
  const { data: rows, loading } = useDebounced(
    () => tab === 'expenses' ? api.get<any[]>('/api/expenses') : api.get<any[]>('/api/withdrawals'), [tab]);
  const [creating, setCreating] = useState(false);
  const [newCat, setNewCat] = useState('');

  const addCat = async () => {
    if (!newCat.trim()) return;
    try { await api.post('/api/expense-categories', { name: newCat.trim() }); setNewCat(''); st.toast('Category added', 'ok'); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  const decide = async (id: number, approve: boolean) => {
    try {
      const r = await api.post<any>(`/api/expenses/${id}/${approve ? 'approve' : 'cancel'}`, { reason: '' });
      st.toast(`${r.ref} → ${r.status}`, 'ok');
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Expenses</h2>
      {st.can('expense.create') && tab === 'expenses' && <button className="primary" onClick={() => setCreating(true)}>+ New expense</button>}
    </div>
    <div className="row" style={{ marginBottom: 10 }}>
      <button className={tab === 'expenses' ? 'primary' : ''} onClick={() => setTab('expenses')}>Operating expenses</button>
      {st.can('profit.view') && <button className={tab === 'withdrawals' ? 'primary' : ''} onClick={() => setTab('withdrawals')}>Owner withdrawals</button>}
      <span style={{ flex: 1 }} />
      <input placeholder="+ new category" value={newCat} onChange={e => setNewCat(e.target.value)} onKeyDown={e => e.key === 'Enter' && addCat()} style={{ width: 160 }} />
      <button onClick={addCat}>Add category</button>
    </div>
    {loading && <p className="muted">Loading…</p>}
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead>{tab === 'expenses'
        ? <tr><th>Ref</th><th>When</th><th>Category</th><th>Amount</th><th>Description</th><th>Status</th><th></th></tr>
        : <tr><th>Ref</th><th>When</th><th>Amount</th><th>Notes</th></tr>}</thead>
        <tbody>{(rows || []).map((r: any) => tab === 'expenses' ? (
          <tr key={r.id}><td>{r.ref}</td><td className="muted">{new Date(r.at).toLocaleString()}</td>
            <td>{r.category || '—'}</td><td style={{ fontWeight: 700 }}>{st.money(r.amount)}</td>
            <td>{r.description || '—'}</td><td><StatusBadge s={r.status} /></td>
            <td className="row">
              {r.status === 'pending' && st.can('approval.grant') ? (<>
                <button className="primary" onClick={() => decide(r.id, true)}>Approve</button>
                <button className="danger" onClick={() => decide(r.id, false)}>Reject</button>
              </>) : null}
              {r.status === 'approved' && st.can('expense.create') ? <button onClick={() => decide(r.id, false)}>Cancel</button> : null}
            </td></tr>) : (
          <tr key={r.ref}><td>{r.ref}</td><td className="muted">{new Date(r.at).toLocaleString()}</td>
            <td style={{ fontWeight: 700 }}>{st.money(r.amount)}</td><td>{r.notes || '—'}</td></tr>))}
        </tbody></table>
    </div>
    {creating && <ExpenseForm cats={cats || []} onClose={() => setCreating(false)} />}
  </div>;
}

function ExpenseForm({ cats, onClose }: { cats: { id: number; name: string }[]; onClose: () => void }) {
  const st = useStore();
  const { data: accounts } = useDebounced(() => api.get<Account[]>('/api/accounts'), []);
  const [f, setF] = useState({ category_id: '', amount: '', account_id: '', description: '' });
  const submit = async () => {
    if (!f.category_id || !Number(f.amount)) { st.toast('Category and amount are required.', 'bad'); return; }
    if (!f.account_id) { st.toast('Choose which account paid the expense.', 'bad'); return; }
    try {
      const r = await api.post<any>('/api/expenses', {
        category_id: Number(f.category_id), amount: Number(f.amount),
        account_id: Number(f.account_id), description: f.description });
      st.toast(`Expense ${r.ref} recorded (${r.status})`, 'ok'); onClose();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title="New expense" onClose={onClose} width={440}>
    {!cats.length && <p className="muted">No categories yet — add one in the Expenses screen first.</p>}
    <Field label="Category *"><select value={f.category_id} onChange={e => setF(p => ({ ...p, category_id: e.target.value }))}>
      <option value="">—</option>{cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
    <Field label="Amount *"><input autoFocus type="number" value={f.amount} onChange={e => setF(p => ({ ...p, amount: e.target.value }))} /></Field>
    <Field label="Paid from"><select value={f.account_id} onChange={e => setF(p => ({ ...p, account_id: e.target.value }))}>
      <option value="">—</option>{(accounts || []).filter(a => a.is_active).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
    <Field label="Description"><input value={f.description} onChange={e => setF(p => ({ ...p, description: e.target.value }))} /></Field>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button onClick={onClose}>Cancel</button>
      <button className="primary" onClick={submit}>Save expense</button></div>
  </Modal>;
}
