// POS billing counter (spec #10–#14): barcode search, cart, discount limit check,
// split cash/credit payments, printable receipt + WhatsApp send.
import React, { useEffect, useRef, useState } from 'react';
import { api, Product, Customer, SaleOut } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced } from '../components/ui';

interface Line { product: Product; qty: number; price: number; free: number }

export default function POS() {
  const st = useStore();
  const [q, setQ] = useState('');
  const [cart, setCart] = useState<Line[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [discount, setDiscount] = useState(0);
  const [done, setDone] = useState<SaleOut | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const found = useDebounced(() => q.trim() ? api.get<Product[]>(`/api/products/search?q=${encodeURIComponent(q)}`) : Promise.resolve([] as Product[]), [q]);
  const results = (found.data || []).filter(p => p.is_active).slice(0, 8);

  const add = (p: Product) => {
    setCart(c => {
      const ex = c.find(l => l.product.id === p.id);
      if (ex) return c.map(l => l.product.id === p.id ? { ...l, qty: l.qty + 1 } : l);
      return [...c, { product: p, qty: 1, price: p.retail_price, free: 0 }];
    });
    setQ(''); inputRef.current?.focus();
  };
  const setQty = (id: number, qty: number) => setCart(c => c.map(l => l.product.id === id ? { ...l, qty: Math.max(0.001, qty) } : l));
  const rm = (id: number) => setCart(c => c.filter(l => l.product.id !== id));

  const subtotal = cart.reduce((s, l) => s + l.qty * l.price, 0);
  const discAmt = Math.min(discount, subtotal);
  const total = Math.max(0, subtotal - discAmt);
  const maxDiscPct = st.user?.max_discount_percent ?? Number(st.settings['pos.max_discount_percent'] ?? 10);
  const discPct = subtotal > 0 ? (discAmt / subtotal) * 100 : 0;
  const discBlocked = discPct > maxDiscPct + 1e-9;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && results.length) { e.preventDefault(); add(results[0]); }
  };

  return <div className="pos">
    <div className="pos-left card">
      <h3 style={{ marginTop: 0 }}>Find products</h3>
      <input ref={inputRef} autoFocus placeholder="Scan barcode or type name / SKU… (Enter adds first match)" value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} style={{ width: '100%' }} />
      <div style={{ maxHeight: 420, overflowY: 'auto', marginTop: 8 }}>
        {results.map(p => (
          <div key={p.id} className="row spread prod-row" onClick={() => add(p)}>
            <div><b>{p.name}</b><div className="muted" style={{ fontSize: 12 }}>{p.unit} · stock {p.stock_qty}{p.barcode ? ` · ${p.barcode}` : ''}</div></div>
            <b>{st.money(p.retail_price)}</b>
          </div>))}
        {!q && <p className="muted">Search to add items — barcodes work with USB scanners too (spec #10).</p>}
        {q && results.length === 0 && <p className="muted">No products match “{q}”.</p>}
      </div>
    </div>
    <div className="pos-right card">
      <h3 style={{ marginTop: 0 }}>Cart ({cart.length})</h3>
      <div style={{ maxHeight: 260, overflowY: 'auto' }}>
        <table><thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th><th /></tr></thead>
          <tbody>{cart.map(l => (
            <tr key={l.product.id}>
              <td>{l.product.name}</td>
              <td><input type="number" min={0} style={{ width: 64 }} value={l.qty} onChange={e => setQty(l.product.id, Number(e.target.value))} /></td>
              <td>{st.money(l.price)}</td><td>{st.money(l.qty * l.price)}</td>
              <td><button onClick={() => rm(l.product.id)}>✕</button></td>
            </tr>))}
            {cart.length === 0 && <tr><td colSpan={5} className="muted">Cart is empty.</td></tr>}
          </tbody></table>
      </div>
      <CustomerPicker customer={customer} setCustomer={setCustomer} />
      <div className="row" style={{ gap: 10, marginTop: 8 }}>
        <Field label={`Discount (${st.settings.currency_symbol || 'Rs'}; max ${maxDiscPct}%)}>
          <input type="number" value={discount || ''} onChange={e => setDiscount(Number(e.target.value) || 0)} style={{ width: 110 }} />
        </Field>
        <div style={{ flex: 1 }} />
      </div>
      {discBlocked && <p style={{ color: 'var(--danger)', fontWeight: 700 }}>⛔ Discount {discPct.toFixed(1)}% exceeds your {maxDiscPct}% limit — owner approval required (spec #36).</p>}
      <div className="row spread" style={{ fontSize: 18, margin: '8px 0' }}><span>Subtotal</span><b>{st.money(subtotal)}</b></div>
      <div className="row spread" style={{ fontSize: 22 }}><span>Total due</span><b>{st.money(total)}</b></div>
      <button className="primary big" disabled={!cart.length || discBlocked || !st.can('sale.create')} onClick={() => setDone(null)}>
        Charge & pay →
      </button>
      <button className="big" style={{ visibility: 'hidden' }} onClick={() => setDone(null)} />
      {/* payment modal opens via below */}
      <PayModal open={payOpen} setOpen={setPayOpen} cart={cart} total={total} discAmt={discAmt} subtotal={subtotal} customer={customer} discount={discount} onDone={(s) => { setCart([]); setDiscount(0); setCustomer(null); setDone(s); }} />
      <div className="row" style={{ justifyContent: 'center', marginTop: -46 }}><span /></div>
    </div>
    {done && <ReceiptModal sale={done} onClose={() => setDone(null)} />}
  </div>;

  // hacky-free state: keep payOpen in component
  function noop() {}
}

// separate state hook usage requires top-level; restructure with a wrapper below.
let payOpen = false; let setPayOpen: (v: boolean) => void = () => {};
