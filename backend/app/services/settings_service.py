"""Settings service — every setting actually drives behavior (spec #71)."""
import json
from sqlalchemy.orm import Session

from app.models.system import Setting

DEFAULTS = {
    # store
    "store.name": "My Karyana Store",
    "store.address": "",
    "store.phone": "",
    "store.whatsapp": "",
    "store.email": "",
    "store.logo": "",
    # currency (never hardcoded PKR everywhere)
    "currency.symbol": "Rs.",
    "currency.code": "PKR",
    "currency.decimals": "0",
    "currency.thousand_sep": ",",
    "currency.decimal_sep": ".",
    "currency.position": "prefix",
    # locale / appearance
    "ui.language": "en",
    "ui.theme": "light",
    "ui.font_size": "medium",
    "timezone": "Asia/Karachi",
    "date_format": "DD MMM YYYY",
    # tax
    "tax.enabled": "false",
    "tax.percent": "0",
    # POS behaviour
    "pos.barcode_auto_add": "true",
    "pos.manual_add_ask_qty": "true",
    "pos.show_category_buttons": "true",
    "pos.default_customer_walkin": "true",
    "pos.allow_negative_stock": "false",
    "pos.shortcuts": json.dumps({"F1": "search", "F2": "customer", "F3": "discount",
                                 "F4": "hold", "F5": "resume", "F6": "payment",
                                 "F7": "new_sale", "F8": "return", "F9": "print"}),
    # payment methods enabled
    "payments.cash": "true",
    "payments.bank": "true",
    "payments.wallet_easypaisa": "true",
    "payments.wallet_jazzcash": "true",
    "payments.credit_khata": "true",
    "payments.dasti": "true",
    "payments.split": "true",
    # dasti defaults
    "dasti.default_due_days": "1",
    "dasti.require_phone": "false",
    # khata rules
    "khata.default_credit_limit": "0",
    "khata.reminder_days": "7",
    # stock
    "stock.low_stock_default": "5",
    "stock.expiring_soon_days": "30",
    # invoice numbering (prefixes configurable)
    "ref.SALE.prefix": "SALE",
    "ref.PUR.prefix": "PUR",
    "ref.PAY.prefix": "PAY",
    "ref.RET.prefix": "RET",
    "ref.EXP.prefix": "EXP",
    "ref.DST.prefix": "DST",
    "ref.ADJ.prefix": "ADJ",
    "ref.ORD.prefix": "ORD",
    "ref.WDR.prefix": "WDR",
    "ref.format": "{prefix}-{yyyymmdd}-{seq:06d}",
    # receipt template
    "receipt.header": "Thank you for shopping!",
    "receipt.footer": "Goods once sold are exchangeable within 7 days with receipt.",
    "receipt.paper_size": "80mm",
    "receipt.show_customer": "true",
    "receipt.show_cashier": "true",
    "receipt.show_discount": "true",
    "receipt.show_payment_method": "true",
    "receipt.show_balance": "true",
    "receipt.printer": "",
    # notifications
    "whatsapp.enabled": "false",
    "whatsapp.auto_sale_receipt": "false",
    "whatsapp.auto_khata_reminder": "false",
    "whatsapp.auto_dasti_reminder": "true",
    "notify.daily_owner_report": "false",
    # sync/backup
    "sync.enabled": "false",
    "backup.auto_local": "false",
    "backup.auto_enabled": "true",
    "backup.auto_interval_hours": "24",
    "backup.keep_count": "14",
    # approvals thresholds (0 = disabled)
    "approval.discount_percent": "0",
    "approval.void_sale": "false",
    "approval.stock_adjust_qty": "0",
    "approval.expense_amount": "0",
    "approval.supplier_payment_amount": "0",
    "approval.price_change": "false",
}


def get_setting(db: Session, key: str, default=None) -> str:
    row = db.get(Setting, key)
    if row is not None and row.value is not None:
        return row.value
    if default is not None:
        return default
    return DEFAULTS.get(key, "")


def get_bool(db: Session, key: str) -> bool:
    return str(get_setting(db, key, "")).lower() in ("1", "true", "yes")


def get_num(db: Session, key: str, default: float = 0) -> float:
    try:
        return float(get_setting(db, key, str(default)))
    except ValueError:
        return default


def set_setting(db: Session, key: str, value: str, user_id: int = None):
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key)
        db.add(row)
    row.value = str(value)
    row.updated_by = user_id
    db.commit()


def all_settings(db: Session) -> dict:
    out = dict(DEFAULTS)
    for row in db.query(Setting).all():
        if row.value is not None:
            out[row.key] = row.value
    return out


def ensure_defaults(db: Session):
    for k, v in DEFAULTS.items():
        if db.get(Setting, k) is None:
            db.add(Setting(key=k, value=v))
    db.commit()
