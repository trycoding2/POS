// Cash & Accounts (spec #26/#28): money movements per account + owner withdrawals.
import React, { useEffect, useState } from 'react';
import { api, fmtDate, type Account } from '../api/client';
import { useStore } from '../store';
import { Field, Kpi, Modal } from '../components/ui';

interface Txn { id: number; direction: string; amount: number; reason: string; ref?: string | null; at: string; user_id: number; device?: string; notes?: string }

export default function Cash() {
  const st = useStore();
  const [accts, setAccts] = useState<Account[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [txns, setTxns] = useState<Txn[]>([]);
  const [withdrawals, setWithdrawals] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [showAdjust, setShowAdjust] = useState(false);
  const [showWithdraw, setShowWithdraw] = useState(false);

  const load = () => {
    api.get<Account[]>('/api/accounts').then(a => { setAccts(a); if (sel === null && a[0]) setSel(a[0].id); }).catch(e => st.toast(e.message, 'bad'));
    if (st.can('profit.view')) api.get<any[]>('/api/withdrawals').then(setWithdrawals).catch(() => {});
  };
  useEffect(load, []); // eslint-disable-line
  useEffect(() => {
    if (sel) api.get<Txn[]>(`/api/accounts/${sel}/transactions`).then(setTxns).catch(() => setTxns([]));
  }, [sel]);

  const total = accts.reduce((a, x) => a + (x.balance ?? 0), 0);

  return (
    <div>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Cash &amp; Accounts</h2>
        <div className="row">
          <button onClick={() => setShowAdjust(true)}>Cash adjustment</button>
          {st.can('profit.view') && <button onClick={() => setShowWithdraw(true)}>Owner withdrawal</button>}
          {st.can('cash.manage') && <button className="primary" onClick={() => setShowNew(true)}>+ New account</button>}
        </div>
      </div>
      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Total across accounts" value={st.money(total)} />
        {accts.filter(a => a.is_active).map(a => (
          <Kpi key={a.id} label={`${a.name} (${a.type})`} value={st.money(a.balance ?? 0)} onClick={() => setSel(a.id)} />
        ))}
      </div>
      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <div className="card">
          <b>{accts.find(a => a.id === sel)?.name || 'Account'} — movement history</b>
          <table>
            <thead><tr><th>When</th><th>Reason</th><th>Ref</th><th className="right">Amount</th></tr></thead>
            <tbody>{txns.map(t => (
              <tr key={t.id}>
                <td className="muted">{fmtDate(t.at)}</td>
                <td>{t.reason}{t.notes ? ` — ${t.notes}` : ''}</td>
                <td>{t.ref || '—'}</td>
                <td className="right" style={{ color: t.direction === 'in' ? 'var(--ok)' : 'var(--danger)' }}>
                  {t.direction === 'in' ? '+' : '−'}{st.money(t.amount)}
                </td>
              </tr>
            ))}{!txns.length && <tr><td colSpan={4} className="muted">No movements yet.</td></tr>}</tbody>
          </table>
        </div>
        <div className="card">
          <b>Owner withdrawals</b>
          <p className="muted" style={{ fontSize: 13 }}>Withdrawals are NOT business expenses (spec #28) — they reduce cash but never net profit.</p>
          <table>
            <thead><tr><th>When</th><th>Notes</th><th className="right">Amount</th></tr></thead>
            <tbody>{withdrawals.map((w, i) => (
              <tr key={i}><td className="muted">{fmtDate(w.at)}</td><td>{w.notes || '—'}</td><td className="right">{st.money(w.amount)}</td></tr>
            ))}{!withdrawals.length && <tr><td colSpan={3} className="muted">None recorded.</td></tr>}</tbody>
          </table>
        </div>
      </div>

      {showNew && <NewAccount onClose={() => setShowNew(false)} onDone={() => { setShowNew(false); load(); }} />}
      {showAdjust && <Adjust accts={accts} sel={sel} onClose={() => setShowAdjust(false)} onDone={() => { setShowAdjust(false); load(); }} />}
      {showWithdraw && <Withdraw accts={accts} onClose={() => setShowWithdraw(false)} onDone={() => { setShowWithdraw(false); load(); }} />}
    </div>
  );
}

function NewAccount({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [f, setF] = useState({ name: '', type: 'cash', opening_balance: 0, is_default_sale: false });
  const save = async () => {
    try { await api.post('/api/accounts', f); st.toast('Account created.', 'ok'); onDone(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return (
    <Modal title="New account" onClose={onClose} width={400}>
      <Field label="Name"><input autoFocus value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="e.g. Easypaisa" /></Field>
      <Field label="Type">
        <select value={f.type} onChange={e => setF({ ...f, type: e.target.value })}>
          <option value="cash">Cash</option><option value="bank">Bank</option><option value="wallet">Wallet</option>
        </select>
      </Field>
      <Field label="Opening balance"><input type="number" value={f.opening_balance} onChange={e => setF({ ...f, opening_balance: Number(e.target.value) })} /></Field>
      <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={f.is_default_sale} onChange={e => setF({ ...f, is_default_sale: e.target.checked })} /> Default for POS sales</label>
      <div className="row" style={{ justifyContent: 'flex-end' }}><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Create</button></div>
    </Modal>
  );
}

function Adjust({ accts, sel, onClose, onDone }: { accts: Account[]; sel: number | null; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [accountId, setAccountId] = useState(sel ?? accts[0]?.id ?? 0);
  const [delta, setDelta] = useState(0);
  const [reason, setReason] = useState('');
  const save = async () => {
    if (!reason.trim()) return st.toast('A reason is required for cash adjustments (audit rule #1).', 'bad');
    try { await api.post(`/api/accounts/${accountId}/adjust`, { delta, reason }); st.toast('Adjustment recorded.', 'ok'); onDone(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return (
    <Modal title="Manual cash adjustment" onClose={onClose} width={420}>
      <p className="muted" style={{ fontSize: 13 }}>Use for counting differences (+/-). Every adjustment is audited and may require approval per settings.</p>
      <Field label="Account">
        <select value={accountId} onChange={e => setAccountId(Number(e.target.value))}>{accts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
      </Field>
      <Field label="Delta (negative allowed)"><input type="number" value={delta} onChange={e => setDelta(Number(e.target.value))} /></Field>
      <Field label="Reason"><input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Cash count short by Rs.200" /></Field>
      <div className="row" style={{ justifyContent: 'flex-end' }}><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Record</button></div>
    </Modal>
  );
}

function Withdraw({ accts, onClose, onDone }: { accts: Account[]; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [amount, setAmount] = useState(0);
  const [accountId, setAccountId] = useState(accts[0]?.id ?? 0);
  const [notes, setNotes] = useState('');
  const save = async () => {
    if (amount <= 0) return st.toast('Amount must be positive.', 'bad');
    try { const r = await api.post<{ ref: string }>('/api/withdrawals', { amount, account_id: accountId, notes }); st.toast(`Withdrawal ${r!.ref ?? ''} recorded.`, 'ok'); onDone(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return (
    <Modal title="Owner withdrawal" onClose={onClose} width={400}>
      <Field label="Amount"><input autoFocus type="number" min={0} value={amount} onChange={e => setAmount(Number(e.target.value))} /></Field>
      <Field label="From account">
        <select value={accountId} onChange={e => setAccountId(Number(e.target.value))}>{accts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
      </Field>
      <Field label="Notes"><input value={notes} onChange={e => setNotes(e.target.value)} /></Field>
      <div className="row" style={{ justifyContent: 'flex-end' }}><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Record withdrawal</button></div>
    </Modal>
  );
}
