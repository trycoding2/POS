"""Returns (spec #25), stock adjustments/damage/expiry (spec #23), Dasti lifecycle (spec #15)."""
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.parties import Customer, Account, Dasti, DastiPayment
from app.models.transactions import Sale, Purchase, Return, ReturnItem
from app.services import inventory, ledger, audit, sync, notify
from app.services.refs import next_ref
from app.services.settings_service import get_setting, get_bool, get_num


# ------------------------------------------------------------------ returns

def customer_return(db: Session, *, user, device_id: str, sale_id: int, items: list[dict],
                    reason: str, refund_method: str = "cash", account_id: int | None = None,
                    stock_condition: str = "good") -> Return:
    """items: [{sale_item_id, qty}]. Original sale kept forever; status updated."""
    try:
        if not user.role_has_permission("sale.return"):
            raise HTTPException(403, "You do not have return permission.")
        if not reason.strip():
            raise HTTPException(400, "A reason is required for returns.")
        sale = db.get(Sale, sale_id)
        if not sale or sale.status == "voided":
            raise HTTPException(400, "Sale not found or voided; cannot return against it.")
        total = 0.0
        ritems = []
        for line in items:
            si = next((s for s in sale.items if s.id == line["sale_item_id"]), None)
            if not si:
                raise HTTPException(400, "Sale item not found in this sale.")
            qty = float(line["qty"])
            if qty <= 0 or qty > si.qty:
                raise HTTPException(400, f"Return quantity invalid (max {si.qty}).")
            amount = round(qty * si.unit_price - (si.discount * qty / si.qty), 6)
            total += amount
            ritems.append((si, qty, amount))
        if not ritems:
            raise HTTPException(400, "Nothing selected to return.")

        acc = None
        if refund_method == "cash":
            if not account_id:
                raise HTTPException(400, "Choose the cash account to refund from.")
            acc = db.get(Account, account_id)
            if not acc or not acc.is_active:
                raise HTTPException(400, "Refund account unavailable. Nothing was changed.")

        ret = Return(uuid=str(_uuid.uuid4()), ref=next_ref(db, "RET"), kind="customer",
                     sale_id=sale.id, customer_id=sale.customer_id, total_amount=round(total, 6),
                     refund_method=refund_method, account_id=account_id,
                     stock_condition=stock_condition, restock=(stock_condition == "good"),
                     reason=reason, user_id=user.id, device_id=device_id)
        db.add(ret)
        db.flush()
        for si, qty, amount in ritems:
            db.add(ReturnItem(return_id=ret.id, product_id=si.product_id, qty=qty,
                              unit_price=si.unit_price, line_total=amount))
            p = db.get(Product, si.product_id)
            if ret.restock:
                inventory.move(db, p, qty_change=qty, movement_type="customer_return",
                               user=user, device_id=device_id, reason=reason,
                               entity_type="return", entity_id=ret.id, entity_ref=ret.ref)
            si.qty_returned = getattr(si, "qty_returned", 0) + qty  # informational

        if refund_method == "cash":
            ledger.add_account_tx(db, acc.id, direction="out", amount=total, reason="return_refund",
                                  entity_type="return", entity_id=ret.id, entity_ref=ret.ref,
                                  user=user, device_id=device_id)
        elif refund_method == "khata_reduction" and sale.customer_id:
            ledger.add_customer_entry(db, sale.customer_id, entry_type="return",
                                      credit=total, entity_type="return", entity_id=ret.id,
                                      entity_ref=ret.ref, user=user, notes=reason)

        returned_all = all((s.qty - getattr(s, "qty_returned", 0)) <= 0 for s in sale.items)
        sale.status = "returned" if returned_all else "partially_returned"

        audit.log(db, user=user, device_id=device_id, module="returns", action="return",
                  entity="return", entity_id=ret.id, entity_ref=ret.ref,
                  new_value={"sale": sale.ref, "total": total, "method": refund_method},
                  reason=reason, amount=total, related_transaction=sale.ref)
        sync.enqueue(db, "return", ret.uuid, {"ref": ret.ref, "total": total}, device_id=device_id)
        db.commit()
        return ret
    except Exception:
        db.rollback()
        raise


def supplier_return(db: Session, *, user, device_id: str, purchase_id: int, items: list[dict],
                    reason: str, resolution: str = "supplier_credit",
                    account_id: int | None = None, condition: str = "damaged") -> Return:
    """items: [{purchase_item_id, qty}] — reduces stock and supplier payable (or refunds cash)."""
    try:
        if not reason.strip():
            raise HTTPException(400, "A reason is required.")
        pur = db.get(Purchase, purchase_id)
        if not pur:
            raise HTTPException(404, "Purchase not found.")
        total = 0.0
        ritems = []
        for line in items:
            pi = next((x for x in pur.items if x.id == line["purchase_item_id"]), None)
            if not pi:
                raise HTTPException(400, "Purchase item not found.")
            qty = float(line["qty"])
            if qty <= 0 or qty > pi.qty_received:
                raise HTTPException(400, f"Return quantity invalid (received {pi.qty_received}).")
            amount = round(qty * pi.cost_price, 6)
            total += amount
            ritems.append((pi, qty, amount))
        if not ritems:
            raise HTTPException(400, "Nothing selected.")

        ret = Return(uuid=str(_uuid.uuid4()), ref=next_ref(db, "RET"), kind="supplier",
                     purchase_id=pur.id, supplier_id=pur.supplier_id,
                     total_amount=round(total, 6), refund_method=resolution,
                     account_id=account_id, stock_condition=condition, restock=False,
                     reason=reason, user_id=user.id, device_id=device_id)
        db.add(ret)
        db.flush()
        for pi, qty, amount in ritems:
            db.add(ReturnItem(return_id=ret.id, product_id=pi.product_id, qty=qty,
                              unit_price=pi.cost_price, line_total=amount))
            p = db.get(Product, pi.product_id)
            inventory.move(db, p, qty_change=-qty, movement_type="supplier_return",
                           user=user, device_id=device_id, reason=reason,
                           entity_type="return", entity_id=ret.id, entity_ref=ret.ref)
            pi.qty_received -= qty

        if resolution == "supplier_credit":
            ledger.add_supplier_entry(db, pur.supplier_id, entry_type="return", debit=total,
                                      entity_type="return", entity_id=ret.id, entity_ref=ret.ref,
                                      user=user, notes=reason)
        elif resolution == "cash_refund":
            acc = db.get(Account, account_id) if account_id else None
            if not acc or not acc.is_active:
                raise HTTPException(400, "Refund account unavailable. Nothing was changed.")
            ledger.add_account_tx(db, acc.id, direction="in", amount=total,
                                  reason="supplier_return_refund", entity_type="return",
                                  entity_id=ret.id, entity_ref=ret.ref, user=user,
                                  device_id=device_id)
            ledger.add_supplier_entry(db, pur.supplier_id, entry_type="return", debit=total,
                                      entity_type="return", entity_id=ret.id, entity_ref=ret.ref,
                                      user=user, notes=reason)
        audit.log(db, user=user, device_id=device_id, module="returns", action="supplier_return",
                  entity="return", entity_id=ret.id, entity_ref=ret.ref,
                  new_value={"purchase": pur.ref, "total": total, "resolution": resolution},
                  reason=reason, amount=total, related_transaction=pur.ref)
        sync.enqueue(db, "return", ret.uuid, {"ref": ret.ref, "total": total}, device_id=device_id)
        db.commit()
        return ret
    except Exception:
        db.rollback()
        raise


# ------------------------------------------------------- stock adjustments etc.

def adjust_stock(db: Session, *, user, device_id: str, product_id: int, new_qty: float | None = None,
                 delta: float | None = None, movement_type: str = "adjustment",
                 reason: str = ""):
    try:
        if not user.role_has_permission("stock.adjust"):
            raise HTTPException(403, "You cannot adjust stock.")
        if not reason.strip():
            raise HTTPException(400, "Stock changes require a reason — no unexplained movements.")
        if movement_type not in ("adjustment", "damage", "expiry", "correction"):
            raise HTTPException(400, "Invalid adjustment type.")
        p = db.get(Product, product_id)
        if not p:
            raise HTTPException(404, "Product not found.")
        if new_qty is not None:
            delta = float(new_qty) - float(p.stock_qty or 0)
        if delta is None or delta == 0:
            raise HTTPException(400, "No quantity change requested.")
        thresh = get_num(db, "approval.stock_adjust_qty", 0)
        if thresh and abs(delta) >= thresh and not user.role_has_permission("approval.grant"):
            raise HTTPException(403,
                f"Adjustments of {abs(delta)}+ units need owner/manager approval.")
        mv = inventory.move(db, p, qty_change=delta, movement_type=movement_type, user=user,
                            device_id=device_id, reason=reason, make_ref=True)
        audit.log(db, user=user, device_id=device_id, module="inventory", action=movement_type,
                  entity="product", entity_id=p.id, entity_ref=p.name,
                  prev_value={"qty": mv.prev_qty}, new_value={"qty": mv.new_qty},
                  reason=reason, related_transaction=mv.ref)
        db.commit()
        return mv
    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------- dasti

def pay_dasti(db: Session, *, user, device_id: str, dasti_id: int, amount: float,
              account_id: int, notes: str = "") -> DastiPayment:
    try:
        if not user.role_has_permission("payment.receive"):
            raise HTTPException(403, "You cannot receive payments.")
        d = db.get(Dasti, dasti_id)
        if not d:
            raise HTTPException(404, "Dasti not found.")
        if d.status in ("settled", "cancelled"):
            raise HTTPException(400, f"Dasti {d.ref} is already {d.status}.")
        acc = db.get(Account, account_id)
        if not acc or not acc.is_active:
            raise HTTPException(400, "Account unavailable. Nothing was changed.")
        outstanding = round(d.amount - (d.paid_amount or 0), 6)
        if amount <= 0 or amount > outstanding + 0.0001:
            raise HTTPException(400, f"Amount must be between 0 and outstanding Rs.{outstanding}.")
        dp = DastiPayment(uuid=str(_uuid.uuid4()), ref=next_ref(db, "PAY"), dasti_id=d.id,
                          amount=amount, account_id=acc.id, received_by=user.id, notes=notes)
        db.add(dp)
        db.flush()
        d.paid_amount = round((d.paid_amount or 0) + amount, 6)
        d.status = "settled" if d.paid_amount >= d.amount - 0.0001 else "partial"
        if d.status == "settled":
            d.closed_at = datetime.now(timezone.utc)
        ledger.add_account_tx(db, acc.id, direction="in", amount=amount, reason="dasti_payment",
                              entity_type="dasti", entity_id=d.id, entity_ref=d.ref,
                              user=user, device_id=device_id)
        audit.log(db, user=user, device_id=device_id, module="dasti", action="payment",
                  entity="dasti", entity_id=d.id, entity_ref=d.ref, amount=amount,
                  new_value={"paid_total": d.paid_amount, "status": d.status},
                  related_transaction=d.ref)
        sync.enqueue(db, "dasti_payment", dp.uuid, {"ref": dp.ref, "amount": amount},
                     device_id=device_id)
        db.commit()
        if get_bool(db, "whatsapp.enabled") and d.phone:
            notify.queue_whatsapp(db, to=d.phone, template="dasti_receipt",
                                  message=f"Dasti {d.ref}: Rs.{amount:.0f} received. "
                                          f"Outstanding Rs.{max(d.amount-d.paid_amount,0):.0f} "
                                          f"— {get_setting(db,'store.name')}")
            db.commit()
        return dp
    except Exception:
        db.rollback()
        raise


def extend_dasti(db: Session, *, user, device_id: str, dasti_id: int, days: int, reason: str):
    from datetime import timedelta
    d = db.get(Dasti, dasti_id)
    if not d:
        raise HTTPException(404, "Dasti not found.")
    if d.status in ("settled", "cancelled"):
        raise HTTPException(400, "Cannot extend a closed dasti.")
    if not reason.strip():
        raise HTTPException(400, "Reason required for extension.")
    prev_due = d.due_date
    base = d.due_date or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    d.due_date = base + timedelta(days=days)
    audit.log(db, user=user, device_id=device_id, module="dasti", action="extend",
              entity="dasti", entity_id=d.id, entity_ref=d.ref,
              prev_value={"due": prev_due}, new_value={"due": d.due_date}, reason=reason)
    db.commit()
    return d


def cancel_dasti(db: Session, *, user, device_id: str, dasti_id: int, reason: str):
    """Cancellation record — original dasti never erased (spec #33)."""
    d = db.get(Dasti, dasti_id)
    if not d:
        raise HTTPException(404, "Dasti not found.")
    if d.status == "settled":
        raise HTTPException(400, "Settled dasti cannot be cancelled; use an adjustment instead.")
    if not reason.strip():
        raise HTTPException(400, "Reason required.")
    if (d.paid_amount or 0) > 0:
        raise HTTPException(400, "Partially paid dasti cannot be cancelled; settle via adjustment.")
    prev = d.status
    d.status = "cancelled"
    d.notes = (d.notes or "") + f" | Cancelled by {user.username}: {reason}"
    d.closed_at = datetime.now(timezone.utc)
    audit.log(db, user=user, device_id=device_id, module="dasti", action="cancel",
              entity="dasti", entity_id=d.id, entity_ref=d.ref,
              prev_value={"status": prev}, new_value={"status": "cancelled"}, reason=reason,
              amount=d.amount)
    db.commit()
    return d
