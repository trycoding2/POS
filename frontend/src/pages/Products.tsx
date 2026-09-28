// Products & catalog management (spec #22/#40): CRUD, live search, price history via timeline.
import React, { useEffect, useState } from 'react';
import { api, type Product } from '../api/client';
import { useStore } from '../store';
import { Modal, Field, StatusBadge, useDebounced, useConfirm } from '../components/ui';

interface Meta { categories: any[]; brands: any[]; units: any[]; default_supplier_id?: number }

export default function Products() {
  const st = useStore();
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<Product[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [editing, setEditing] = useState<Partial<Product> | null>(null);
  const [adjustTarget, setAdjustTarget] = useState<Product | null>(null);
  const [detail, setDetail] = useState<{ product: Product; timeline: any[]; price_history: any[] } | null>(null);
  const [tab, setTab] = useState<'products' | 'catalog'>('products');
  const [confirm, confirmNode] = useConfirm();

  const search = useDebounced(() => q.trim() ? api.get<Product[]>(`/api/products/search?q=${encodeURIComponent(q)}`) : Promise.resolve([] as Product[]), [q]);

  const loadList = () => api.get<Product[]>('/api/products/search?q=').then(setRows).catch(() => {});
  useEffect(() => { loadList(); api.get<Meta>('/api/catalog/meta').then(setMeta).catch(() => {}); }, []); // eslint-disable-line

  const shown = q.trim() ? (search.data || []) : rows;

  const save = async (p: Partial<Product>) => {
    try {
      if (p.id) await api.put(`/api/products/${p.id}`, p); else await api.post('/api/products', p);
      st.toast('Product saved', 'ok'); setEditing(null); loadList();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  const deactivate = async (p: Product) => {
    if (!(await confirm(`Deactivate “${p.name}”? It will no longer appear in POS searches but all history is kept (spec #33 — no hard delete).`))) return;
    try { await api.put(`/api/products/${p.id}`, { is_active: false }); st.toast('Product deactivated', 'ok'); loadList(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };

  const openAdjust = (p: Product) => setAdjustTarget(p);

  const openDetail = async (p: Product) => {
    try {
      const tl = await api.get<{ movements: any[]; price_history: any[]; traceability: any }>(`/api/products/${p.id}/timeline`);
      setDetail({ product: p, timeline: tl.movements || [], price_history: tl.price_history || [] });
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Products</h2>
        <div className="row">
          <button className={tab === 'products' ? 'primary' : ''} onClick={() => setTab('products')}>Products</button>
          <button className={tab === 'catalog' ? 'primary' : ''} onClick={() => setTab('catalog')}>Categories / Units / Brands</button>
          {st.can('product.manage') && tab === 'products' &&
            <button className="primary" onClick={() => setEditing({ unit: 'pcs', track_expiry: false, track_batch: false })}>+ New product</button>}
        </div>
      </div>

      {tab === 'products' && <>
        <input autoFocus placeholder="Search name / SKU / barcode / brand…" value={q} onChange={e => setQ(e.target.value)} style={{ width: '100%', marginBottom: 10 }} />
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table>
            <thead><tr><th>Name</th><th>SKU / Barcode</th><th>Unit</th><th>Stock</th><th>Cost</th><th>Retail</th><th>Margin</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {shown.map(p => (
                <tr key={p.id}>
                  <td><a onClick={() => openDetail(p)} style={{ cursor: 'pointer' }}>{p.name}</a></td>
                  <td className="muted">{p.sku || '—'} / {p.barcode || '—'}</td>
                  <td>{p.unit}</td>
                  <td style={p.stock_qty <= p.min_stock ? { color: 'var(--danger)', fontWeight: 700 } : undefined}>{p.stock_qty}{p.min_stock ? ` (min ${p.min_stock})` : ''}</td>
                  <td>{st.money(p.cost_price)}</td>
                  <td>{st.money(p.retail_price)}</td>
                  <td>{p.margin_percent != null ? p.margin_percent + '%' : '—'}</td>
                  <td>{p.is_active ? <StatusBadge s="active" /> : <StatusBadge s="cancelled" />}</td>
                  <td className="row">
                    <button onClick={() => setEditing(p)}>Edit</button>
                    {p.is_active && st.can('stock.adjust') && <button onClick={() => openAdjust(p)}>Adjust</button>}
                    {p.is_active && <button className="danger" onClick={() => deactivate(p)}>Deactivate</button>}
                  </td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={9} className="muted" style={{ textAlign: 'center', padding: 20 }}>{q ? 'No products match.' : 'No products yet — create your first product.'}</td></tr>}
            </tbody>
          </table>
        </div>
      </>}

      {tab === 'catalog' && meta && <CatalogTab meta={meta} reload={() => api.get<Meta>('/api/catalog/meta').then(setMeta)} />}

      {editing && <ProductForm initial={editing} meta={meta} onCancel={() => setEditing(null)} onSave={save} />}
      {detail && <Modal title={detail.product.name} onClose={() => setDetail(null)} width={640}>
        <div className="grid kpis" style={{ marginBottom: 10 }}>
          <Kv label="Stock" v={String(detail.product.stock_qty)} /><Kv label="Avg cost" v={st.money(detail.product.cost_price)} />
          <Kv label="Retail" v={st.money(detail.product.retail_price)} /><Kv label="Stock value" v={st.money(detail.product.stock_qty * detail.product.cost_price)} />
        </div>
        <h4>Price history (spec #24)</h4>
        <table><thead><tr><th>When</th><th>Field</th><th>Old</th><th>New</th><th>By</th><th>Reason</th></tr></thead>
          <tbody>{detail.price_history.slice(0, 20).map((h: any, i: number) =>
            <tr key={i}><td>{h.at}</td><td>{h.field}</td><td>{h.prev}</td><td>{h.new}</td><td>{h.user}</td><td>{h.reason || '—'}</td></tr>)}
            {detail.price_history.length === 0 && <tr><td colSpan={6} className="muted">No price changes recorded.</td></tr>}</tbody></table>
        <h4>Recent activity</h4>
        <table><thead><tr><th>When</th><th>Type</th><th>Qty change</th><th>Ref</th><th>By</th></tr></thead>
          <tbody>{detail.timeline.slice(0, 25).map((t: any, i: number) =>
            <tr key={i}><td>{t.at}</td><td>{t.type}</td><td>{t.qty_change ?? '—'}</td><td>{t.ref || '—'}</td><td>{t.user || '—'}</td></tr>)}
            {detail.timeline.length === 0 && <tr><td colSpan={5} className="muted">No movements yet.</td></tr>}</tbody></table>
      </Modal>}
      {confirmNode}
      {adjustTarget && <AdjustModal product={adjustTarget} onClose={() => setAdjustTarget(null)} />}
    </div>
  );
}

function Kv({ label, v }: { label: string; v: string }) {
  return <div className="card kpi"><div className="v" style={{ fontSize: 18 }}>{v}</div><div className="l">{label}</div></div>;
}

function AdjustModal({ product: target, onClose }: { product: Product; onClose: () => void }) {
  const st = useStore();
  const [qty, setQty] = useState('');
  const [reason, setReason] = useState('Manual adjustment');
  if (!target) return null;
  const submit = async () => {
    try {
      await api.post(`/api/products/${target.id}/adjust-stock`, { new_qty: Number(qty), reason });
      st.toast('Stock adjusted — movement + audit record created', 'ok'); onClose();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title={`Adjust stock — ${target.name}`} onClose={onClose} width={380}>
    <p className="muted">Current: {target.stock_qty}. Enter the new physical count; the difference is recorded as an audited movement (spec #23).</p>
    <Field label="New quantity"><input type="number" autoFocus value={qty} onChange={e => setQty(e.target.value)} /></Field>
    <Field label="Reason"><input value={reason} onChange={e => setReason(e.target.value)} /></Field>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={!qty} onClick={submit}>Save adjustment</button>
    </div>
  </Modal>;
}

function ProductForm({ initial, meta, onCancel, onSave }: {
  initial: Partial<Product>; meta: Meta | null; onCancel: () => void; onSave: (p: Partial<Product>) => void;
}) {
  const [f, setF] = useState<Partial<Product>>({ unit: 'pcs', track_expiry: false, track_batch: false, ...initial });
  const set = (k: keyof Product) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const v = e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value;
    setF(prev => ({ ...prev, [k]: v as any }));
  };
  const num = (k: keyof Product) => (e: React.ChangeEvent<HTMLInputElement>) => setF(prev => ({ ...prev, [k]: e.target.value === '' ? null as any : Number(e.target.value) }));
  return <Modal title={f.id ? `Edit: ${f.name}` : 'New product'} onClose={onCancel} width={560}>
    <div className="row" style={{ gap: 10 }}>
      <div style={{ flex: 2 }}><Field label="Name *"><input autoFocus value={f.name || ''} onChange={set('name')} /></Field></div>
      <div style={{ flex: 1 }}><Field label="SKU"><input value={f.sku || ''} onChange={set('sku')} /></Field></div>
      <div style={{ flex: 1 }}><Field label="Barcode"><input value={f.barcode || ''} onChange={set('barcode')} /></Field></div>
    </div>
    <div className="row" style={{ gap: 10 }}>
      <Field label="Unit"><select value={f.unit || 'pcs'} onChange={set('unit')}>
        {(meta?.units || ['pcs', 'kg', 'g', 'L', 'ml', 'box', 'carton', 'dozen']).map(u => <option key={u} value={typeof u === 'string' ? u : u.name}>{typeof u === 'string' ? u : u.name}</option>)}
      </select></Field>
      <Field label="Category"><select value={f.category || ''} onChange={set('category')}>
        <option value="">—</option>{(meta?.categories || []).map((c: any) => <option key={c.id ?? c.name} value={c.name}>{c.name}</option>)}
      </select></Field>
      <Field label="Brand"><select value={f.brand || ''} onChange={set('brand')}>
        <option value="">—</option>{(meta?.brands || []).map((b: any) => <option key={b.id ?? b.name} value={b.name}>{b.name}</option>)}
      </select></Field>
    </div>
    <div className="row" style={{ gap: 10 }}>
      <Field label="Purchase cost"><input type="number" step="0.01" value={f.cost_price ?? ''} onChange={num('cost_price')} /></Field>
      <Field label="Retail price *"><input type="number" step="0.01" value={f.retail_price ?? ''} onChange={num('retail_price')} /></Field>
      <Field label="Wholesale"><input type="number" step="0.01" value={f.wholesale_price ?? ''} onChange={num('wholesale_price')} /></Field>
      <Field label="Special"><input type="number" step="0.01" value={f.special_price ?? ''} onChange={num('special_price')} /></Field>
    </div>
    <div className="row" style={{ gap: 10 }}>
      {!f.id && <Field label="Opening stock"><input type="number" value={(f as any).opening_stock ?? ''} onChange={e => setF(p => ({ ...p, opening_stock: Number(e.target.value) || undefined } as any))} /></Field>}
      <Field label="Min stock (low alert)"><input type="number" value={f.min_stock ?? ''} onChange={num('min_stock')} /></Field>
      <Field label="Max stock"><input type="number" value={f.max_stock ?? ''} onChange={num('max_stock')} /></Field>
    </div>
    <div className="row" style={{ gap: 14 }}>
      <label><input type="checkbox" checked={!!f.track_batch} onChange={set('track_batch')} /> Track batch</label>
      <label><input type="checkbox" checked={!!f.track_expiry} onChange={set('track_expiry')} /> Track expiry</label>
      {f.id != null && <label><input type="checkbox" checked={f.is_active !== false} onChange={e => setF(p => ({ ...p, is_active: (e.target as HTMLInputElement).checked }))} /> Active</label>}
    </div>
    <Field label="Notes"><input value={f.notes || ''} onChange={set('notes')} /></Field>
    <p className="muted" style={{ fontSize: 12 }}>Price/cost changes on existing products are recorded with old→new values and reason in the product timeline (spec #24).</p>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onCancel}>Cancel</button>
      <button className="primary" disabled={!f.name || !f.retail_price} onClick={() => onSave(f)}>Save</button>
    </div>
  </Modal>;
}

function CatalogTab({ meta, reload }: { meta: Meta; reload: () => void }) {
  const st = useStore();
  const add = async (kind: 'categories' | 'brands' | 'units') => {
    const name = prompt(`New ${kind.slice(0, -1)} name:`);
    if (!name) return;
    try { await api.post(`/api/catalog/${kind}`, { name }); st.toast('Added', 'ok'); reload(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
    {(['categories', 'brands', 'units'] as const).map(k => (
      <div key={k} className="card" style={{ flex: 1 }}>
        <div className="row spread"><h3 style={{ margin: 0 }}>{k[0].toUpperCase() + k.slice(1)}</h3>
          <button onClick={() => add(k)}>+ Add</button></div>
        <ul>{(meta[k] as any[]).map((x: any) => <li key={x.id ?? x.name}>{typeof x === 'string' ? x : x.name}</li>)}
          {(meta[k] as any[]).length === 0 && <li className="muted">None yet.</li>}</ul>
      </div>
    ))}
  </div>;
}
