import React, { useEffect, useRef, useState } from 'react';

export function Modal({ title, children, onClose, width }: {
  title: string; children: React.ReactNode; onClose: () => void; width?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={e => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); }}>
      <div className="modal" ref={ref} style={width ? { minWidth: width } : undefined}>
        <div className="row spread" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label style={{ display: 'block', marginBottom: 10 }}>
    <span className="muted" style={{ fontSize: 13 }}>{label}</span>
    {children}
  </label>;
}

export function Kpi({ label, value, onClick, tone }: {
  label: string; value: React.ReactNode; onClick?: () => void; tone?: string }) {
  return (
    <div className="card kpi" onClick={onClick} style={{ cursor: onClick ? 'pointer' : undefined }}>
      <div className="v" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

// Generic confirm modal for destructive/sensitive actions (spec #59)
export function useConfirm() {
  const [state, setState] = useState<{ msg: string; resolve: (v: boolean) => void } | null>(null);
  const confirm = (msg: string) => new Promise<boolean>(resolve => setState({ msg, resolve }));
  const node = state ? (
    <Modal title="Please confirm" onClose={() => { state.resolve(false); setState(null); }} width={380}>
      <p>{state.msg}</p>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={() => { state.resolve(false); setState(null); }}>Cancel</button>
        <button className="danger" onClick={() => { state.resolve(true); setState(null); }}>Yes, continue</button>
      </div>
    </Modal>
  ) : null;
  return [confirm, node] as const;
}

export function StatusBadge({ s }: { s: string }) {
  const map: Record<string, string> = {
    completed: 'ok', paid: 'ok', settled: 'ok', received: 'ok', active: 'ok', synced: 'ok', sent: 'ok', approved: 'ok',
    pending: 'warn', partial: 'warn', held: 'warn', ordered: 'warn', draft: 'warn', retry: 'warn', sending: 'warn',
    voided: 'bad', cancelled: 'bad', failed: 'bad', overdue: 'bad', expired: 'bad', conflict: 'bad', rejected: 'bad',
  };
  return <span className={'badge ' + (map[s.toLowerCase()] || 'info')}>{s}</span>;
}

// Live search-as-you-type with keyboard nav (spec #6/#68). Used by POS and pickers.
export function useDebounced<T>(fn: () => Promise<T>, deps: unknown[], ms = 160): { data: T | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    let alive = true;
    const delay = first.current ? 0 : ms;
    first.current = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try { const d = await fn(); if (alive) setData(d); } catch { if (alive) setData(null); }
      if (alive) setLoading(false);
    }, delay);
    return () => { alive = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, loading };
}
