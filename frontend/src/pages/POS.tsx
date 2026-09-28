// POS billing counter (spec #7-#14, #57): barcode-scan fast add, live search with keyboard
// nav, quantity prompt on manual pick, cash/khata/dasti/split payments, discount limits +
// manager approval, hold/resume, printable receipt + WhatsApp send.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api, fmtMoney, type Product, type Customer, type Account, type SaleOut } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced } from '../components/ui';

interface Line { product: Product; qty: number; price: number; discount: number }
interface PayLine { accountId: number; amount: number }

const num = (v: unknown) => Math.round(Number(v ?? 0) * 100) / 100;
let accountsCache: Account[] | undefined;   // fetched once per session, reused by pay/dasti modals

export default function POS() {
  const st = useStore();
  const money = (v: number | null | undefined) => fmtMoney(v, st.settings);
  const [q, setQ] = useState('');
  const [cart, setCart] = useState<Line[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [extraDisc, setExtraDisc] = useState(0);
  const [done, setDone] = useState<SaleOut | null>(null);
  const [payOpen, setPayOpen] = useState(false);
  const [dastiOpen, setDastiOpen] = useState(false);
  const [heldOpen, setHeldOpen] = useState(false);
  const [custOpen, setCustOpen] = useState(false);
  const [qtyAsk, setQtyAsk] = useState<Product | null>(null);
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // ---- settings that actually drive behavior (spec #71) ----
  const askQtyOnManual = st.settings['pos.ask_quantity_on_manual_add'] !== 'false';
  const shortcuts: Record<string, string> = useMemo(() => {
    try { return st.settings['pos.shortcuts'] ? JSON.parse(st.settings['pos.shortcuts']) : {}; } catch { return {}; }
  }, [st.settings]);
  const sc = (action: string, fallback: string) => (shortcuts[action] || fallback).toLowerCase();

  const found = useDebounced(
    () => q.trim() ? api.get<Product[]>(`/api/products/search?q=${encodeURIComponent(q.trim())}&limit=12`) : Promise.resolve([] as Product[]),
    [q]);
  const results = (found.data || []).slice(0, 12);

  // ---- cart ops ----
  const addProduct = (p: Product, askQty: boolean) => {
    if (askQty) { setQtyAsk(p); return; }
    setCart(c => {
      const ex = c.find(l => l.product.id === p.id);
      if (ex) return c.map(l => l.product.id === p.id ? { ...l, qty: num(l.qty + 1) } : l);
      return [...c, { product: p, qty: 1, price: p.retail_price || 0, discount: 0 }];
    });
    setQ(''); setSel(0); inputRef.current?.focus();
  };
  const setQty = (id: number, qty: number) => setCart(c => c.map(l => l.product.id === id ? { ...l, qty: Math.max(0, num(qty)) } : l).filter(l => l.qty > 0));
  const setPrice = (id: number, price: number) => setCart(c => c.map(l => l.product.id === id ? { ...l, price: Math.max(0, price) } : l));
  const setLineDisc = (id: number, d: number) => setCart(c => c.map(l => l.product.id === id ? { ...l, discount: Math.max(0, d) } : l));
  const rm = (id: number) => setCart(c => c.filter(l => l.product.id !== id));
  const clearAll = () => { setCart([]); setExtraDisc(0); setCustomer(null); inputRef.current?.focus(); };

  // ---- barcode scanner detection (spec #7): HID scanners type fast + end with Enter ----
  const keys = useRef<{ t: number }[]>([]);
  const lastKey = useRef(0);
  const onSearchKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const typed = q.trim();
      const gap = performance.now() - lastKey.current;
      const dense = keys.current.length >= 5 && (keys.current[keys.current.length - 1].t - keys.current[0].t) < 300;
      const isScan = /^\d{8,}$/.test(typed) && (dense || gap > 4000);
      keys.current = [];
      if (isScan && typed) {
        api.get<Product[]>(`/api/products/search?q=${typed}&limit=1`).then(r => {
          if (r.length) addProduct(r[0], false);           // auto-add x1, NO popup (spec #7)
          else st.toast(`No product with barcode ${typed}. Nothing added to the cart.`, 'bad');
        });
        setQ('');
        return;
      }
      if (results.length) addProduct(results[Math.min(sel, results.length - 1)], askQtyOnManual);
      return;
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, results.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); }
    if (e.key === 'Escape') { setQ(''); setSel(0); }
    if (e.key.length === 1) { keys.current.push({ t: performance.now() }); if (keys.current.length > 40) keys.current.shift(); }
    lastKey.current = performance.now();
  };

  const subtotal = cart.reduce((s, l) => s + l.qty * l.price, 0);
  const lineDisc = cart.reduce((s, l) => s + Math.min(l.discount, l.qty * l.price), 0);
  const discTotal = Math.min(lineDisc + extraDisc, subtotal);
  const taxPct = st.settings['tax.enabled'] === 'true' ? Number(st.settings['tax.percent'] || 0) : 0;
  const tax = Math.round((subtotal - discTotal) * taxPct) / 100;
  const total = Math.max(0, Math.round((subtotal - discTotal + tax) * 100) / 100);
  const maxDiscPct = st.user?.max_discount_percent != null ? Number(st.user.max_discount_percent) : Number(st.settings['pos.max_discount_percent'] ?? 10);
  const discPct = subtotal > 0 ? (discTotal / subtotal) * 100 : 0;
  const discOverLimit = discPct > maxDiscPct + 1e-9;
  const apprThreshold = Number(st.settings['approval.discount_percent'] || 0);
  const needsApproval = apprThreshold > 0 && discPct >= apprThreshold;

  const payload = (payments: PayLine[], creditMode: string, dasti?: Record<string, unknown>) => ({
    items: cart.map(l => ({ product_id: l.product.id, qty: l.qty, unit_price: l.price, discount: l.discount })),
    customer_id: customer?.id ?? null,
    payments: payments.filter(p => p.amount > 0).map(p => ({ account_id: p.accountId, amount: p.amount })),
    credit_mode: creditMode,
    dasti: dasti ?? null,
    extra_discount: extraDisc,
    notes: '',
  });

  const complete = async (payments: PayLine[], creditMode: string, dasti?: Record<string, unknown>) => {
    setBusy(true);
    const body = payload(payments, creditMode, dasti);
    try {
      let s: SaleOut;
      if (needsApproval && !st.can('approval.grant')) {
        const res = await api.post<any>('/api/pos/sales/request-approval?total_estimate=' + total, body);
        if (res.approved_inline && res.sale) s = res.sale;
        else { st.toast(`Discount queued for approval (#${res.approval_id}). The sale was NOT completed - an owner/manager must approve it.`, 'info'); setBusy(false); return; }
      } else {
        s = await api.post<SaleOut>('/api/pos/sales', body);
      }
      setDone(s); setPayOpen(false); setDastiOpen(false); setCart([]); setExtraDisc(0); setCustomer(null);
      st.toast(`Sale ${s.ref} completed - ${money(s.grand_total)}`, 'ok');
    } catch (e: any) {
      if (e.status === 409 && String(e.message).includes('APPROVAL_REQUIRED')) {
        const res = await api.post<any>('/api/pos/sales/request-approval?total_estimate=' + total, body).catch(() => null);
        if (res?.approved_inline && res.sale) { setDone(res.sale); setPayOpen(false); setCart([]); setExtraDisc(0); setCustomer(null); }
        else st.toast(res ? `Sale queued for approval #${res.approval_id}. Nothing was charged.` : 'Approval required but could not be requested.', 'info');
      } else {
        st.toast(`${e.message}${e.committed ? '' : ' (Nothing was changed - stock and cash are untouched.)'}`, 'bad');
      }
    } finally { setBusy(false); inputRef.current?.focus(); }
  };

  const holdSale = async () => {
    if (!cart.length) return;
    try {
      const r = await api.post<{ id: number; ref: string }>('/api/pos/hold', {
        cart: cart.map(l => ({ product_id: l.product.id, name: l.product.name, qty: l.qty, price: l.price, discount: l.discount })),
        customer_id: customer?.id ?? null, notes: '',
      });
      st.toast(`Sale held as ${r.ref}`, 'ok'); clearAll();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  // ---- global F-key shortcuts (spec #57) ----
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!/^F\d{1,2}$/.test(e.key)) return;
      const map: Record<string, () => void> = {
        [sc('search', 'F1')]: () => inputRef.current?.focus(),
        [sc('customer', 'F2')]: () => setCustOpen(true),
        [sc('hold', 'F4')]: () => holdSale(),
        [sc('resume', 'F5')]: () => setHeldOpen(true),
        [sc('payment', 'F6')]: () => { if (cart.length) setPayOpen(true); },
        [sc('new_sale', 'F7')]: () => clearAll(),
        [sc('print', 'F9')]: () => done && window.print(),
      };
      const fn = map[e.key.toLowerCase()];
      if (fn) { e.preventDefault(); fn(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart, done, st.settings]);

  return <div className="pos">
    <div className="card pos-left">
      <h3 style={{ marginTop: 0 }}>Find products</h3>
      <input ref={inputRef} autoFocus placeholder="Scan barcode or type name / SKU / brand... arrows then Enter"
        value={q} onChange={e => { setQ(e.target.value); setSel(0); }} onKeyDown={onSearchKey} style={{ width: '100%' }} />
      <div style={{ maxHeight: 460, overflowY: 'auto', marginTop: 8 }}>
        {results.map((p, i) => (
          <div key={p.id} className={'row spread prod-row' + (i === sel ? ' sel' : '')}
            onClick={() => addProduct(p, askQtyOnManual)} style={{ cursor: 'pointer', padding: 8, borderBottom: '1px solid var(--line)' }}>
            <div><b>{p.name}</b><div className="muted" style={{ fontSize: 12 }}>
              {p.unit} · stock {p.stock_qty}{p.barcode ? ` · ${p.barcode}` : ''}{p.category ? ` · ${p.category}` : ''}</div></div>
            <b>{money(p.retail_price)}</b>
          </div>))}
        {!q && <p className="muted">USB barcode scanners work directly (scan = add x1, no popup). Shortcuts: F1 search · F2 customer · F4 hold · F5 resume · F6 payment · F7 new sale.</p>}
        {q && !found.loading && results.length === 0 && <p className="muted">No products match "{q}". Add them under Products first.</p>}
      </div>
    </div>

    <div className="card pos-cart">
      <div className="row spread"><h3 style={{ margin: 0 }}>Cart ({cart.length})</h3>
        <div className="row" style={{ gap: 6 }}>
          <button onClick={() => setHeldOpen(true)}>Resume held</button>
          <button onClick={clearAll}>New sale</button>
        </div></div>
      <div className="cart-lines" style={{ maxHeight: 300, overflowY: 'auto', marginTop: 6 }}>
        {cart.map(l => (
          <div key={l.product.id} className="row" style={{ gap: 6, alignItems: 'center', borderBottom: '1px solid var(--line)', padding: '6px 0' }}>
            <div style={{ flex: 2 }}><b>{l.product.name}</b><div className="muted" style={{ fontSize: 11 }}>{l.product.unit} · stock {l.product.stock_qty}</div></div>
            <input type="number" min={0} step="any" style={{ width: 70 }} value={l.qty} onChange={e => setQty(l.product.id, Number(e.target.value))} title="Quantity" />
            {st.can('price.change')
              ? <input type="number" min={0} step="any" style={{ width: 84 }} value={l.price} onChange={e => setPrice(l.product.id, Number(e.target.value))} title="Unit price" />
              : <span style={{ width: 84 }}>{money(l.price)}</span>}
            {st.can('discount.apply') && <input type="number" min={0} placeholder="disc" style={{ width: 64 }} value={l.discount || ''} onChange={e => setLineDisc(l.product.id, Number(e.target.value) || 0)} title="Line discount" />}
            <span style={{ width: 90, textAlign: 'right' }}>{money(Math.max(0, l.qty * l.price - l.discount))}</span>
            <button onClick={() => rm(l.product.id)} aria-label="Remove">✕</button>
          </div>))}
        {cart.length === 0 && <p className="muted">Cart is empty - scan or search to add items.</p>}
      </div>

      <div className="row" style={{ gap: 10, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={() => setCustOpen(true)}>👤 {customer ? customer.name : 'Walk-in customer'}</button>
        {st.can('discount.apply') && <label className="muted" style={{ fontSize: 13 }}>Sale discount
          <input type="number" min={0} value={extraDisc || ''} onChange={e => setExtraDisc(Number(e.target.value) || 0)} style={{ width: 100, marginLeft: 6 }} /></label>}
      </div>

      <div className="totals">
        <div className="row spread"><span>Subtotal</span><b>{money(subtotal)}</b></div>
        <div className="row spread"><span>Discount {discPct > 0 ? `(${discPct.toFixed(1)}%)` : ''}</span><b>-{money(discTotal)}</b></div>
        {taxPct > 0 && <div className="row spread"><span>Tax {taxPct}%</span><b>{money(tax)}</b></div>}
        <div className="row spread grand"><span>Grand Total</span><b>{money(total)}</b></div>
      </div>

      {discOverLimit && <p style={{ color: 'var(--danger)', fontWeight: 700 }}>⛔ Discount {discPct.toFixed(1)}% exceeds your {maxDiscPct}% limit - the server will reject this sale (spec #35).</p>}
      {!discOverLimit && needsApproval && <p style={{ fontWeight: 700, color: '#b8860b' }}>⏳ Discount meets the {apprThreshold}% approval threshold - a manager can approve at the counter, otherwise it queues for the owner (spec #36).</p>}

      <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <button className="primary big" disabled={!cart.length || discOverLimit || busy || !st.can('sale.create')} onClick={() => setPayOpen(true)}>💰 Complete sale</button>
        <button disabled={!cart.length || busy || !customer || !st.can('khata.create')} onClick={() => complete([], 'khata')} title="Full credit to customer Khata ledger">📒 Khata (credit)</button>
        <button disabled={!cart.length || busy || st.settings['payments.dasti'] === 'false' || !st.can('dasti.create')} onClick={() => setDastiOpen(true)}>🤝 Dasti</button>
        <button disabled={!cart.length || busy} onClick={holdSale}>⏸ Hold</button>
        <button className="danger" disabled={!cart.length} onClick={clearAll}>Cancel</button>
      </div>
    </div>

    {qtyAsk && <QtyModal product={qtyAsk} onCancel={() => { setQtyAsk(null); inputRef.current?.focus(); }}
      onAdd={(qty) => {
        setCart(c => {
          const ex = c.find(l => l.product.id === qtyAsk.id);
          if (ex) return c.map(l => l.product.id === qtyAsk.id ? { ...l, qty: num(l.qty + qty) } : l);
          return [...c, { product: qtyAsk, qty, price: qtyAsk.retail_price || 0, discount: 0 }];
        });
        setQtyAsk(null); setQ(''); inputRef.current?.focus();
      }} />}

    {payOpen && <PayModal total={total} money={money} busy={busy}
      allowCash={st.settings['payments.cash'] !== 'false'} allowBank={st.settings['payments.bank'] !== 'false'} allowWallet={st.settings['payments.wallet'] !== 'false'}
      khataAllowed={!!customer && st.can('khata.create')}
      onClose={() => setPayOpen(false)} onComplete={complete} />}

    {dastiOpen && <DastiModal money={money} total={total} busy={busy} customer={customer}
      onClose={() => setDastiOpen(false)}
      onComplete={(partial, dasti) => complete(partial, 'dasti', dasti)} />}

    {custOpen && <CustomerModal onClose={() => setCustOpen(false)} onPick={(c) => { setCustomer(c); setCustOpen(false); }} />}

    {heldOpen && <HeldModal onClose={() => setHeldOpen(false)} onResume={(items) => { setCart(items); setHeldOpen(false); inputRef.current?.focus(); }} />}

    {done && <ReceiptModal sale={done} onClose={() => { setDone(null); inputRef.current?.focus(); }} />}
  </div>;
}

function QtyModal({ product, onCancel, onAdd }: { product: Product; onCancel: () => void; onAdd: (q: number) => void }) {
  const st = useStore();
  const [qty, setQty] = useState('1');
  return <Modal title="Quantity" onClose={onCancel} width={340}>
    <p><b>{product.name}</b><br /><span className="muted">Unit: {product.unit} · Price: {st.money(product.retail_price)} · Stock: {product.stock_qty}</span></p>
    <input autoFocus type="number" min={0} step="any" value={qty} style={{ width: '100%', fontSize: 22 }}
      onChange={e => setQty(e.target.value)}
      onKeyDown={e => { if (e.key === 'Enter' && Number(qty) > 0) onAdd(Number(qty)); }} />
    <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
      <button onClick={onCancel}>Cancel</button>
      <button className="primary" disabled={!(Number(qty) > 0)} onClick={() => onAdd(Number(qty))}>Add</button>
    </div>
  </Modal>;
}

function PayModal({ total, money, busy, allowCash, allowBank, allowWallet, khataAllowed, onClose, onComplete }: {
  total: number; money: (v: number) => string; busy: boolean;
  allowCash: boolean; allowBank: boolean; allowWallet: boolean; khataAllowed: boolean;
  onClose: () => void;
  onComplete: (pays: PayLine[], mode: string) => void;
}) {
  const [accts, setAccts] = useState<Account[] | null>(accountsCache ?? null);
  const [mainAcc, setMainAcc] = useState<number | null>(null);
  const [tendered, setTendered] = useState('');
  const [split, setSplit] = useState(false);
  const [lines, setLines] = useState<PayLine[]>([]);
  useEffect(() => {
    if (!accts) api.get<Account[]>('/api/accounts').then(a => { accountsCache = a; setAccts(a); }).catch(() => setAccts([]));
  }, [accts]);
  const usable = (accts || []).filter(a => a.is_active && (
    (a.type === 'cash' && allowCash) || (a.type === 'bank' && allowBank) || (a.type === 'wallet' && allowWallet)));
  useEffect(() => { if (mainAcc === null && usable.length) setMainAcc((usable.find(a => a.is_default_sale) || usable[0]).id); }, [accts]); // eslint-disable-line
  const paidSplit = lines.reduce((s, l) => s + (l.amount || 0), 0);
  const tenderAmt = Number(tendered || 0);
  const paidSingle = tenderAmt > 0 ? Math.min(tenderAmt, total) : 0;
  const paid = split ? Math.min(paidSplit, total) : paidSingle;
  const remaining = Math.max(0, Math.round((total - paid) * 100) / 100);
  const change = !split && tenderAmt > total ? Math.round((tenderAmt - total) * 100) / 100 : 0;

  const finish = (mode: string) => {
    let pays: PayLine[];
    if (split) pays = lines.filter(l => l.amount > 0);
    else if (mainAcc != null && paid > 0) pays = [{ accountId: mainAcc, amount: paid }];
    else pays = [];
    onComplete(pays, mode);
  };

  return <Modal title={`Payment - ${money(total)}`} onClose={onClose} width={470}>
    {!accts ? <p className="muted">Loading payment accounts...</p> : usable.length === 0
      ? <p style={{ color: 'var(--danger)' }}>No enabled payment accounts. Enable Cash/Bank/Wallet under Settings and create accounts first.</p>
      : <>
        {!split && <>
          <Field label="Account">
            <select value={mainAcc ?? ''} onChange={e => setMainAcc(Number(e.target.value))} style={{ width: '100%' }}>
              {usable.map(a => <option key={a.id} value={a.id}>{a.name} ({a.type})</option>)}
            </select></Field>
          <Field label="Cash tendered (change calculated automatically)">
            <input type="number" min={0} step="any" autoFocus value={tendered} onChange={e => setTendered(e.target.value)} style={{ width: '100%', fontSize: 20 }} /></Field>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <button onClick={() => setTendered(String(total))}>Exact</button>
            {[100, 500, 1000, 1500, 2000, 5000].map(v => <button key={v} onClick={() => setTendered(String(Math.round(((Number(tendered) || 0) + v) * 100) / 100))}>+{v}</button>)}
          </div>
        </>}
        {split && <div>
          {lines.map((l, i) => <div key={i} className="row" style={{ gap: 6, marginTop: 6 }}>
            <select value={l.accountId} onChange={e => setLines(ls => ls.map((x, j) => j === i ? { ...x, accountId: Number(e.target.value) } : x))}>
              {usable.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <input type="number" min={0} step="any" value={l.amount || ''} onChange={e => setLines(ls => ls.map((x, j) => j === i ? { ...x, amount: Number(e.target.value) || 0 } : x))} style={{ width: 120 }} />
            <button onClick={() => setLines(ls => ls.filter((_, j) => j !== i))}>✕</button>
          </div>)}
          <button style={{ marginTop: 6 }} onClick={() => setLines(ls => [...ls, { accountId: usable[0]?.id ?? 0, amount: 0 }])}>+ Add split line</button>
        </div>}
        <div className="row spread" style={{ marginTop: 10 }}><span>Paid</span><b>{money(paid)}</b></div>
        <div className="row spread"><span>Remaining</span><b>{money(remaining)}</b></div>
        {change > 0 && <div className="row spread"><span>Change to give</span><b style={{ color: 'green' }}>{money(change)}</b></div>}

        <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button className="primary big" disabled={busy || paid < total - 0.004 || !mainAcc} onClick={() => finish('none')}>✔ Full payment</button>
          {khataAllowed && remaining > 0.004 &&
            <button disabled={busy} onClick={() => finish('khata')}>📒 Pay {money(paid)} · rest to Khata</button>}
          <button onClick={() => { setSplit(s => !s); if (!split && !lines.length) setLines([{ accountId: usable[0]?.id ?? 0, amount: 0 }]); }}>{split ? 'Single payment' : 'Split payment'}</button>
        </div>
        <p className="muted" style={{ fontSize: 12 }}>If anything fails, nothing is saved - stock and cash stay untouched (spec #58).</p>
      </>}
  </Modal>;
}

function DastiModal({ money, total, busy, customer, onClose, onComplete }: {
  money: (v: number) => string; total: number; busy: boolean;
  customer: Customer | null; onClose: () => void;
  onComplete: (partial: PayLine[], dasti: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState(customer?.name ?? '');
  const [phone, setPhone] = useState(customer?.phone ?? '');
  const [dueDays, setDueDays] = useState('1');
  const [notes, setNotes] = useState('');
  const [partial, setPartial] = useState('0');
  const [accts, setAccts] = useState<Account[]>(accountsCache?.filter(x => x.is_active) ?? []);
  const [acc, setAcc] = useState<number | null>(null);
  useEffect(() => {
    if (!accts.length) api.get<Account[]>('/api/accounts').then(a => {
      accountsCache = a; setAccts(a.filter(x => x.is_active));
      const d = a.find(x => x.is_default_sale) || a[0]; if (d) setAcc(d.id);
    }).catch(() => {});
  }, [accts.length]);
  const part = Number(partial || 0);
  return <Modal title={`Dasti - temporary credit ${money(total)}`} onClose={onClose} width={440}>
    <p className="muted" style={{ fontSize: 13 }}>Dasti is short-term credit with a due date. Payments never erase the original record (spec #15).</p>
    <Field label="Customer name (optional)"><input value={name} onChange={e => setName(e.target.value)} style={{ width: '100%' }} /></Field>
    <Field label="Phone (optional - enables WhatsApp reminders)"><input value={phone} onChange={e => setPhone(e.target.value)} style={{ width: '100%' }} /></Field>
    <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
      <Field label="Due in days"><input type="number" min={0} value={dueDays} onChange={e => setDueDays(e.target.value)} style={{ width: 90 }} /></Field>
      <Field label="Paid now (optional)"><input type="number" min={0} max={total} step="any" value={part || ''} onChange={e => setPartial(e.target.value)} style={{ width: 120 }} /></Field>
      {part > 0 && <Field label="From account">
        <select value={acc ?? ''} onChange={e => setAcc(Number(e.target.value))}><option value="">-</option>{accts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>}
    </div>
    <Field label="Notes"><input value={notes} onChange={e => setNotes(e.target.value)} style={{ width: '100%' }} /></Field>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={busy || (part > 0 && acc == null)}
        onClick={() => onComplete(part > 0 && acc != null ? [{ accountId: acc, amount: Math.min(part, total) }] : [],
          { customer_name: name, phone, due_days: Number(dueDays) || 1, notes })}>Create Dasti sale</button>
    </div>
  </Modal>;
}

function CustomerModal({ onClose, onPick }: { onClose: () => void; onPick: (c: Customer | null) => void }) {
  const st = useStore();
  const [q, setQ] = useState('');
  const found = useDebounced(() => api.get<Customer[]>(`/api/customers?q=${encodeURIComponent(q)}&limit=30`), [q]);
  const [creating, setCreating] = useState(false);
  const [nf, setNf] = useState({ name: '', phone: '', credit_limit: '', opening_balance: '' });
  const create = async () => {
    if (!nf.name.trim()) { st.toast('Name required', 'bad'); return; }
    try {
      const c = await api.post<Customer>('/api/customers', {
        name: nf.name.trim(), phone: nf.phone, alt_phone: '', address: '', notes: '',
        credit_limit: Number(nf.credit_limit || 0), opening_balance: Number(nf.opening_balance || 0),
        is_khata: true, whatsapp_enabled: !!nf.phone,
      });
      st.toast(`Customer ${c.name} created`, 'ok'); onPick(c);
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title="Select customer" onClose={onClose} width={480}>
    {!creating ? <>
      <input autoFocus placeholder="Search name or phone..." value={q} onChange={e => setQ(e.target.value)} style={{ width: '100%' }} />
      <div style={{ maxHeight: 300, overflowY: 'auto', marginTop: 8 }}>
        <div className="row spread clickable" style={{ padding: 8 }} onClick={() => onPick(null)}><b>🚶 Walk-in (no customer)</b><span className="muted">default</span></div>
        {(found.data || []).map(c => (
          <div key={c.id} className="row spread clickable" style={{ padding: 8, borderBottom: '1px solid var(--line)' }} onClick={() => onPick(c)}>
            <div><b>{c.name}</b><div className="muted" style={{ fontSize: 12 }}>{c.phone || 'no phone'}{c.is_khata ? ' · Khata' : ''}</div></div>
            {c.balance != null && <b>{st.money(c.balance)}</b>}
          </div>))}
      </div>
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 10 }}>
        {st.can('customer.create') ? <button onClick={() => setCreating(true)}>+ New customer</button> : <span />}
        <button onClick={onClose}>Close</button>
      </div>
    </> : <>
      <Field label="Name *"><input autoFocus value={nf.name} onChange={e => setNf({ ...nf, name: e.target.value })} style={{ width: '100%' }} /></Field>
      <Field label="Phone"><input value={nf.phone} onChange={e => setNf({ ...nf, phone: e.target.value })} style={{ width: '100%' }} /></Field>
      <div className="row" style={{ gap: 10 }}>
        <Field label="Credit limit"><input type="number" value={nf.credit_limit} onChange={e => setNf({ ...nf, credit_limit: e.target.value })} style={{ width: 120 }} /></Field>
        <Field label="Opening balance"><input type="number" value={nf.opening_balance} onChange={e => setNf({ ...nf, opening_balance: e.target.value })} style={{ width: 120 }} /></Field>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={() => setCreating(false)}>Back</button>
        <button className="primary" onClick={create}>Save &amp; select</button>
      </div>
    </>}
  </Modal>;
}

function HeldModal({ onClose, onResume }: { onClose: () => void; onResume: (items: Line[]) => void }) {
  const st = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api.get<any[]>('/api/pos/held').then(setRows).catch(() => {}).finally(() => setLoading(false)); }, []);
  const resume = async (h: any) => {
    try {
      const r = await api.post<{ cart: any[] }>(`/api/pos/hold/${h.id}/resume`, {});
      const raw: any[] = r.cart || [];
      if (!raw.length) { st.toast('Held cart is empty.', 'info'); return; }
      // re-fetch products so prices/stock are current
      const all = await api.get<Product[]>('/api/products/search?q=&limit=500').catch(() => [] as Product[]);
      const items: Line[] = raw.filter(c => c.product_id).map(c => {
        const p = all.find(x => x.id === c.product_id);
        return { product: p || ({ id: c.product_id, name: c.name, unit: '', cost_price: 0, retail_price: c.price, stock_qty: 0, min_stock: 0, is_active: true, track_expiry: false, track_batch: false } as unknown as Product), qty: c.qty, price: c.price, discount: c.discount || 0 };
      });
      onResume(items);
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title="Held sales" onClose={onClose} width={480}>
    {loading && <p className="muted">Loading...</p>}
    {!loading && rows.length === 0 && <p className="muted">No held sales.</p>}
    {rows.map(h => <div key={h.id} className="row spread" style={{ padding: 8, borderBottom: '1px solid var(--line)' }}>
      <div><b>{h.ref}</b><div className="muted" style={{ fontSize: 12 }}>{new Date(h.at).toLocaleString()}</div></div>
      <button className="primary" onClick={() => resume(h)}>Resume</button>
    </div>)}
  </Modal>;
}

function ReceiptModal({ sale, onClose }: { sale: SaleOut; onClose: () => void }) {
  const st = useStore();
  const [sending, setSending] = useState(false);
  const sendWhatsApp = async () => {
    if (!sale.customer_id) { st.toast('Walk-in sale has no phone number.', 'bad'); return; }
    setSending(true);
    try {
      const c = await api.get<Customer>(`/api/customers/${sale.customer_id}`);
      if (!c.phone) { st.toast('This customer has no phone number saved.', 'bad'); return; }
      const r = await api.post<any>('/api/notifications/send', {
        to: c.phone, template: 'sale_receipt',
        message: sale.receipt || `Sale ${sale.ref}: ${fmtMoney(sale.grand_total, st.settings)}. Thank you!`,
        customer_name: c.name });
      st.toast(r.status === 'sent' ? 'Receipt sent on WhatsApp ✔'
        : `Queued with status "${r.status}"${r.error ? ` - ${r.error}` : '. Configure WhatsApp API credentials in Settings to deliver.'}`,
        r.status === 'sent' ? 'ok' : 'info');
    } catch (e: any) { st.toast(e.message, 'bad'); } finally { setSending(false); }
  };
  return <Modal title={`Receipt - ${sale.ref}`} onClose={onClose} width={430}>
    <pre className="mono" style={{ background: 'rgba(127,127,127,.08)', padding: 12, maxHeight: 340, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
      {sale.receipt || `Sale ${sale.ref}\nTotal: ${fmtMoney(sale.grand_total, st.settings)}\nStatus: ${sale.status}`}
    </pre>
    {Number(sale.change_given || 0) > 0 && <p><b>Change given: {st.money(sale.change_given)}</b></p>}
    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
      <button onClick={() => window.open(`/api/pos/sales/${sale.id}/receipt.pdf`, '_blank')}>🖨 PDF</button>
      <button onClick={() => window.print()}>Print</button>
      <button onClick={sendWhatsApp} disabled={sending}>💬 WhatsApp receipt</button>
      <span style={{ flex: 1 }} />
      <button className="primary" onClick={onClose}>New sale</button>
    </div>
    <div className="row" style={{ marginTop: 8, gap: 8 }}>
      <StatusBadge s={sale.status} />
      <span className="muted">{sale.cashier} · {sale.device} · {new Date(sale.created_at).toLocaleString()}</span>
    </div>
  </Modal>;
}
