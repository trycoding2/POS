// Reports (spec #29): sales, profit, inventory, receivables/payables, cash, payments, products + CSV export.
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';

const TABS = ['sales', 'profit', 'inventory', 'receivables', 'payables', 'cash', 'payments', 'sales-by-product'] as const;
type Tab = typeof TABS[number];

function csvKind(tab: Tab): string {
  if (tab === 'sales') return 'sales';
  if (tab === 'profit') return 'profit';
  if (tab === 'sales-by-product') return 'products';
  if (tab === 'receivables') return 'receivables';
  if (tab === 'payables') return 'payables';
  return 'sales';
}

export default function Reports() {
  const st = useStore();
  const [tab, setTab] = useState<Tab>('sales');
  const [from, setFrom] = useState(new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10));
  const [to, setTo] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const load = () => {
    setLoading(true);
    api.get<any>(`/api/reports/${tab}?start=${from}&end=${to}`)
      .then(setData).catch(e => st.toast(e.message, 'bad')).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [tab]); // eslint-disable-line
    const rows: any[] = Array.isArray(data) ? data
    : tab === 'receivables' ? [...(data?.customers ?? []), ...(data?.overdue_dastis ?? [])]
    : tab === 'payables' ? (data?.suppliers ?? [])
    : tab === 'inventory' ? (data?.products ?? [])
    : (data?.rows ?? data?.items ?? data?.days ?? data?.products ?? []);
  const cols = rows.length ? Object.keys(rows[0]) : [];
    const moneyCols = cols.filter(c => /amount|total|revenue|profit|cost|discount|balance|paid|due|value|margin|payable|outstanding/i.test(c) && c !== 'id');
  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Reports</h2>
      <a className="primary" style={{ textDecoration: 'none' }} href={`${(import.meta.env.VITE_API_URL as string) || ''}/api/reports/export.csv?kind=${csvKind(tab)}&start=${from}&end=${to}`} onClick={async e => {
        e.preventDefault();
        try {
          const blob = await api.get<Blob>(`/api/reports/export.csv?kind=${csvKind(tab)}&start=${from}&end=${to}`);
          const url = URL.createObjectURL(blob as any); const a = document.createElement('a');
          a.href = url; a.download = `${tab}-report.csv`; a.click(); URL.revokeObjectURL(url);
        } catch (err: any) { st.toast(err.message, 'bad'); }
      }}>⬇ Export CSV</a>
    </div>
    <div className="row" style={{ marginBottom: 10, flexWrap: 'wrap' }}>
      {TABS.map(t => <button key={t} className={tab === t ? 'primary' : ''} onClick={() => setTab(t)}>{t.replace(/-/g, ' ')}</button>)}
      <span style={{ flex: 1 }} />
      <input type="date" value={from} onChange={e => setFrom(e.target.value)} />
      <input type="date" value={to} onChange={e => setTo(e.target.value)} />
      <button className="primary" onClick={load}>Apply</button>
    </div>
    {loading && <p className="muted">Loading…</p>}
    {!loading && data && !Array.isArray(data) && cols.length === 0 && (() => {
      const nums = Object.entries(data).filter(([, v]) => typeof v === 'number');
      return <div className="grid kpis" style={{ marginBottom: 12 }}>{nums.map(([k, v]) => (
        <div key={k} className="card kpi"><div className="v">{moneyCols.concat(cols).includes(k) || /total|amount|profit|revenue|value|balance|paid|due/i.test(k) ? st.money(v as number) : String(v)}</div><div className="l">{k.replace(/_/g, ' ')}</div></div>))}</div>;
    })()}
    {rows.length > 0 && <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr>{cols.map(c => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
        <tbody>{rows.slice(0, 400).map((r, i) => (
          <tr key={i}>{cols.map(c => <td key={c}>{typeof r[c] === 'number' && moneyCols.includes(c) ? st.money(r[c]) : String(r[c] ?? '—')}</td>)}</tr>))}</tbody></table>
    </div>}
    {!loading && rows.length === 0 && <p className="muted">No data for the selected period.</p>}
  </div>;
}
