// Purchases (spec #19/#20): supplier or temporary seller, line items with cost/discount/free qty,
// partial payment with due tracking. Stock + payables + cash all move atomically on the backend.
import React, { useState } from 'react';
import { api, type Account, type Purchase, type Supplier, type Product } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced } from '../components/ui';

interface DraftItem { product_id: number; name: string; qty: string; cost_price: string; discount: string; qty_free: string; batch_no: string }

export default function Purchases() {
  const st = useStore();
  const [q, setQ] = useState('');
  const { data: list } = useDebounced(() => api.get<Purchase[]>(`/api/purchases?q=${encodeURIComponent(q)}`), [q]);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<Purchase | null>(null);
  const refresh = () => setQ(x => x + '');

  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Purchases</h2>
      {st.can('purchase.create') && <button className="primary" onClick={() => setCreating(true)}>+ New purchase</button>}
    </div>
    <input autoFocus style={{ width: 320, marginBottom: 10 }} placeholder="Search by PUR reference…"
      value={q} onChange={e => setQ(e.target.value)} />
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Ref</th><th>Date</th><th>Total</th><th>Paid</th><th>Due</th><th>Status</th><th></th></tr></thead>
        <tbody>{(list || []).map(p => (
          <tr key={p.id}>
            <td><a style={{ cursor: 'pointer' }} onClick={() => setDetail(p)}>{p.ref}</a></td>
            <td className="muted">{new Date(p.created_at || '').toLocaleString()}</td>
            <td>{st.money(p.grand_total)}</td><td>{st.money(p.paid_amount)}</td>
            <td style={p.due_amount > 0 ? { color: 'var(--danger)', fontWeight: 700 } : undefined}>{st.money(p.due_amount)}</td>
            <td><StatusBadge s={p.status} /></td>
            <td><button onClick={() => setDetail(p)}>View</button></td>
          </tr>))}
          {(list || []).length === 0 && <tr><td colSpan={7} className="muted" style={{ textAlign: 'center', padding: 20 }}>No purchases yet.</td></tr>}
        </tbody></table>
    </div>
    {creating && <PurchaseForm onClose={() => setCreating(false)} onDone={() => { setCreating(false); refresh(); }} />}
    {detail && <Modal title={detail.ref} onClose={() => setDetail(null)} width={640}>
      <p className="muted">Total {st.money(detail.grand_total)} · Paid {st.money(detail.paid_amount)} · Due {st.money(detail.due_amount)} · <StatusBadge s={detail.status} /></p>
      <table><thead><tr><th>Product</th><th>Qty</th><th>Free</th><th>Cost</th><th>Discount</th><th>Line total</th></tr></thead>
        <tbody>{detail.items.map(i => <tr key={i.id}><td>#{i.product_id}</td><td>{i.qty_received}</td><td>{i.qty_free}</td>
          <td>{st.money(i.cost_price)}</td><td>{st.money(i.discount ?? 0)}</td><td>{st.money(i.line_total)}</td></tr>)}</tbody></table>
      {detail.notes && <p className="muted">Notes: {detail.notes}</p>}
    </Modal>}
  </div>;
}

function PurchaseForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [supQ, setSupQ] = useState('');
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [tempName, setTempName] = useState('');
  const [items, setItems] = useState<DraftItem[]>([]);
  const [prodQ, setProdQ] = useState('');
  const [invoice, setInvoice] = useState('');
  const [paid, setPaid] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const { data: accounts } = useDebounced(() => api.get<Account[]>('/api/accounts'), []);
  const [accountId, setAccountId] = useState<number | null>(null);

  const { data: sups } = useDebounced(() => api.get<Supplier[]>(`/api/suppliers?q=${encodeURIComponent(supQ)}`), [supQ]);
  const { data: prods } = useDebounced(
    () => prodQ ? api.get<Product[]>(`/api/products/search?q=${encodeURIComponent(prodQ)}`) : Promise.resolve([] as Product[]),
    [prodQ]);

  const total = items.reduce((s, i) => s + Math.max(0, Number(i.qty) || 0) * (Number(i.cost_price) || 0) - (Number(i.discount) || 0), 0);
  const paidN = Number(paid || 0);
  const due = Math.max(0, total - paidN);

  const addProduct = (p: Product) => {
    setItems(prev => [...prev, { product_id: p.id, name: p.name, qty: '1', cost_price: String(p.cost_price ?? ''), discount: '0', qty_free: '0', batch_no: '' }]);
    setProdQ('');
  };
  const upd = (idx: number, k: keyof DraftItem) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, [k]: e.target.value } : it));

  const submit = async () => {
    if (!supplier && !tempName.trim()) { st.toast('Select a supplier or enter a temporary seller name.', 'bad'); return; }
    if (!items.length) { st.toast('Add at least one product.', 'bad'); return; }
    if (paidN > 0 && !accountId) { st.toast('Choose the account the payment is made from.', 'bad'); return; }
    setBusy(true);
    try {
      await api.post('/api/purchases', {
        supplier_id: supplier?.id ?? null, supplier_name: supplier ? undefined : tempName.trim(),
        items: items.map(i => ({ product_id: i.product_id, qty: Number(i.qty), cost_price: Number(i.cost_price), discount: Number(i.discount || 0), qty_free: Number(i.qty_free || 0), batch_no: i.batch_no })),
        invoice_no: invoice, paid_amount: paidN, account_id: accountId, notes,
      });
      st.toast(`Purchase recorded — stock updated, payable ${due > 0 ? st.money(due) + ' due' : 'fully paid'}`, 'ok');
      onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
    setBusy(false);
  };

  return <Modal title="New purchase" onClose={onClose} width={760}>
    <div className="row" style={{ gap: 10 }}>
      <div style={{ flex: 1 }}>
        <Field label="Supplier (search)">
          <input value={supQ} placeholder="Type to search suppliers…" onChange={e => { setSupQ(e.target.value); setSupplier(null); }} />
          {!supplier && supQ && <div className="suggest">{(sups || []).map(s =>
            <div key={s.id} className="suggest-row" onClick={() => { setSupplier(s); setSupQ(s.name); }}>{s.name}{s.phone ? ` · ${s.phone}` : ''}</div>)}</div>}
        </Field>
        {supplier && <span className="badge ok">Selected: {supplier.name}</span>}
      </div>
      <div style={{ flex: 1 }}>
        <Field label="…or temporary / unknown seller (spec #19)">
          <input value={tempName} disabled={!!supplier} placeholder="e.g. Biker from main market" onChange={e => setTempName(e.target.value)} />
        </Field>
      </div>
    </div>

    <Field label="Add products (name / SKU / barcode)">
      <input value={prodQ} placeholder="Start typing…" onChange={e => setProdQ(e.target.value)} />
      {!!items.length && <div className="card" style={{ padding: 0, marginTop: 8, maxHeight: 220, overflowY: 'auto' }}>
        <table><thead><tr><th>Product</th><th>Qty</th><th>Cost</th><th>Disc.</th><th>Free</th><th>Batch</th><th></th></tr></thead>
          <tbody>{items.map((it, idx) => <tr key={idx}>
            <td>{it.name}</td>
            <td><input style={{ width: 60 }} type="number" value={it.qty} onChange={upd(idx, 'qty')} /></td>
            <td><input style={{ width: 80 }} type="number" value={it.cost_price} onChange={upd(idx, 'cost_price')} /></td>
            <td><input style={{ width: 60 }} type="number" value={it.discount} onChange={upd(idx, 'discount')} /></td>
            <td><input style={{ width: 50 }} type="number" value={it.qty_free} onChange={upd(idx, 'qty_free')} /></td>
            <td><input style={{ width: 80 }} value={it.batch_no} onChange={upd(idx, 'batch_no')} /></td>
            <td><button className="danger" onClick={() => setItems(p => p.filter((_, i) => i !== idx))}>✕</button></td>
          </tr>)}</tbody></table>
      </div>}
    </Field>
    {prodQ && (prods || []).length > 0 && <div className="suggest" style={{ marginBottom: 10 }}>
      {(prods || []).slice(0, 8).map(p => <div key={p.id} className="suggest-row" onClick={() => addProduct(p)}>
        {p.name} <span className="muted">stock {p.stock_qty} · last cost {st.money(p.cost_price)}</span></div>)}
    </div>}

    <div className="row" style={{ gap: 10 }}>
      <div style={{ flex: 1 }}><Field label="Supplier invoice no."><input value={invoice} onChange={e => setInvoice(e.target.value)} /></Field></div>
      <div style={{ flex: 1 }}><Field label="Amount paid now"><input type="number" value={paid} onChange={e => setPaid(e.target.value)} /></Field></div>
      <div style={{ flex: 1 }}><Field label="Paid from account">
        <select value={accountId ?? ''} onChange={e => setAccountId(Number(e.target.value) || null)}>
          <option value="">—</option>{(accounts || []).filter(a => a.is_active).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select></Field></div>
    </div>
    <Field label="Notes"><input value={notes} onChange={e => setNotes(e.target.value)} /></Field>

    <div className="card" style={{ background: 'var(--bg)' }}>
      <div className="row spread"><span>Total</span><b>{st.money(total)}</b></div>
      <div className="row spread"><span>Paying</span><b>{st.money(paidN)}</b></div>
      <div className="row spread"><span>Due (supplier payable)</span><b style={{ color: due > 0 ? 'var(--danger)' : undefined }}>{st.money(due)}</b></div>
    </div>
    <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={busy || !items.length} onClick={submit}>{busy ? 'Saving…' : 'Save purchase'}</button>
    </div>
  </Modal>;
}
