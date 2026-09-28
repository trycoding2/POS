// Inventory dashboard (spec #22): stock health, low/out/expiring/dead lists.
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';
import { Kpi } from '../components/ui';

export default function Inventory() {
  const st = useStore();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState('');
  useEffect(() => { api.get<any>('/api/inventory/dashboard').then(setD).catch(e => setErr(e.message)); }, []);
  if (err) return <div className="card"><b>Could not load inventory</b><p className="muted">{err}</p></div>;
  if (!d) return <p className="muted">Loading inventory…</p>;
  const list = (rows: any[], cols: string[]) => (
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{(rows || []).map((r: any, i: number) => (
          <tr key={i}>{cols.map(c => <td key={c}>{typeof r[c] === 'number' ? c.replace(/price|value|cost|total/i, '') && st.money(r[c]) : String(r[c] ?? '—')}</td>)}</tr>))}
          {(rows || []).length === 0 && <tr><td colSpan={cols.length} className="muted" style={{ textAlign: 'center', padding: 12 }}>None 🎉</td></tr>}
        </tbody></table>
    </div>
  );
  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Inventory</h2>
      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Total products" value={d.total_products ?? 0} />
        <Kpi label="Stock value (cost)" value={st.money(d.stock_value_cost)} />
        <Kpi label="Low stock" value={d.low_stock_count ?? (d.low_stock || []).length} tone={ '#d32f2f'} onClick={() => document.getElementById('low')?.scrollIntoView()} />
        <Kpi label="Out of stock" value={d.out_of_stock_count ?? (d.out_of_stock || []).length} tone="#d32f2f" />
        <Kpi label="Expiring soon" value={d.expiring_count ?? (d.expiring_soon || []).length} tone="#ef6c00" />
        <Kpi label="Expired" value={d.expired_count ?? (d.expired || []).length} tone="#d32f2f" />
      </div>
      <h3 id="low">Low stock ({(d.low_stock || []).length})</h3>{list(d.low_stock, ['name', 'stock_qty', 'min_stock'])}
      <h3>Out of stock ({(d.out_of_stock || []).length})</h3>{list(d.out_of_stock, ['name', 'stock_qty'])}
      <h3>Expiring soon ({(d.expiring_soon || []).length})</h3>{list(d.expiring_soon, ['name', 'batch', 'expiry_date', 'qty'])}
      <h3>Expired ({(d.expired || []).length})</h3>{list(d.expired, ['name', 'batch', 'expiry_date', 'qty'])}
      <h3>Fast moving (30 days)</h3>{list(d.fast_moving, ['name', 'qty_sold', 'revenue'])}
      <h3>Slow / dead stock</h3>{list(d.dead_stock ?? d.slow_moving, ['name', 'stock_qty', 'days_since_sale'])}
    </div>
  );
}
