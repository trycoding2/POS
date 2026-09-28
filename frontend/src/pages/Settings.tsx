// Owner Control Center (spec #38/#56): every setting is backed by PUT /api/settings and
// actually drives behavior server-side (spec #71). No cosmetic settings here.
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';
import { Field } from '../components/ui';

const GROUPS: { name: string; icon: string; keys: [string, string, string?][] }[] = [
  { name: 'Store', icon: '🏪', keys: [
    ['store.name', 'Store name'], ['store.address', 'Address'], ['store.phone', 'Phone'],
    ['store.whatsapp', 'WhatsApp number'], ['store.email', 'Email']] },
  { name: 'Currency', icon: '💰', keys: [
    ['currency.symbol', 'Symbol (e.g. Rs.)'], ['currency.code', 'Code (e.g. PKR)'],
    ['currency.decimals', 'Decimal places (0-2)'], ['currency.thousand_sep', 'Thousand separator'],
    ['currency.decimal_sep', 'Decimal separator'], ['currency.position', 'Position (prefix/suffix)']] },
  { name: 'Appearance & Language', icon: '🎨', keys: [
    ['ui.theme', 'Theme (light/dark)'], ['ui.font_size', 'Font size'], ['ui.language', 'Language (en/ur)'],
    ['timezone', 'Time zone'], ['date_format', 'Date format']] },
  { name: 'POS', icon: '🛒', keys: [
    ['pos.barcode_auto_add', 'Barcode auto-add to cart (true/false)'],
    ['pos.manual_add_ask_qty', 'Ask quantity on manual add'],
    ['pos.show_category_buttons', 'Show category buttons'],
    ['pos.default_customer_walkin', 'Default customer = Walk-in'],
    ['pos.allow_negative_stock', 'Allow negative stock (NOT recommended)']] },
  { name: 'Payments', icon: '💵', keys: [
    ['payments.cash', 'Cash enabled'], ['payments.bank', 'Bank enabled'],
    ['payments.wallet_easypaisa', 'Easypaisa enabled'], ['payments.wallet_jazzcash', 'JazzCash enabled'],
    ['payments.credit_khata', 'Khata credit enabled'], ['payments.dasti', 'Dasti enabled'],
    ['payments.split', 'Split payments enabled']] },
  { name: 'Khata & Dasti', icon: '📒', keys: [
    ['khata.default_credit_limit', 'Default credit limit (0 = no limit)'],
    ['khata.reminder_days', 'Reminder after N days'],
    ['dasti.default_due_days', 'Dasti default due days'],
    ['dasti.require_phone', 'Dasti requires phone (true/false)']] },
  { name: 'Stock', icon: '📦', keys: [
    ['stock.low_stock_default', 'Default low-stock threshold'],
    ['stock.expiring_soon_days', 'Expiring-soon window (days)']] },
  { name: 'Tax', icon: '🧾', keys: [['tax.enabled', 'Tax enabled (true/false)'], ['tax.percent', 'Tax %']] },
  { name: 'Receipts', icon: '🖨️', keys: [
    ['receipt.header', 'Receipt header message'], ['receipt.footer', 'Receipt footer message'],
    ['receipt.paper_size', 'Paper size (80mm/58mm/A4)'], ['receipt.printer', 'Printer name'],
    ['receipt.show_customer', 'Show customer'], ['receipt.show_cashier', 'Show cashier'],
    ['receipt.show_discount', 'Show discount'], ['receipt.show_payment_method', 'Show payment method'],
    ['receipt.show_balance', 'Show balance']] },
  { name: 'Notifications / WhatsApp', icon: '💬', keys: [
    ['whatsapp.enabled', 'WhatsApp engine enabled (needs API token below)'],
    ['whatsapp.auto_sale_receipt', 'Auto-send sale receipts'],
    ['whatsapp.auto_khata_reminder', 'Auto khata reminders'],
    ['whatsapp.auto_dasti_reminder', 'Auto dasti reminders'],
    ['notify.daily_owner_report', 'Daily owner summary'],
    ['whatsapp.api_url', 'WhatsApp Cloud API URL (integration boundary)'],
    ['whatsapp.api_token', 'WhatsApp API token (stored locally, never sent to third parties)'],
    ['whatsapp.phone_number_id', 'WhatsApp phone number id']] },
  { name: 'Backup & Sync', icon: '☁️', keys: [
    ['backup.auto_local', 'Automatic local backup hourly'],
    ['backup.keep_count', 'Backups to keep'],
    ['sync.enabled', 'Cloud sync enabled'], ['sync.server_url', 'Sync server URL'],
    ['sync.api_key', 'Sync API key']] },
  { name: 'Approvals (0 = off)', icon: '✅', keys: [
    ['approval.discount_percent', 'Discount % needing approval'],
    ['approval.void_sale', 'Sale void needs approval (true/false)'],
    ['approval.stock_adjust_qty', 'Stock adjustment qty needing approval'],
    ['approval.expense_amount', 'Expense amount needing approval'],
    ['approval.supplier_payment_amount', 'Supplier payment amount needing approval'],
    ['approval.price_change', 'Price change needs approval (true/false)']] },
  { name: 'Invoice numbering', icon: '🔢', keys: [
    ['ref.format', 'Ref format ({prefix}-{yyyymmdd}-{seq:06d})'],
    ['ref.SALE.prefix', 'Sale prefix'], ['ref.PUR.prefix', 'Purchase prefix'],
    ['ref.PAY.prefix', 'Payment prefix'], ['ref.RET.prefix', 'Return prefix'],
    ['ref.EXP.prefix', 'Expense prefix'], ['ref.DST.prefix', 'Dasti prefix'],
    ['ref.ADJ.prefix', 'Adjustment prefix'], ['ref.ORD.prefix', 'Order prefix'],
    ['ref.WDR.prefix', 'Withdrawal prefix']] },
];

export default function Settings() {
  const st = useStore();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [group, setGroup] = useState('Store');
  useEffect(() => { setDraft({ ...st.settings }); }, [st.settings]);

  const g = GROUPS.find(x => x.name === group)!;
  const dirty = g.keys.some(([k]) => (draft[k] ?? '') !== (st.settings[k] ?? ''));

  const save = async () => {
    const changes: Record<string, string> = {};
    for (const [k] of g.keys) if ((draft[k] ?? '') !== (st.settings[k] ?? '')) changes[k] = draft[k] ?? '';
    if (!Object.keys(changes).length) return;
    try {
      await api.put('/api/settings', changes);
      await st.refreshSettings();          // settings take effect immediately (spec #71)
      setSaved(true); setTimeout(() => setSaved(false), 1800);
      st.toast(`Saved: ${Object.keys(changes).join(', ')}`, 'ok');
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };

  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>⚙️ Settings — Owner Control Center</h2>
      {saved && <span className="badge ok">Saved ✔</span>}
    </div>
    <p className="muted" style={{ fontSize: 13 }}>Every setting here is enforced by the backend: currency formatting, POS behavior,
      Dasti availability, receipt content, approval thresholds, reference formats and more.</p>
    <div className="row" style={{ flexWrap: 'wrap', marginBottom: 12 }}>
      {GROUPS.map(x => <button key={x.name} className={group === x.name ? 'primary' : ''}
        onClick={() => setGroup(x.name)}>{x.icon} {x.name}</button>)}
    </div>
    <div className="card" style={{ maxWidth: 640 }}>
      <h3 style={{ marginTop: 0 }}>{g.icon} {g.name}</h3>
      {g.keys.map(([k, label]) => (
        <Field key={k} label={`${label}  ·  ${k}`}>
          <input value={draft[k] ?? ''} onChange={e => setDraft(p => ({ ...p, [k]: e.target.value }))} />
        </Field>))}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="primary" disabled={!dirty} onClick={save}>Save {g.name} settings</button>
      </div>
    </div>
  </div>;
}
