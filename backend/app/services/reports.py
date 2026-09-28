"""Reports & dashboard (spec #29-#31, #51). All figures derived from transactional data."""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models.transactions import (Sale, SaleItem, Purchase, Expense, CustomerLedgerEntry,
                                     SupplierLedgerEntry, StockMovement, Return,
                                     OwnerWithdrawal)
from app.models.catalog import Product, Batch
from app.models.parties import Customer, Supplier, Dasti, Account, AccountTransaction
from app.services import ledger
from app.services.settings_service import get_num


def _day_range(db_date_field, start: datetime | None, end: datetime | None):
    conds = []
    if start:
        conds.append(db_date_field >= start)
    if end:
        conds.append(db_date_field <= end)
    return conds


def profit_summary(db: Session, start: datetime | None, end: datetime | None) -> dict:
    """Revenue / COGS / gross profit / expenses / net profit — kept conceptually separate."""
    active_sale = Sale.status.in_(["completed", "partially_returned", "returned"])
    revenue = db.query(func.coalesce(func.sum(Sale.grand_total - Sale.tax_total), 0)).filter(
        active_sale, *_day_range(Sale.created_at, start, end)).scalar()
    cogs = db.query(func.coalesce(func.sum(SaleItem.line_total * 0 + SaleItem.cost_price * SaleItem.qty), 0)) \
        .join(Sale, and_(Sale.id == SaleItem.sale_id, active_sale)) \
        .filter(*_day_range(Sale.created_at, start, end)).scalar()
    # returns reduce revenue & COGS
    ret_amt = db.query(func.coalesce(func.sum(Return.total_amount), 0)).filter(
        Return.kind == "customer", *_day_range(Return.created_at, start, end)).scalar()
    discounts = db.query(func.coalesce(func.sum(Sale.discount_total), 0)).filter(
        active_sale, *_day_range(Sale.created_at, start, end)).scalar()
    expenses = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.status == "approved", *_day_range(Expense.occurred_at, start, end)).scalar()
    withdrawals = db.query(func.coalesce(func.sum(OwnerWithdrawal.amount), 0)).filter(
        *_day_range(OwnerWithdrawal.occurred_at, start, end)).scalar()
    revenue = float(revenue) - float(ret_amt)
    gross = round(float(revenue) - float(cogs), 6)
    net = round(gross - float(expenses), 6)   # withdrawals are NOT expenses (spec #28/#51)
    return {
        "revenue": round(float(revenue), 6), "cogs": round(float(cogs), 6),
        "gross_profit": gross, "expenses": round(float(expenses), 6),
        "net_profit": net, "discounts_given": round(float(discounts), 6),
        "returns": round(float(ret_amt), 6), "owner_withdrawals": round(float(withdrawals), 6),
        "period": {"start": start.isoformat() if start else None,
                   "end": end.isoformat() if end else None},
    }


def sales_report(db: Session, start=None, end=None, group_by: str = "day") -> list[dict]:
    q = db.query(Sale).filter(Sale.status != "voided", *_day_range(Sale.created_at, start, end))
    rows = q.all()
    buckets: dict[str, dict] = {}
    for s in rows:
        key = s.created_at.strftime("%Y-%m-%d") if group_by == "day" else \
            (s.device_id if group_by == "device" else
             (str(s.user_id) if group_by == "employee" else "all"))
        b = buckets.setdefault(key, {"group": key, "count": 0, "total": 0, "discount": 0,
                                     "credit": 0, "paid": 0})
        b["count"] += 1
        b["total"] += s.grand_total
        b["discount"] += s.discount_total
        b["credit"] += s.credit_amount
        b["paid"] += s.paid_total
    return sorted(buckets.values(), key=lambda r: r["group"], reverse=True)


def product_sales_report(db: Session, start=None, end=None) -> list[dict]:
    rows = db.query(
        Product.id, Product.name,
        func.sum(SaleItem.qty).label("qty"),
        func.sum(SaleItem.line_total).label("amount"),
        func.sum(SaleItem.cost_price * SaleItem.qty).label("cogs"),
    ).join(SaleItem, SaleItem.product_id == Product.id) \
     .join(Sale, and_(Sale.id == SaleItem.sale_id, Sale.status != "voided")) \
     .filter(*_day_range(Sale.created_at, start, end)) \
     .group_by(Product.id).order_by(func.sum(SaleItem.line_total).desc()).all()
    return [{"product_id": r.id, "name": r.name, "qty": float(r.qty or 0),
             "amount": round(float(r.amount or 0), 2),
             "profit": round(float(r.amount or 0) - float(r.cogs or 0), 2)} for r in rows]


def payment_method_report(db: Session, start=None, end=None) -> list[dict]:
    from app.models.transactions import SalePayment
    rows = db.query(Account.name, Account.type, func.sum(SalePayment.amount)) \
        .join(SalePayment, SalePayment.account_id == Account.id) \
        .join(Sale, Sale.id == SalePayment.sale_id).filter(Sale.status != "voided",
                                                            *_day_range(Sale.created_at, start, end)) \
        .group_by(Account.id).all()
    return [{"account": n, "type": t, "amount": round(float(a or 0), 2)} for n, t, a in rows]


def inventory_snapshot(db: Session) -> dict:
    prods = db.query(Product).filter(Product.is_active == True).all()  # noqa: E712
    low_default = get_num(db, "stock.low_stock_default", 5)
    expiring_days = get_num(db, "stock.expiring_soon_days", 30)
    now = datetime.now(timezone.utc)
    out = {"total_products": len(prods), "stock_value_cost": 0.0, "stock_value_retail": 0.0,
           "low_stock": [], "out_of_stock": [], "expiring_soon": [], "expired": [],
           "products": []}
    for p in prods:
        qty = float(p.stock_qty or 0)
        out["stock_value_cost"] += qty * float(p.cost_price or 0)
        out["stock_value_retail"] += qty * float(p.retail_price or 0)
        minv = float(p.min_stock or 0) or low_default
        out["products"].append({"id": p.id, "name": p.name, "sku": p.sku,
                                "qty": qty, "min": minv,
                                "cost": float(p.cost_price or 0),
                                "retail": float(p.retail_price or 0),
                                "stock_value_cost": round(qty * float(p.cost_price or 0), 2)})
        if qty <= 0:
            out["out_of_stock"].append({"id": p.id, "name": p.name})
        elif qty <= minv:
            out["low_stock"].append({"id": p.id, "name": p.name, "qty": qty, "min": minv})
    for b in db.query(Batch).filter(Batch.qty_remaining > 0).all():
        if not b.expiry_date:
            continue
        exp = b.expiry_date if b.expiry_date.tzinfo else b.expiry_date.replace(tzinfo=timezone.utc)
        days = (exp - now).days
        item = {"batch_id": b.id, "product_id": b.product_id, "batch_no": b.batch_no,
                "qty": b.qty_remaining, "expiry": exp.strftime("%Y-%m-%d")}
        if days < 0:
            out["expired"].append(item)
        elif days <= expiring_days:
            out["expiring_soon"].append(item)
    out["stock_value_cost"] = round(out["stock_value_cost"], 2)
    out["stock_value_retail"] = round(out["stock_value_retail"], 2)
    return out


def receivables(db: Session) -> dict:
    khata_total = 0.0
    overdue_total = 0.0
    customers_out = []
    for c in db.query(Customer).filter(Customer.is_active == True).all():  # noqa: E712
        bal = ledger.customer_balance(db, c.id)
        if bal > 0.0001:
            khata_total += bal
            customers_out.append({"customer_id": c.id, "name": c.name, "phone": c.phone,
                                  "balance": round(bal, 2), "credit_limit": c.credit_limit})
    dasti_out = 0.0
    overdue_dastis = []
    now = datetime.now(timezone.utc)
    for d in db.query(Dasti).filter(Dasti.status.in_(["pending", "partial"])).all():
        outstanding = d.amount - (d.paid_amount or 0)
        dasti_out += outstanding
        due = d.due_date
        if due and due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due and due < now:
            overdue_total += outstanding
            overdue_dastis.append({"dasti_id": d.id, "ref": d.ref, "name": d.customer_name,
                                   "outstanding": round(outstanding, 2),
                                   "due": due.strftime("%Y-%m-%d")})
    return {"total_receivable": round(khata_total, 2), "dasti_outstanding": round(dasti_out, 2),
            "overdue_dasti": round(overdue_total, 2), "customers": customers_out,
            "overdue_dastis": overdue_dastis}


def payables(db: Session) -> dict:
    total = 0.0
    rows = []
    for s in db.query(Supplier).filter(Supplier.is_active == True).all():  # noqa: E712
        bal = ledger.supplier_balance(db, s.id)
        if bal > 0.0001:
            total += bal
            rows.append({"supplier_id": s.id, "name": s.name, "payable": round(bal, 2)})
    return {"total_payable": round(total, 2), "suppliers": rows}


def cash_position(db: Session) -> list[dict]:
    out = []
    for a in db.query(Account).filter(Account.is_active == True).all():  # noqa: E712
        out.append({"account_id": a.id, "name": a.name, "type": a.type,
                    "balance": round(ledger.account_balance(db, a.id), 2)})
    return out


def dashboard(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ps = profit_summary(db, day_start, now)
    rec = receivables(db)
    pay = payables(db)
    inv = inventory_snapshot(db)
    today_purchases = db.query(func.coalesce(func.sum(Purchase.grand_total), 0)).filter(
        Purchase.created_at >= day_start, Purchase.status != "cancelled").scalar()
    recent = db.query(Sale).order_by(Sale.id.desc()).limit(8).all()
    alerts = []
    if inv["low_stock"]:
        alerts.append({"type": "low_stock", "count": len(inv["low_stock"])})
    if inv["out_of_stock"]:
        alerts.append({"type": "out_of_stock", "count": len(inv["out_of_stock"])})
    if inv["expiring_soon"]:
        alerts.append({"type": "expiring_soon", "count": len(inv["expiring_soon"])})
    if inv["expired"]:
        alerts.append({"type": "expired", "count": len(inv["expired"])})
    if rec["overdue_dasti"]:
        alerts.append({"type": "dasti_overdue", "amount": rec["overdue_dasti"]})
    from app.models.system import Notification, SyncQueue
    failed_notif = db.query(Notification).filter(Notification.status == "failed").count()
    if failed_notif:
        alerts.append({"type": "failed_notifications", "count": failed_notif})
    pending_sync = db.query(SyncQueue).filter(
        SyncQueue.status.in_(["pending", "failed", "conflict", "retry"])).count()
    from app.services.settings_service import get_bool
    sync_enabled = get_bool(db, "sync.enabled")
    if sync_enabled and pending_sync:
        alerts.append({"type": "unsynced_records", "count": pending_sync})
    # pending approvals (spec #36/#55)
    from app.models.auth import Approval
    pend_appr = db.query(Approval).filter(Approval.status == "pending").count()
    if pend_appr:
        alerts.append({"type": "pending_approvals", "count": pend_appr})
    # top products today (owner dashboard drill-down)
    tp_rows = db.query(Product.name, func.sum(SaleItem.qty), func.sum(SaleItem.line_total)) \
        .join(SaleItem, SaleItem.product_id == Product.id) \
        .join(Sale, and_(Sale.id == SaleItem.sale_id, Sale.status != "voided")) \
        .filter(Sale.created_at >= day_start) \
        .group_by(Product.id).order_by(func.sum(SaleItem.line_total).desc()).limit(8).all()
    top_products = [{"name": n, "qty": float(q or 0), "revenue": round(float(a or 0), 2)}
                    for n, q, a in tp_rows]
    return {
        "today_sales": ps["revenue"], "today_gross_profit": ps["gross_profit"],
        "today_expenses": ps["expenses"], "today_net_profit_estimate": ps["net_profit"],
        "today_discounts": ps["discounts_given"], "today_returns": ps["returns"],
        "today_purchases": round(float(today_purchases), 2),
        "cash_accounts": cash_position(db),
        "receivables": rec["total_receivable"], "dasti_outstanding": rec["dasti_outstanding"],
        "overdue_dasti": rec["overdue_dasti"],
        "payables": pay["total_payable"],
        "alerts": alerts,
        "top_products": top_products,
        "recent_sales": [{"id": s.id, "ref": s.ref, "total": s.grand_total,
                          "status": s.status,
                          "at": s.created_at.isoformat() if s.created_at else None}
                         for s in recent],
        "inventory": {"stock_value_cost": round(inv["stock_value_cost"], 2),
                      "total_products": inv["total_products"],
                      "low_stock_count": len(inv["low_stock"]),
                      "out_of_stock_count": len(inv["out_of_stock"])},
        "low_stock_count": len(inv["low_stock"]),
        "out_of_stock_count": len(inv["out_of_stock"]),
        "expiring_soon_count": len(inv["expiring_soon"]),
        "expired_count": len(inv["expired"]),
        "alerts": alerts,
        "recent_sales": [{"ref": s.ref, "total": s.grand_total, "status": s.status,
                          "at": s.created_at.isoformat(), "user_id": s.user_id,
                          "device": s.device_id} for s in recent],
        "sync_pending": pending_sync,
    }


def customer_timeline(db: Session, customer_id: int, limit: int = 200) -> list[dict]:
    entries = db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.customer_id == customer_id).order_by(
        CustomerLedgerEntry.id.desc()).limit(limit).all()
    running = ledger.customer_balance(db, customer_id)
    out = []
    bal = running
    for e in reversed(entries):
        out.append({"at": e.occurred_at.isoformat(), "type": e.entry_type,
                    "debit": e.debit, "credit": e.credit, "ref": e.entity_ref,
                    "notes": e.notes, "user_id": e.user_id})
    # show balance-after per row walking forward
    walk = 0.0
    c = db.get(Customer, customer_id)
    walk = float(c.opening_balance or 0) if c else 0.0
    for row in out:
        walk += row["debit"] - row["credit"]
        row["balance_after"] = round(walk, 2)
    return list(reversed(out))


def supplier_timeline(db: Session, supplier_id: int, limit: int = 200) -> list[dict]:
    entries = db.query(SupplierLedgerEntry).filter(
        SupplierLedgerEntry.supplier_id == supplier_id).order_by(
        SupplierLedgerEntry.id.desc()).limit(limit).all()
    s = db.get(Supplier, supplier_id)
    out = []
    for e in reversed(entries):
        out.append({"at": e.occurred_at.isoformat(), "type": e.entry_type,
                    "debit": e.debit, "credit": e.credit, "ref": e.entity_ref,
                    "notes": e.notes})
    walk = float(s.opening_balance or 0) if s else 0.0
    for row in out:
        walk += row["credit"] - row["debit"]
        row["balance_after"] = round(walk, 2)
    return list(reversed(out))


def product_timeline(db: Session, product_id: int, limit: int = 200) -> list[dict]:
    mvs = db.query(StockMovement).filter(StockMovement.product_id == product_id).order_by(
        StockMovement.id.desc()).limit(limit).all()
    return [{"at": m.occurred_at.isoformat(), "type": m.movement_type, "change": m.change,
             "new_qty": m.new_qty, "reason": m.reason, "ref": m.entity_ref,
             "user_id": m.user_id, "device": m.device_id} for m in reversed(mvs)]


def stock_traceability_check(db: Session, product_id: int) -> dict:
    """Verify current stock equals sum of movements (spec #50)."""
    p = db.get(Product, product_id)
    total = db.query(func.coalesce(func.sum(StockMovement.change), 0)).filter(
        StockMovement.product_id == product_id).scalar()
    return {"product": p.name, "current_stock": float(p.stock_qty or 0),
            "sum_of_movements": round(float(total), 6),
            "consistent": abs(float(p.stock_qty or 0) - float(total)) < 1e-6}
