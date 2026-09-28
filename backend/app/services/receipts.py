"""Receipts: plain-text thermal (80mm/58mm), HTML print view, and PDF via ReportLab (spec #37/#60).

All layout fields come from settings — nothing hardcoded. If printing fails the
transaction remains safely stored (receipt is generated from stored data on demand).
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdfcanvas
from sqlalchemy.orm import Session

from app.models.transactions import Sale
from app.models.parties import Customer
from app.services.settings_service import get_setting, get_bool


def fmt_money(db: Session, value: float) -> str:
    sym = get_setting(db, "currency.symbol", "Rs.")
    dec = int(float(get_setting(db, "currency.decimals", "0")))
    tsep = get_setting(db, "currency.thousand_sep", ",")
    dsep = get_setting(db, "currency.decimal_sep", ".")
    s = f"{abs(value):,.{dec}f}".replace(",", "#").replace(".", dsep).replace("#", tsep)
    neg = "-" if value < 0 else ""
    pos = get_setting(db, "currency.position", "prefix")
    return f"{neg}{sym}{s}" if pos == "prefix" else f"{neg}{s}{sym}"


def receipt_text(db: Session, sale: Sale) -> str:
    width = 42 if get_setting(db, "receipt.paper_size", "80mm") == "80mm" else 32
    lines = []
    lines.append(get_setting(db, "store.name").center(width))
    if get_setting(db, "store.address"):
        lines.append(get_setting(db, "store.address").center(width))
    contact = " | ".join(x for x in [get_setting(db, "store.phone")] if x)
    if contact:
        lines.append(contact.center(width))
    lines.append("-" * width)
    lines.append(f"Receipt: {sale.ref}")
    lines.append(f"Date: {sale.created_at.strftime('%d %b %Y %H:%M')}")
    if get_bool(db, "receipt.show_customer"):
        cust = db.get(Customer, sale.customer_id) if sale.customer_id else None
        lines.append(f"Customer: {cust.name if cust else 'Walk-in'}")
    if get_bool(db, "receipt.show_cashier"):
        from app.models.auth import User
        u = db.get(User, sale.user_id)
        lines.append(f"Cashier: {u.full_name or u.username if u else ''}")
    lines.append("-" * width)
    for it in sale.items:
        from app.models.catalog import Product
        p = db.get(Product, it.product_id)
        name = (p.name if p else "?")[:width - 12]
        line_total = fmt_money(db, it.line_total)
        qty_price = f"{it.qty:g} x {fmt_money(db, it.unit_price)}"
        pad = width - len(name) - len(line_total) - 1
        lines.append(f"{name}{' ' * max(pad, 1)}{line_total}")
        lines.append(f"  {qty_price}")
    lines.append("-" * width)
    lines.append(f"Subtotal:{fmt_money(db, sale.subtotal).rjust(width - 9)}")
    if get_bool(db, "receipt.show_discount") and sale.discount_total:
        lines.append(f"Discount:{fmt_money(db, -sale.discount_total).rjust(width - 9)}")
    if sale.tax_total:
        lines.append(f"Tax:{fmt_money(db, sale.tax_total).rjust(width - 9)}")
    lines.append(f"TOTAL:{fmt_money(db, sale.grand_total).rjust(width - 7)}")
    if get_bool(db, "receipt.show_payment_method"):
        for sp in sale.payments:
            from app.models.parties import Account
            a = db.get(Account, sp.account_id)
            lines.append(f"Paid ({a.name if a else '?'}):{fmt_money(db, sp.amount).rjust(width - 20)}")
    if sale.credit_amount:
        lines.append(f"Credit Due:{fmt_money(db, sale.credit_amount).rjust(width - 13)}")
    if get_bool(db, "receipt.show_balance") and sale.customer_id:
        from app.services import ledger
        bal = ledger.customer_balance(db, sale.customer_id)
        if bal:
            lines.append(f"Balance:{fmt_money(db, bal).rjust(width - 9)}")
    lines.append("=" * width)
    hdr = get_setting(db, "receipt.header")
    ftr = get_setting(db, "receipt.footer")
    if hdr:
        lines.append(hdr.center(width))
    if ftr:
        lines.append(ftr.center(width))
    return "\n".join(lines)


def receipt_pdf_bytes(db: Session, sale: Sale) -> bytes:
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    text = receipt_text(db, sale)
    y = A4[1] - 60
    for line in text.split("\n"):
        c.setFont("Courier", 10)
        c.drawString(60, y, line[:80])
        y -= 14
        if y < 60:
            c.showPage()
            y = A4[1] - 60
    c.save()
    return buf.getvalue()
