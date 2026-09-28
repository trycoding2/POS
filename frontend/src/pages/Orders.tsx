// Purchase Orders (spec #21): create draft/sent orders, send, cancel, receive partially/completely.
import React, { useEffect, useState } from 'react';
import { api, fmtDate, type OrderOut, type Product, type Purchase, type Supplier } from '../api/client';
import { useStore } from '../store';
import { Field, Modal, StatusBadge, useDebounced } from '../components/ui';

interface Meta { categories: { id: number; name: string }[]; brands: any[]; units: { id: number; name: string }[] }

export default function Orders() {
  const st = useStore();
  const [rows, setRows] = useState<OrderOut[]>([]);
  const [status, setStatus] = useState('');
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [creating, setCreating] = useState(false);
  const [receiving, setReceiving] = useState<OrderOut | null>(null);
  const load = () => api.get<OrderOut[]>(`/api/orders${status ? `?status=${status}` : ''}`).then(setRows).catch(e => st.toast(e.message, 'bad'));
  useEffect(() => { load(); }, [status]); // eslint-disable-line
  useEffect(() => {
    api.get<Supplier[]>('/api/suppliers').then(s => setSuppliers(s.filter(x => !x.is_temporary))).catch(() => {});
    api.get<Meta>('/api/catalog/meta').then(setMeta).catch(() => {});
  }, []);

  const setOrderStatus = async (o: OrderOut, s: string) => {
    try { await api.post(`/api/orders/${o.id}/status`, { status: s }); st.toast(`Order ${o.ref} → ${s}`, 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return (
    <div>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Supplier Orders</h2>
        <div className="row">
          <select value={status} onChange={e => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {['draft', 'sent', 'ordered', 'partially_received', 'received', 'cancelled'].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {st.can('order.manage') && <button className="primary" onClick={() => setCreating(true)}>+ New order</button>}
        </div>
      </div>
      <table>
        <thead><tr><th>Ref</th><th>Supplier</th><th>Status</th><th>Items</th><th>Received</th><th>Date</th><th></th></tr></thead>
        <tbody>
          {rows.map(o => {
            const ordered = o.items.reduce((a, i) => a + i.qty_ordered, 0);
            const rec = o.items.reduce((a, i) => a + i.qty_received, 0);
            const sp = suppliers.find(s => s.id === o.supplier_id);
            return (
              <tr key={o.id}>
                <td><b>{o.ref}</b></td>
                <td>{sp?.name || `#${o.supplier_id}`}</td>
                <td><StatusBadge s={o.status} /></td>
                <td>{o.items.length} ({ordered})</td>
                <td>{rec}{rec < ordered && o.status !== 'cancelled' ? <span className="muted"> / {ordered}</span> : ''}</td>
                <td className="muted">{fmtDate(o.created_at)}</td>
                <td className="right">
                  {(o.status === 'draft') && <button onClick={() => setOrderStatus(o, 'sent')}>Send</button>}
                  {(o.status === 'draft' || o.status === 'sent' || o.status === 'ordered' || o.status === 'partially_received') && <>
                    <button onClick={() => setOrderStatus(o, 'ordered')}>Mark ordered</button>
                    {st.can('purchase.receive') && <button className="primary" onClick={() => setReceiving(o)}>Receive</button>}
                    <button className="danger" onClick={() => setOrderStatus(o, 'cancelled')}>Cancel</button>
                  </>}
                </td>
              </tr>
            );
          })}
          {!rows.length && <tr><td colSpan={7} className="muted">No orders.</td></tr>}
        </tbody>
      </table>
      {creating && <NewOrder meta={meta} suppliers={suppliers} onClose={() => setCreating(false)} onDone={() => { setCreating(false); load(); }} />}
      {receiving && <ReceiveModal order={receiving} products={[]} onClose={() => setReceiving(null)}
        onDone={() => { setReceiving(null); load(); }} />}
    </div>
  );
}

function NewOrder({ meta, suppliers, onClose, onDone }: {
  meta: Meta | null; suppliers: Supplier[]; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [supplierId, setSupplierId] = useState<number>(suppliers[0]?.id ?? 0);
  const [send, setSend] = useState(false);
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<{ product_id: number; name: string; qty_ordered: number; expected_cost: number }[]>([]);
  const [q, setQ] = useState('');
  const { data: found } = useDebounced(() => q.trim() ? api.get<Product[]>(`/api/products/search?q=${encodeURIComponent(q)}&limit=8`) : Promise.resolve([]), [q]);

  const add = (p: Product) => {
    if (items.some(i => i.product_id === p.id)) return;
    setItems([...items, { product_id: p.id, name: p.name, qty_ordered: 1, expected_cost: p.cost_price || 0 }]);
    setQ('');
  };

  const save = async () => {
    if (!supplierId) return st.toast('Choose a supplier.', 'bad');
    if (!items.length) return st.toast('Add at least one product.', 'bad');
    try {
      const o = await api.post<OrderOut>('/api/orders', {
        supplier_id: supplierId, send, notes,
        items: items.map(i => ({ product_id: i.product_id, qty_ordered: i.qty_ordered, expected_cost: i.expected_cost })),
      });
      st.toast(`Order ${o.ref} created (${o.status}).`, 'ok');
      onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return (
    <Modal title="New supplier order" onClose={onClose} width={560}>
      <Field label="Supplier">
        <select value={supplierId} onChange={e => setSupplierId(Number(e.target.value))}>
          <option value={0}>— select —</option>
          {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </Field>
      <Field label="Add products">
        <input autoFocus placeholder="Search product…" value={q} onChange={e => setQ(e.target.value)} />
        {found && found.length > 0 && (
          <div className="suggest">{found.map(p => (
            <div key={p.id} className="srow" onClick={() => add(p)}>
              <span>{p.name}</span><span className="muted">stock {p.stock_qty} · cost {st.money(p.cost_price)}</span>
            </div>
          ))}</div>
        )}
      </Field>
      <table>
        <thead><tr><th>Product</th><th>Qty</th><th>Expected cost</th><th></th></tr></thead>
        <tbody>{items.map((i, idx) => (
          <tr key={i.product_id}>
            <td>{i.name}</td>
            <td><input type="number" min={1} style={{ width: 70 }} value={i.qty_ordered}
              onChange={e => setItems(items.map((x, j) => j === idx ? { ...x, qty_ordered: Number(e.target.value) } : x))} /></td>
            <td><input type="number" min={0} style={{ width: 90 }} value={i.expected_cost}
              onChange={e => setItems(items.map((x, j) => j === idx ? { ...x, expected_cost: Number(e.target.value) } : x))} /></td>
            <td><button onClick={() => setItems(items.filter((_, j) => j !== idx))}>✕</button></td>
          </tr>
        ))}</tbody>
      </table>
      <Field label="Notes"><input value={notes} onChange={e => setNotes(e.target.value)} /></Field>
      <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={send} onChange={e => setSend(e.target.checked)} /> Send now (instead of draft)</label>
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
        <button onClick={onClose}>Cancel</button>
        <button className="primary" onClick={save}>Create order</button>
      </div>
      {meta && null /* meta used for future category filtering */}
    </Modal>
  );
}

function ReceiveModal({ order, onClose, onDone }: {
  order: OrderOut; products: Product[]; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [qtys, setQtys] = useState<Record<number, number>>({});
  const [paid, setPaid] = useState(0);
  const [accounts, setAccounts] = useState<{ id: number; name: string }[]>([]);
  const [accountId, setAccountId] = useState(0);
  const [invoice, setInvoice] = useState('');
  useEffect(() => { api.get<any[]>('/api/accounts').then(a => { setAccounts(a); setAccountId(a.find(x => x.is_default_sale)?.id ?? a[0]?.id ?? 0); }).catch(() => {}); }, []);

  const receive = async () => {
    const receipts = order.items
      .map(i => ({ order_item_id: i.id, qty: qtys[i.id] ?? 0 }))
      .filter(r => r.qty > 0);
    if (!receipts.length) return st.toast('Enter quantity to receive for at least one item.', 'bad');
    try {
      const p = await api.post<Purchase>(`/api/orders/${order.id}/receive`, {
        receipts, paid_amount: paid, account_id: accountId || undefined, invoice_no: invoice,
      });
      st.toast(`Received as purchase ${p.ref}. Due: ${st.money(p.due_amount)}`, 'ok');
      onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return (
    <Modal title={`Receive ${order.ref}`} onClose={onClose} width={560}>
      <table>
        <thead><tr><th>Item #</th><th>Ordered</th><th>Already received</th><th>Remaining</th><th>Receive now</th></tr></thead>
        <tbody>{order.items.map(i => (
          <tr key={i.id}>
            <td>#{i.product_id}</td><td>{i.qty_ordered}</td><td>{i.qty_received}</td><td>{i.remaining}</td>
            <td><input type="number" min={0} max={i.remaining} style={{ width: 80 }}
              value={qtys[i.id] ?? 0} onChange={e => setQtys({ ...qtys, [i.id]: Number(e.target.value) })} /></td>
          </tr>
        ))}</tbody>
      </table>
      <p className="muted">Costs come from the order's expected cost. Receiving updates stock, supplier payables and creates a traceable purchase record.</p>
      <div className="row" style={{ gap: 10 }}>
        <Field label="Paid now"><input type="number" min={0} value={paid} onChange={e => setPaid(Number(e.target.value))} style={{ width: 110 }} /></Field>
        <Field label="From account">
          <select value={accountId} onChange={e => setAccountId(Number(e.target.value))}>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </Field>
        <Field label="Supplier invoice #"><input value={invoice} onChange={e => setInvoice(e.target.value)} /></Field>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={onClose}>Cancel</button>
        <button className="primary" onClick={receive}>Receive stock</button>
      </div>
    </Modal>
  );
}
