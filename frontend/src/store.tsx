import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, setToken, deviceId, Settings, UserInfo } from './api/client';

interface Toast { id: number; msg: string; kind: 'ok' | 'bad' | 'info' }
interface Store {
  user: UserInfo | null; settings: Settings; ready: boolean; online: boolean;
  can: (perm: string) => boolean;
  money: (v: number | null | undefined) => string;
  toast: (msg: string, kind?: Toast['kind']) => void;
  refreshSettings: () => Promise<void>;
  logout: () => Promise<void>;
  setUser: (u: UserInfo | null, s?: Settings) => void;
}
const Ctx = createContext<Store>(null as unknown as Store);
export const useStore = () => useContext(Ctx);

let tid = 1;
export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [settings, setSettings] = useState<Settings>({});
  const [ready, setReady] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = (msg: string, kind: Toast['kind'] = 'info') => {
    const id = tid++;
    setToasts(t => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4200);
  };

  const refreshSettings = async () => {
    try { setSettings(await api.get<Settings>('/api/settings')); } catch { /* offline-tolerant */ }
  };

  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false);
    window.addEventListener('online', on); window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  useEffect(() => {
    (async () => {
      if (localStorage.getItem('km_token')) {
        try {
          const me = await api.get<{ user: UserInfo }>('/api/auth/me');
          setUser(me.user);
          setSettings(await api.get<Settings>('/api/settings'));
        } catch { setToken(null); }
      }
      setReady(true);
    })();
  }, []);

  // theme + font size actually applied (spec #71)
  useEffect(() => {
    document.documentElement.dataset.theme = settings['ui.theme'] || 'light';
    const fs = settings['ui.font_size'];
    if (fs) document.body.style.fontSize = fs.endsWith('px') ? fs : fs + 'px';
  }, [settings]);

  const value: Store = {
    user, settings, ready, online,
    can: (p: string) => !!user?.permissions?.includes(p) || user?.role === 'Owner',
    money: v => {
      const dec = parseInt(settings['currency.decimals'] ?? '0');
      const tsep = settings['currency.thousand_sep'] ?? ',';
      const dsep = settings['currency.decimal_sep'] ?? '.';
      const sym = settings['currency.symbol'] ?? 'Rs.';
      const pos = settings['currency.position'] ?? 'prefix';
      if (v === null || v === undefined || isNaN(Number(v))) return '—';
      const s = Math.abs(Number(v)).toFixed(dec);
      const [ip, fp] = s.split('.');
      const grouped = ip.replace(/\B(?=(\d{3})+(?!\d))/g, tsep) + (fp ? dsep + fp : '');
      const body = (Number(v) < 0 ? '-' : '') + grouped;
      return pos === 'suffix' ? body + ' ' + sym : sym + ' ' + body;
    },
    toast, refreshSettings,
    setUser: (u, s) => { setUser(u); if (s) setSettings(s); },
    logout: async () => {
      try { await api.post('/api/auth/logout'); } catch { /* ignore */ }
      setToken(null); setUser(null);
    },
  };
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toast">{toasts.map(t => (
        <div key={t.id} className="t" style={{ background: t.kind === 'ok' ? 'var(--ok)' : t.kind === 'bad' ? 'var(--danger)' : '#1565c0' }}>{t.msg}</div>
      ))}</div>
    </Ctx.Provider>
  );
}
export { deviceId };
