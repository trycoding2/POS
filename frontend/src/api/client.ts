// Central API client. All pages use this — no page talks to the backend directly.
const BASE = (import.meta.env.VITE_API_URL as string) || '';

export class ApiError extends Error {
  status: number; committed: boolean;
  constructor(status: number, message: string, committed: boolean) {
    super(message); this.status = status; this.committed = committed;
  }
}

let token: string | null = localStorage.getItem('km_token');
export function setToken(t: string | null) {
  token = t;
  if (t) localStorage.setItem('km_token', t); else localStorage.removeItem('km_token');
}

export const deviceId = localStorage.getItem('km_device') || (() => {
  const d = 'POS-01'; localStorage.setItem('km_device', d); return d;
})();

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = 'Bearer ' + token;
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method, headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Cannot reach the local server. The application works offline once loaded, but the desktop service must be running.', false);
  }
  let data: any = null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('json')) data = await res.json();
  else if (ct.includes('text')) data = { text: await res.text() };
  else data = await res.blob().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, (data && data.detail) || `Request failed (${res.status}).`,
      !!(data && data.committed));
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => req<T>('GET', p),
  post: <T>(p: string, b?: unknown) => req<T>('POST', p, b ?? {}),
  put: <T>(p: string, b?: unknown) => req<T>('PUT', p, b ?? {}),
};

// ---------- typed helpers ----------
export type Money = number;
export interface Settings { [k: string]: string }
export interface UserInfo {
  id: number; username: string; full_name: string; role: string; role_id: number;
  is_active: boolean; permissions?: string[]; max_discount_percent?: number;
}
export interface Product {
  id: number; name: string; sku?: string; barcode?: string; unit: string;
  category?: string; brand?: string; cost_price: Money; retail_price: Money;
  wholesale_price?: Money | null; special_price?: Money | null;
  stock_qty: number; min_stock: number; margin_percent?: number | null;
  is_active: boolean; track_expiry: boolean; track_batch: boolean;
  category_id?: number | null; brand_id?: number | null; unit_id?: number | null;
  default_supplier_id?: number | null; notes?: string; max_stock?: number | null;
}
export interface CartLine { product: Product; qty: number; price: Money; discount: Money }
export interface SaleOut {
  id: number; ref: string; status: string; subtotal: Money; discount_total: Money;
  tax_total: Money; grand_total: Money; paid_total: Money; credit_amount: Money;
  customer: string; customer_id?: number | null; cashier?: string; device?: string;
  created_at: string; void_reason?: string | null; notes?: string;
  items: { id: number; product_id: number; qty: number; unit_price: Money; discount: Money; line_total: Money }[];
  payments: { account_id: number; amount: Money; method: string }[];
  receipt?: string; change_given?: Money;
}
export interface Account { id: number; name: string; type: string; is_active: boolean; balance: Money; is_default_sale?: boolean }
export interface Customer {
  id: number; name: string; phone?: string; alt_phone?: string; address?: string;
  notes?: string; credit_limit?: Money; is_khata: boolean; whatsapp_enabled?: boolean;
  is_active: boolean; balance?: Money | null; outstanding?: Money;
}
export interface Supplier {
  id: number; name: string; company?: string; phone?: string; address?: string;
  contact_person?: string; payment_terms?: string; notes?: string; is_active: boolean;
  balance?: Money | null;
}
export interface Dasti {
  id: number; ref: string; customer_name?: string; phone?: string; amount: Money;
  paid_amount: Money; outstanding: Money; overdue: boolean; status: string;
  created_at?: string; due_date?: string | null; items: any[]; notes?: string; created_by?: number;
}
export interface AuditRow {
  id: number; at: string; user?: string; role?: string; device?: string; module: string;
  action: string; entity?: string; entity_ref?: string | null; prev?: string | null;
  new?: string | null; reason?: string | null; related?: string | null; amount?: Money | null;
}
export interface Purchase {
  id: number; ref: string; supplier_id?: number | null; invoice_no?: string;
  subtotal: Money; discount_total: Money; grand_total: Money; paid_amount: Money;
  due_amount: Money; status: string; created_at?: string; notes?: string;
  items: { id: number; product_id: number; qty_received: number; qty_ordered: number; qty_free: number; unit_cost: Money; line_total: Money }[];
}

// Currency formatting driven by live settings (spec #39/#71 — never hardcoded).
export function fmtMoney(v: Money | null | undefined, st: Settings): string {
  if (v === null || v === undefined || isNaN(Number(v))) return '—';
  const dec = parseInt(st['currency.decimals'] ?? '0');
  const tsep = st['currency.thousand_sep'] ?? ',';
  const dsep = st['currency.decimal_sep'] ?? '.';
  const sym = st['currency.symbol'] ?? 'Rs.';
  const pos = st['currency.position'] ?? 'prefix';
  let s = Math.abs(Number(v)).toFixed(dec);
  const [ip, fp] = s.split('.');
  const grouped = ip.replace(/\B(?=(\d{3})+(?!\d))/g, tsep) + (fp ? dsep + fp : '');
  const body = (Number(v) < 0 ? '-' : '') + grouped;
  return pos === 'suffix' ? body + ' ' + sym : sym + ' ' + body;
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}