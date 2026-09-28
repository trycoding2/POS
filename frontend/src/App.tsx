// App shell: auth gate, permission-aware sidebar navigation (spec #4/#35), topbar with
// offline indicator (spec #43) and route table. Every nav item maps to a real page.
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, HashRouter, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import { useStore } from './store';
import { api } from './api/client';
import Login from './pages/Login';

const isTauri = !!(window as any).__TAURI_INTERNALS__;
const Router: typeof BrowserRouter = isTauri ? HashRouter : BrowserRouter;

const Dashboard = lazy(() => import('./pages/Dashboard'));
const POS = lazy(() => import('./pages/POS'));
const Products = lazy(() => import('./pages/Products'));
const Inventory = lazy(() => import('./pages/Inventory'));
const Purchases = lazy(() => import('./pages/Purchases'));
const Orders = lazy(() => import('./pages/Orders'));
const Customers = lazy(() => import('./pages/Customers'));
const Khata = lazy(() => import('./pages/Khata'));
const Dasti = lazy(() => import('./pages/Dasti'));
const Suppliers = lazy(() => import('./pages/Suppliers'));
const Cash = lazy(() => import('./pages/Cash'));
const Expenses = lazy(() => import('./pages/Expenses'));
const Returns = lazy(() => import('./pages/Returns'));
const Reports = lazy(() => import('./pages/Reports'));
const Notifications = lazy(() => import('./pages/Notifications'));
const Users = lazy(() => import('./pages/Users'));
const Activity = lazy(() => import('./pages/Activity'));
const Backup = lazy(() => import('./pages/Backup'));
const Settings = lazy(() => import('./pages/Settings'));
const Help = lazy(() => import('./pages/Help'));

interface NavItem { to: string; label: string; icon: string; perms?: string[]; settingOff?: string }

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/pos', label: 'POS / Sales', icon: '🛒', perms: ['sale.create'] },
  { to: '/products', label: 'Products', icon: '📦', perms: ['product.manage'] },
  { to: '/inventory', label: 'Inventory', icon: '🏷️' },
  { to: '/purchases', label: 'Purchases', icon: '🚚', perms: ['purchase.create'] },
  { to: '/orders', label: 'Orders', icon: '📋', perms: ['order.manage'] },
  { to: '/customers', label: 'Customers', icon: '👥', perms: ['customer.create'] },
  { to: '/khata', label: 'Khata', icon: '📒', perms: ['customer.balance.view'] },
  { to: '/dasti', label: 'Dasti', icon: '🤝', perms: ['dasti.create'], settingOff: 'payments.dasti' },
  { to: '/suppliers', label: 'Suppliers', icon: '🏭', perms: ['supplier.create'] },
  { to: '/cash', label: 'Cash & Accounts', icon: '💵', perms: ['cash.manage'] },
  { to: '/expenses', label: 'Expenses', icon: '🧾', perms: ['expense.create'] },
  { to: '/returns', label: 'Returns', icon: '↩️' },
  { to: '/reports', label: 'Reports', icon: '📈' },
  { to: '/notifications', label: 'WhatsApp / Alerts', icon: '💬', perms: ['notification.send'] },
  { to: '/users', label: 'Users & Roles', icon: '🔐', perms: ['users.manage'] },
  { to: '/activity', label: 'Audit Log', icon: '🕵️', perms: ['audit.view'] },
  { to: '/backup', label: 'Backup & Sync', icon: '☁️', perms: ['backup.manage'] },
  { to: '/settings', label: 'Settings', icon: '⚙️', perms: ['settings.edit'] },
  { to: '/help', label: 'Help', icon: '❓' },
];

export default function App() {
  const st = useStore();
  if (!st.ready) return <div className="login-wrap"><p className="muted">Loading…</p></div>;
  if (!st.user) return <Login />;

  const allowed = (n: NavItem) =>
    (!n.perms || n.perms.some(p => st.can(p))) &&
    !(n.settingOff && st.settings[n.settingOff] === 'false');
  const items = NAV.filter(allowed);

  return (
    <Router>
      <Shell items={items} />
    </Router>
  );
}

function Shell({ items }: { items: NavItem[] }) {
  const st = useStore();
  const navigate = useNavigate();
  const user = st.user;   // non-null here (App gates on auth), local copy for TS narrowing
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">🏪 {st.settings['store.name'] || 'Karyana Manager'}</div>
        <nav style={{ flex: 1 }}>
          {items.map(n => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'}>{n.icon} {n.label}</NavLink>
          ))}
        </nav>
        <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
          <div className="muted" style={{ fontSize: 13 }}>{user?.full_name || user?.username}
            <br /><span className="badge">{user?.role}</span></div>
          <button style={{ width: '100%', marginTop: 8 }} onClick={async () => { await st.logout(); }}>Sign out</button>
        </div>
      </aside>
      <div className="main">
        <div className="topbar">
          <span className="muted" style={{ fontSize: 13 }}>Device: {(localStorage.getItem('km_device') || 'POS-01')}</span>
          <span style={{ flex: 1 }} />
          {!st.online && <span className="badge bad">OFFLINE — transactions still save locally</span>}
          <SyncChip />
          <ApprovalsBell />
        </div>
        <div className="content">
          <Suspense fallback={<p className="muted">Loading…</p>}>
            <Routes>
              <Route path="/" element={<Go perm="" page={<Dashboard />} />} />
              <Route path="/pos" element={<Go perm="sale.create" page={<POS />} />} />
              <Route path="/products" element={<Go perm="product.manage" page={<Products />} />} />
              <Route path="/inventory" element={<Go perm="" page={<Inventory />} />} />
              <Route path="/purchases" element={<Go perm="purchase.create" page={<Purchases />} />} />
              <Route path="/orders" element={<Go perm="order.manage" page={<Orders />} />} />
              <Route path="/customers" element={<Go perm="customer.create" page={<Customers />} />} />
              <Route path="/khata" element={<Go perm="customer.balance.view" page={<Khata />} />} />
              <Route path="/dasti" element={<Go perm="dasti.create" page={<Dasti />} />} />
              <Route path="/suppliers" element={<Go perm="supplier.create" page={<Suppliers />} />} />
              <Route path="/cash" element={<Go perm="cash.manage" page={<Cash />} />} />
              <Route path="/expenses" element={<Go perm="expense.create" page={<Expenses />} />} />
              <Route path="/returns" element={<Go perm="" page={<Returns />} />} />
              <Route path="/reports" element={<Go perm="" page={<Reports />} />} />
              <Route path="/notifications" element={<Go perm="notification.send" page={<Notifications />} />} />
              <Route path="/users" element={<Go perm="users.manage" page={<Users />} />} />
              <Route path="/activity" element={<Go perm="audit.view" page={<Activity />} />} />
              <Route path="/backup" element={<Go perm="backup.manage" page={<Backup />} />} />
              <Route path="/settings" element={<Go perm="settings.edit" page={<Settings />} />} />
              <Route path="/help" element={<Go perm="" page={<Help />} />} />
              <Route path="*" element={<NoMatch navigate={navigate} />} />
            </Routes>
          </Suspense>
        </div>
      </div>
    </div>
  );
}

function NoMatch({ navigate }: { navigate: (p: string, o?: { replace?: boolean }) => void }) {
  React.useEffect(() => { navigate('/', { replace: true }); }, [navigate]);
  return null;
}

// Permission guard: server also enforces every permission — this is UX only (spec #65).
function Go({ perm, page }: { perm: string; page: React.ReactNode }) {
  const st = useStore();
  if (perm && !st.can(perm)) {
    return <div className="card"><b>Not allowed</b><p className="muted">
      Your role does not have the “{perm}” permission. Ask the owner to enable it under Users &amp; Roles.</p></div>;
  }
  return <>{page}</>;
}

function SyncChip() {
  const st = useStore();
  const [s, setS] = React.useState<{ pending: number; cloud_configured: boolean } | null>(null);
  React.useEffect(() => {
    if (!st.online) return;
    let alive = true;
    const load = () => api.get<any>('/api/sync/status').then(r => alive && setS(r)).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => { alive = false; clearInterval(t); };
  }, [st.online]);
  if (!s) return null;
  if (!s.cloud_configured) return <span className="badge info" title="Cloud sync not configured — data stays local + backups">Local only</span>;
  return s.pending > 0
    ? <span className="badge warn">{s.pending} unsynced</span>
    : <span className="badge ok">Synced</span>;
}

function ApprovalsBell() {
  const st = useStore();
  const [n, setN] = React.useState(0);
  React.useEffect(() => {
    if (!st.can('approval.grant')) return;
    let alive = true;
    const load = () => api.get<any[]>('/api/approvals?status=pending').then(r => alive && setN(r.length)).catch(() => {});
    load();
    const t = setInterval(load, 45000);
    return () => { alive = false; clearInterval(t); };
  }, [st.user]);
  if (!st.can('approval.grant') || n === 0) return null;
  return <span className="badge bad" title="Pending approvals">⏳ {n} approval{n > 1 ? 's' : ''}</span>;
}
