import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type AuditRow } from '../api/client';
import { useStore } from '../store';
import { Kpi } from '../components/ui';

interface Dash {
  today_sales: number; today_gross_profit?: number; today_expenses?: number;
  today_net_profit_estimate?: number; today_discounts: number; today_returns: number;
  today_purchases: number; cash_accounts: { account_id: number; name: string; balance: number }[];
  receivables: number; dasti_outstanding: number; payables: number;
  inventory: { stock_value_cost: number; low_stock_count?: number };
  top_products?: { name: string; qty: number; revenue: number }[];
}

export default function Dashboard() {
  const st = useStore();
  const [d, setD] = useState<Dash | null>(null);
  const [act, setAct] = useState<AuditRow[]>([]);
  const load = () => {
    api.get<Dash>('/api/reports/dashboard').then(setD).catch(e => st.toast(e.message, 'bad'));
    if (st.can('audit.view')) api.get<AuditRow[]>('/api/activity?limit=12').then(setAct).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []); // eslint-disable-line
  if (!d) return <p className="muted">Loading dashboard…</p>;
  const storeName = st.settings['store.name'] || 'Dashboard';
  return (
    <div>
      <h2 style={{ marginTop: 0 }}>{storeName} — Today</h2>
      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Sales" value={st.money(d.today_sales)} tone="var(--brand)" />
        {d.today_gross_profit !== undefined && <Kpi label="Gross profit" value={st.money(d.today_gross_profit)} />}
        {d.today_net_profit_estimate !== undefined && <Kpi label="Net profit (est.)" value={st.money(d.today_net_profit_estimate)} />}
        <Kpi label="Expenses" value={st.money(d.today_expenses ?? 0)} />
        <Kpi label="Discounts" value={st.money(d.today_discounts)} />
        <Kpi label="Returns" value={st.money(d.today_returns)} />
        <Kpi label="Purchases" value={st.money(d.today_purchases)} />
        <Kpi label="Receivables (Khata)" value={st.money(d.receivables)} onClick={() => {}} />
        <Kpi label="Dasti outstanding" value={st.money(d.dasti_outstanding)} />
        <Kpi label="Payables (Suppliers)" value={st.money(d.payables)} />
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))' }}>
        <div className="card">
          <b>Cash & accounts</b>
          <table><tbody>{d.cash_accounts.map(a => (
            <tr key={a.account_id}><td>{a.name}</td><td className="right">{st.money(a.balance)}</td></tr>
          ))}</tbody></table>
          <Link to="/cash">Manage cash →</Link>
        </div>
        <div className="card">
          <b>Inventory</b>
          <p>Stock value (cost): <b>{st.money(d.inventory.stock_value_cost)}</b></p>
          <p>Low-stock items: <span className="badge warn">{d.inventory.low_stock_count ?? 0}</span></p>
          <Link to="/inventory">Open inventory →</Link>
        </div>
        <div className="card">
          <b>Top products today</b>
          <table><tbody>
            {(d.top_products || []).slice(0, 6).map((p, i) => (
              <tr key={i}><td>{p.name}</td><td className="muted">×{p.qty}</td><td className="right">{st.money(p.revenue)}</td></tr>
            ))}
            {!(d.top_products || []).length && <tr><td className="muted">No sales yet today.</td></tr>}
          </tbody></table>
          <Link to="/reports">More reports →</Link>
        </div>
        {st.can('audit.view') && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="row spread"><b>Activity log</b><Link to="/activity">Full log →</Link></div>
            <table><tbody>{act.map(a => (
              <tr key={a.id}>
                <td className="muted mono" style={{ fontSize: 12 }}>{new Date(a.at).toLocaleTimeString()}</td>
                <td>{a.user}</td><td><span className="badge">{a.module}</span></td>
                <td>{a.action} {a.entity}{a.entity_ref ? ` · ${a.entity_ref}` : ''}</td>
                <td className="muted" style={{ fontSize: 12 }}>{a.reason || ''}</td>
              </tr>
            ))}</tbody></table>
          </div>
        )}
      </div>
    </div>
  );
}
