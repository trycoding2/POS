// Returns (spec #25): customer returns against a sale, supplier returns against a purchase.
// Original transactions are never deleted — returns are separate traceable records.
import React, { useEffect, useState } from 'react';
import { api, fmtDate, type SaleOut, type Purchase } from '../api/client';
import { useStore } from '../store';
import { Field, Modal, StatusBadge } from '../components/ui';

interface RetRow {
  id: number; ref: string; kind: string; total: number; reason?: string; refund_method?: string;
  stock_condition?: string; sale_id?: number | null; purchase_id?: number | null; at: string;
  items: { product_id: number; qty: number; line_total: number }[];
}

export default function Returns() {
  const st = useStore();
  const [kind, setKind] = useState('');
  const [rows, setRows] = useState<RetRow[]>([]);
  const [custOpen, setCustOpen] = useState(false);
  const [supOpen, setSupOpen] = useState(false);

  const load = () => api.get<RetRow[]>(`/api/returns${kind ? `?kind=${kind}` : ''}`).then(setRows).catch(e => st.toast(e.message, 'bad'));
  useEffect(() => { load(); }, [kind]); // eslint-disable-line

  return (
    <div>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Returns</h2>
        <div className="row">
          <select value={kind} onChange={e => setKind(e.target.value)}>
            <option value="">All types</option><option value="customer">Customer returns</option><option value="supplier">Supplier returns</option>
          </select>
          {st.can('sale.return') && <button className="primary" onClick={() => setCustOpen(true)}>Customer return</button>}
          {st.can('purchase.create') && <button onClick={() => setSupOpen(true)}>Supplier return</button>}
        </div>
      </div>
      <table>
        <thead><tr><th>Ref</th><th>Type</th><th>Against</th><th>Items</th><th>Reason</th><th className="right">Amount</th><th>When</th></tr></thead>
        <tbody>{rows.map(r => (
          <tr key={r.id}>
            <td><b>{r.ref}</b></td>
            <td><StatusBadge s={r.kind === 'customer' ? 'Customer' : 'Supplier'} /></td>
            <td>{r.kind === 'customer' ? `Sale #${r.sale_id}` : `Purchase #${r.purchase_id}`}</td>
            <td>{r.items.length}</td>
            <td className="muted">{r.reason || '—'}</td>
            <td className="right">{st.money(r.total)}</td>
            <td className="muted">{fmtDate(r.at)}</td>
          </tr>
        ))}{!rows.length && <tr><td colSpan={7} className="muted">No returns recorded.</td></tr>}</tbody>
      </table>
      {custOpen && <CustomerReturn onClose={() => setCustOpen(false)} onDone={() => { setCustOpen(false); load(); }} />}
      {supOpen && <SupplierReturn onClose={() => setSupOpen(false)} onDone={() => { setSupOpen(false); load(); }} />}
    </div>
  );
}

function CustomerReturn({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [q, setQ] = useState('');
  const [sale, setSale] = useState<SaleOut | null>(null);
  const [qtys, setQtys] = useState<Record<number, number>>({});
  const [reason, setReason] = useState('');
  const [method, setMethod] = useState('cash');
  const [condition, setCondition] = useState('good');
  const [accounts, setAccounts] = useState<any[]>([]);
  const [accountId, setAccountId] = useState(0);
  useEffect(() => { api.get<any[]>('/api/accounts').then(a => { setAccounts(a); setAccountId(a[0]?.id ?? 0); }).catch(() => {}); }, []);

  const findSale = async () => {
    try {
      const list = await api.get<SaleOut[]>(`/api/sales?q=${encodeURIComponent(q)}&limit=10`);
      if (!list.length) return st.toast('No matching sale found.', 'bad');
      setSale(list[0]);
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  const submit = async () => {
    if (!sale) return;
    const items = sale.items
      .map(i => ({ sale_item_id: i.id, qty: qtys[i.id] ?? 0 }))
      .filter(i => i.qty > 0);
    if (!items.length) return st.toast('Enter quantity to return for at least one item.', 'bad');
    if (!reason.trim()) return st.toast('A reason is required.', 'bad');
    try {
      const r = await api.post<{ ref: string; total: number }>(`/api/pos/sales/${sale.id}/return`,
        { items, reason, refund_method: method, account_id: accountId || undefined, stock_condition: condition });
      st.toast(`Return ${r.ref} recorded (${st.money(r.total)}). Stock and balances updated.`, 'ok');
      onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return (
    <Modal title="Customer return" onClose={onClose} width={560}>
      {!sale ? <>
        <Field label="Original sale reference (e.g. SALE-20260928-000005)">
          <div className="row"><input autoFocus value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && findSale()} placeholder="Scan or type sale ref…" />
            <button className="primary" onClick={findSale}>Find</button></div>
        </Field>
      </> : <>
        <p><b>{sale.ref}</b> — {sale.customer} · {st.money(sale.grand_total)} · <StatusBadge s={sale.status} /></p>
        <table>
          <thead><tr><th>Product</th><th>Sold</th><th>Return qty</th></tr></thead>
          <tbody>{sale.items.map(i => (
            <tr key={i.id}><td>#{i.product_id}</td><td>{i.qty}</td>
              <td><input type="number" min={0} max={i.qty} style={{ width: 80 }} value={qtys[i.id] ?? 0}
                onChange={e => setQtys({ ...qtys, [i.id]: Number(e.target.value) })} /></td></tr>
          ))}</tbody>
        </table>
        <div className="row" style={{ gap: 10 }}>
          <Field label="Reason"><input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. wrong item" /></Field>
          <Field label="Refund method">
            <select value={method} onChange={e => setMethod(e.target.value)}>
              <option value="cash">Cash</option><option value="credit">Credit to Khata</option><option value="none">No refund (exchange)</option>
            </select>
          </Field>
          <Field label="Stock condition">
            <select value={condition} onChange={e => setCondition(e.target.value)}>
              <option value="good">Good (restock)</option><option value="damaged">Damaged</option><option value="expired">Expired</option>
            </select>
          </Field>
          {method === 'cash' && <Field label="Refund from">
            <select value={accountId} onChange={e => setAccountId(Number(e.target.value))}>{accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
          </Field>}
        </div>
      </>}
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
        <button onClick={onClose}>Cancel</button>
        {sale && <button className="primary" onClick={submit}>Record return</button>}
      </div>
    </Modal>
  );
}

function SupplierReturn({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [pur, setPur] = useState<Purchase | null>(null);
  const [qtys, setQtys] = useState<Record<number, number>>({});
  const [reason, setReason] = useState('');
  const [resolution, setResolution] = useState('supplier_credit');
  const [condition, setCondition] = useState('damaged');
  const purchases = usePurchases();

  const submit = async () => {
    if (!pur) return st.toast('Choose the original purchase first.', 'bad');
    const items = pur.items.map(i => ({ purchase_item_id: i.id, qty: qtys[i.id] ?? 0 })).filter(i => i.qty > 0);
    if (!items.length) return st.toast('Enter quantity for at least one item.', 'bad');
    if (!reason.trim()) return st.toast('A reason is required.', 'bad');
    try {
      const r = await api.post<{ ref: string; total: number }>(`/api/purchases/${pur.id}/return`,
        { items, reason, resolution, condition });
      st.toast(`Supplier return ${r.ref} recorded (${st.money(r.total)}).`, 'ok');
      onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return (
    <Modal title="Supplier return" onClose={onClose} width={560}>
      <Field label="Original purchase">
        <select value={pur?.id ?? 0} onChange={e => setPur(purchases.find(p => p.id === Number(e.target.value)) ?? null)}>
          <option value={0}>— select purchase —</option>
          {purchases.map(p => <option key={p.id} value={p.id}>{p.ref} · {st.money(p.grand_total)} · {fmtDate(p.created_at)}</option>)}
        </select>
      </Field>
      {pur && <table>
        <thead><tr><th>Item</th><th>Received</th><th>Return qty</th></tr></thead>
        <tbody>{pur.items.map(i => (
          <tr key={i.id}><td>Product #{i.product_id} @ {st.money(i.cost_price)}</td><td>{i.qty_received}</td>
            <td><input type="number" min={0} max={i.qty_received} style={{ width: 80 }} value={qtys[i.id] ?? 0}
              onChange={e => setQtys({ ...qtys, [i.id]: Number(e.target.value) })} /></td></tr>
        ))}</tbody>
      </table>}
      <div className="row" style={{ gap: 10 }}>
        <Field label="Reason"><input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. expired batch" /></Field>
        <Field label="Resolution">
          <select value={resolution} onChange={e => setResolution(e.target.value)}>
            <option value="supplier_credit">Supplier credit</option><option value="refund">Cash refund</option><option value="replacement">Replacement</option>
          </select>
        </Field>
        <Field label="Condition">
          <select value={condition} onChange={e => setCondition(e.target.value)}>
            <option value="damaged">Damaged</option><option value="expired">Expired</option><option value="wrong">Wrong item</option>
          </select>
        </Field>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end' }}><button onClick={onClose}>Cancel</button><button className="primary" onClick={submit}>Record return</button></div>
    </Modal>
  );
}

function usePurchases(): Purchase[] {
  const [rows, setRows] = useState<Purchase[]>([]);
  useEffect(() => { api.get<Purchase[]>('/api/purchases?limit=100').then(setRows).catch(() => {}); }, []);
  return rows;
}
