import React, { useEffect, useState } from 'react';
import { api, setToken, type UserInfo, type Settings } from '../api/client';
import { useStore } from '../store';
import { deviceId } from '../api/client';
import { Field, Modal } from '../components/ui';

export default function Login() {
  const st = useStore();
  const [initialized, setInit] = useState<boolean | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  // setup wizard state
  const [wizard, setWizard] = useState(false);
  const [w, setW] = useState({ store_name: '', owner_username: 'owner', owner_password: '', owner_full_name: '', currency_symbol: 'Rs.', address: '', phone: '', opening_cash: '0' });
  const W = (k: string, v: string) => setW(x => ({ ...x, [k]: v }));

  useEffect(() => { api.get<{ initialized: boolean }>('/api/auth/initialized').then(r => setInit(r.initialized)).catch(() => setErr('Backend not reachable. Start it with: uvicorn app.main:app --port 8000')); }, []);

  const finishLogin = (token: string, user: UserInfo, settings?: Settings) => {
    setToken(token); st.setUser(user, settings);
  };

  const doLogin = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const r = await api.post<{ token: string; user: UserInfo; settings: Settings }>('/api/auth/login', { username, password, device_id: deviceId });
      finishLogin(r.token, r.user, r.settings);
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  };

  const doSetup = async () => {
    if (!w.store_name.trim()) { setErr('Store name is required.'); return; }
    if (w.owner_password.length < 6) { setErr('Owner password must be at least 6 characters.'); return; }
    setBusy(true); setErr('');
    try {
      const r = await api.post<{ ok: boolean; token: string }>('/api/auth/setup', {
        ...w, opening_cash: parseFloat(w.opening_cash) || 0,
      });
      const login = await api.post<{ token: string; user: UserInfo; settings: Settings }>('/api/auth/login', { username: w.owner_username, password: w.owner_password, device_id: deviceId });
      finishLogin(login.token, login.user, login.settings);
    } catch (ex: any) { setErr(ex.message); setBusy(false); }
  };

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <h2 style={{ marginTop: 0 }}>🏪 Karyana Manager</h2>
        {initialized === false ? (
          <>
            <p className="muted">Welcome! First-time setup — create your store and owner account.</p>
            <button className="primary big" style={{ width: '100%' }} onClick={() => setWizard(true)}>Start Setup Wizard</button>
          </>
        ) : (
          <form onSubmit={doLogin}>
            <Field label="Username"><input autoFocus value={username} onChange={e => setUsername(e.target.value)} /></Field>
            <Field label="Password"><input type="password" value={password} onChange={e => setPassword(e.target.value)} /></Field>
            {err && <p style={{ color: 'var(--danger)' }}>{err}</p>}
            <button className="primary big" style={{ width: '100%' }} disabled={busy}>{busy ? 'Signing in…' : 'Sign In'}</button>
            <p className="muted" style={{ fontSize: 13 }}>Device: {deviceId}</p>
          </form>
        )}
      </div>
      {wizard && (
        <Modal title="Initial Setup Wizard" onClose={() => setWizard(false)} width={460}>
          <Field label="Store name *"><input autoFocus value={w.store_name} onChange={e => W('store_name', e.target.value)} placeholder="Al-Madina Karyana Store" /></Field>
          <div className="row"><div style={{ flex: 1 }}><Field label="Owner username *"><input value={w.owner_username} onChange={e => W('owner_username', e.target.value)} /></Field></div>
            <div style={{ flex: 1 }}><Field label="Owner full name"><input value={w.owner_full_name} onChange={e => W('owner_full_name', e.target.value)} /></Field></div></div>
          <Field label="Owner password * (min 6 chars)"><input type="password" value={w.owner_password} onChange={e => W('owner_password', e.target.value)} /></Field>
          <div className="row"><div style={{ flex: 1 }}><Field label="Currency symbol"><input value={w.currency_symbol} onChange={e => W('currency_symbol', e.target.value)} /></Field></div>
            <div style={{ flex: 1 }}><Field label="Opening cash (Main Cash)"><input value={w.opening_cash} onChange={e => W('opening_cash', e.target.value)} /></Field></div></div>
          <Field label="Phone"><input value={w.phone} onChange={e => W('phone', e.target.value)} /></Field>
          <Field label="Address"><input value={w.address} onChange={e => W('address', e.target.value)} /></Field>
          <p className="muted" style={{ fontSize: 13 }}>Units, roles, payment accounts and expense categories are created automatically. You can complete receipt, WhatsApp, cloud-backup and tax settings later from Settings.</p>
          {err && <p style={{ color: 'var(--danger)' }}>{err}</p>}
          <div className="row spread">
            <button onClick={() => setWizard(false)}>Cancel</button>
            <button className="primary" disabled={busy} onClick={doSetup}>{busy ? 'Setting up…' : 'Finish Setup'}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
