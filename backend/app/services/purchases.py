"""Purchases, supplier payments, purchase orders and receiving (spec #19-#21)."""
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.catalog import Product, Batch
from app.models.parties import Supplier, Account
from app.models.transactions import (Purchase, PurchaseItem, PurchasePayment,
                                     PurchaseOrder, PurchaseOrderItem)
from app.services import inventory, ledger, audit, sync
from app.services.refs import next_ref
from app.services.settings_service import get_num


def create_purchase(db: Session, *, user, device_id: str, supplier_id: int | None,
                    supplier_name: str | None, items: list[dict], invoice_no: str = "",
                    paid_amount: float = 0, account_id: int | None = None,
                    discount_total: float = 0, notes: str = "",
                    order_id: int | None = None, receive_now: bool = True) -> Purchase:
    """supplier_id None + supplier_name => random/temporary seller record is auto-created
    (still a permanent transaction record — spec #19)."""
    try:
        if not items:
            raise HTTPException(400, "Purchase has no items.")
        if supplier_id:
            supplier = db.get(Supplier, supplier_id)
            if not supplier:
                raise HTTPException(404, "Supplier not found.")
        else:
            supplier = Supplier(uuid=str(_uuid.uuid4()),
                                name=supplier_name or "Temporary / Unknown",
                                is_temporary=True, created_by=user.id)
            db.add(supplier)
            db.flush()
            audit.log(db, user=user, device_id=device_id, module="suppliers", action="create",
                      entity="supplier", entity_id=supplier.id, entity_ref=supplier.name,
                      new_value={"temporary": True}, reason="Auto-created for quick purchase")

        subtotal = 0.0
        resolved = []
        for line in items:
            p = db.get(Product, line["product_id"])
            if not p:
                raise HTTPException(400, f"Product id {line.get('product_id')} not found.")
            qty = float(line.get("qty", 0))
            cost = float(line.get("cost_price", 0))
            free = float(line.get("qty_free", 0))
            disc = float(line.get("discount", 0))
            if qty <= 0 or cost < 0:
                raise HTTPException(400, f"Invalid quantity/cost for {p.name}. Nothing saved.")
            if cost != float(p.cost_price or 0) and not user.role_has_permission("cost.change"):
                raise HTTPException(403, f"You may not change purchase cost of {p.name}.")
            line_total = round(qty * cost - disc, 6)
            subtotal += qty * cost
            resolved.append((p, qty, free, cost, disc, line_total,
                             line.get("batch_no"), line.get("expiry_date")))

        grand = round(subtotal - discount_total, 6)
        paid_amount = float(paid_amount or 0)
        if paid_amount > 0 and not account_id:
            raise HTTPException(400, "Select the account the purchase was paid from.")
        if paid_amount > grand:
            raise HTTPException(400, "Paid amount cannot exceed purchase total.")
        due = round(grand - paid_amount, 6)

        pur = Purchase(uuid=str(_uuid.uuid4()), ref=next_ref(db, "PUR"), supplier_id=supplier.id,
                       order_id=order_id, invoice_no=invoice_no, subtotal=round(subtotal, 6),
                       discount_total=round(discount_total, 6), grand_total=grand,
                       paid_amount=paid_amount, due_amount=due,
                       status="received" if receive_now else "draft",
                       user_id=user.id, device_id=device_id, notes=notes)
        db.add(pur)
        db.flush()

        for (p, qty, free, cost, disc, line_total, batch_no, expiry) in resolved:
            pi = PurchaseItem(purchase_id=pur.id, product_id=p.id, qty_ordered=qty,
                              qty_received=qty if receive_now else 0, qty_free=free,
                              cost_price=cost, discount=disc, line_total=line_total,
                              batch_no=batch_no, expiry_date=expiry)
            db.add(pi)
            if receive_now:
                # weighted average cost update (audited via price history below)
                old_cost = float(p.cost_price or 0)
                stock = float(p.stock_qty or 0)
                if stock + qty > 0:
                    new_cost = round((old_cost * stock + cost * qty) / (stock + qty), 6)
                else:
                    new_cost = cost
                if abs(new_cost - old_cost) > 1e-9:
                    from app.models.catalog import PriceHistory
                    db.add(PriceHistory(product_id=p.id, field="cost", old_value=old_cost,
                                        new_value=new_cost, reason=f"Purchase {pur.ref}",
                                        changed_by=user.id))
                    p.cost_price = new_cost
                inventory.move(db, p, qty_change=qty, movement_type="purchase", user=user,
                               device_id=device_id, entity_type="purchase",
                               entity_id=pur.id, entity_ref=pur.ref)
                if free:
                    inventory.move(db, p, qty_change=free, movement_type="free_item", user=user,
                                   device_id=device_id, reason=f"Free qty on {pur.ref}",
                                   entity_type="purchase", entity_id=pur.id, entity_ref=pur.ref)
                if batch_no or expiry:
                    db.add(Batch(product_id=p.id, batch_no=batch_no, expiry_date=expiry,
                                 qty_in=qty, qty_remaining=qty, purchase_id=pur.id))

        # supplier ledger: credit portion increases payable
        if due > 0:
            ledger.add_supplier_entry(db, supplier.id, entry_type="purchase", credit=due,
                                      entity_type="purchase", entity_id=pur.id,
                                      entity_ref=pur.ref, user=user)
        if paid_amount > 0:
            acc = db.get(Account, account_id)
            if not acc or not acc.is_active:
                raise HTTPException(400, "Payment account unavailable. Nothing was changed.")
            ledger.add_account_tx(db, acc.id, direction="out", amount=paid_amount,
                                  reason="purchase_payment", entity_type="purchase",
                                  entity_id=pur.id, entity_ref=pur.ref, user=user,
                                  device_id=device_id)
            pp = PurchasePayment(uuid=str(_uuid.uuid4()), ref=next_ref(db, "PAY"),
                                 purchase_id=pur.id, supplier_id=supplier.id,
                                 amount=paid_amount, account_id=acc.id, user_id=user.id,
                                 device_id=device_id)
            db.add(pp)
            ledger.add_supplier_entry(db, supplier.id, entry_type="purchase_payment",
                                      debit=paid_amount, entity_type="purchase",
                                      entity_id=pur.id, entity_ref=pur.ref, user=user)

        if order_id:
            _update_order_receipts(db, order_id)

        audit.log(db, user=user, device_id=device_id, module="purchases", action="create",
                  entity="purchase", entity_id=pur.id, entity_ref=pur.ref,
                  new_value={"total": grand, "paid": paid_amount, "due": due,
                             "supplier": supplier.name},
                  amount=grand, related_transaction=pur.ref)
        sync.enqueue(db, "purchase", pur.uuid, {"ref": pur.ref, "grand_total": grand},
                     device_id=device_id)
        db.commit()
        return pur
    except Exception:
        db.rollback()
        raise


def pay_supplier(db: Session, *, user, supplier_id: int, amount: float, account_id: int,
                 device_id: str, purchase_id: int | None = None, notes: str = ""):
    try:
        threshold = get_num(db, "approval.supplier_payment_amount", 0)
        if threshold and amount > threshold and not user.role_has_permission("approval.grant"):
            raise HTTPException(403,
                f"Supplier payments above Rs.{threshold} require owner/manager approval.")
        sup = db.get(Supplier, supplier_id)
        acc = db.get(Account, account_id)
        if not sup:
            raise HTTPException(404, "Supplier not found.")
        if not acc or not acc.is_active:
            raise HTTPException(400, "Payment account unavailable. Nothing was changed.")
        if amount <= 0:
            raise HTTPException(400, "Amount must be positive.")
        ref = next_ref(db, "PAY")
        pp = PurchasePayment(uuid=str(_uuid.uuid4()), ref=ref, purchase_id=purchase_id,
                             supplier_id=sup.id, amount=amount, account_id=acc.id,
                             user_id=user.id, device_id=device_id, notes=notes)
        db.add(pp)
        db.flush()
        ledger.add_account_tx(db, acc.id, direction="out", amount=amount,
                              reason="supplier_payment", entity_type="supplier_payment",
                              entity_id=pp.id, entity_ref=ref, user=user, device_id=device_id)
        ledger.add_supplier_entry(db, sup.id, entry_type="purchase_payment", debit=amount,
                                  entity_type="supplier_payment", entity_id=pp.id,
                                  entity_ref=ref, user=user, notes=notes)
        if purchase_id:
            pur = db.get(Purchase, purchase_id)
            if pur and pur.supplier_id == sup.id:
                applied = min(amount, float(pur.due_amount or 0))
                pur.paid_amount = round(float(pur.paid_amount or 0) + applied, 6)
                pur.due_amount = round(float(pur.due_amount or 0) - applied, 6)
                pp.purchase_id = pur.id
                if pur.due_amount <= 0.004 and pur.status in ("received", "partially_received"):
                    pur.status = "paid"
        audit.log(db, user=user, device_id=device_id, module="suppliers", action="payment",
                  entity="supplier_payment", entity_id=pp.id, entity_ref=ref,
                  amount=amount, related_transaction=ref,
                  new_value={"supplier": sup.name, "paid": amount})
        sync.enqueue(db, "supplier_payment", pp.uuid, {"ref": ref, "amount": amount},
                     device_id=device_id)
        db.commit()
        return pp
    except Exception:
        db.rollback()
        raise


def create_order(db: Session, *, user, device_id, supplier_id: int, items: list[dict],
                 notes: str = "", status: str = "draft") -> PurchaseOrder:
    try:
        sup = db.get(Supplier, supplier_id)
        if not sup:
            raise HTTPException(404, "Supplier not found.")
        if not items:
            raise HTTPException(400, "Order has no items.")
        o = PurchaseOrder(uuid=str(_uuid.uuid4()), ref=next_ref(db, "ORD"),
                          supplier_id=sup.id, status=status, user_id=user.id, notes=notes)
        db.add(o)
        db.flush()
        for line in items:
            p = db.get(Product, line["product_id"])
            if not p:
                raise HTTPException(400, f"Product id {line['product_id']} not found.")
            db.add(PurchaseOrderItem(order_id=o.id, product_id=p.id,
                                     qty_ordered=float(line.get("qty_ordered", line.get("qty", 0)) or 0),
                                     expected_cost=float(line.get("expected_cost", 0) or 0)))
        audit.log(db, user=user, device_id=device_id, module="orders", action="create",
                  entity="purchase_order", entity_id=o.id, entity_ref=o.ref,
                  new_value={"items": len(items), "status": status})
        db.commit()
        return o
    except Exception:
        db.rollback()
        raise


def set_order_status(db: Session, *, user, order_id: int, status: str, device_id: str):
    allowed = {"draft", "sent", "ordered", "cancelled"}
    if status not in allowed:
        raise HTTPException(400, f"Cannot set order to {status}. Receiving is done via purchases.")
    o = db.get(PurchaseOrder, order_id)
    if not o:
        raise HTTPException(404, "Order not found.")
    if o.status in ("received",) and status == "cancelled":
        raise HTTPException(400, "A fully received order cannot be cancelled.")
    prev = o.status
    o.status = status
    audit.log(db, user=user, device_id=device_id, module="orders", action="update",
              entity="purchase_order", entity_id=o.id, entity_ref=o.ref,
              prev_value={"status": prev}, new_value={"status": status})
    db.commit()
    return o


def _update_order_receipts(db: Session, order_id: int):
    o = db.get(PurchaseOrder, order_id)
    if not o:
        return
    total_ord = sum(i.qty_ordered for i in o.items)
    total_rec = sum(i.qty_received for i in o.items)
    if total_rec >= total_ord and total_ord > 0:
        o.status = "received"
    elif total_rec > 0:
        o.status = "partially_received"


def receive_against_order(db: Session, *, user, device_id, order_id: int,
                          receipts: list[dict], cost_overrides: dict | None = None,
                          paid_amount: float = 0, account_id: int | None = None,
                          invoice_no: str = "") -> Purchase:
    """receipts: [{order_item_id, qty}] — partial or full; creates a real Purchase."""
    try:
        o = db.get(PurchaseOrder, order_id)
        if not o:
            raise HTTPException(404, "Order not found.")
        items = []
        for r in receipts:
            oi = next((i for i in o.items if i.id == r["order_item_id"]), None)
            if not oi:
                raise HTTPException(400, "Order item not found.")
            qty = float(r["qty"])
            if qty <= 0 or oi.qty_received + qty > oi.qty_ordered:
                remaining = oi.qty_ordered - oi.qty_received
                raise HTTPException(400,
                    f"Cannot receive {qty}; only {remaining} remaining on this order line.")
            cost = (cost_overrides or {}).get(str(oi.product_id), oi.expected_cost)
            items.append({"product_id": oi.product_id, "qty": qty, "cost_price": cost})
            oi.qty_received = oi.qty_received + qty
        if not items:
            raise HTTPException(400, "Nothing to receive.")
        pur = create_purchase.__wrapped__(db, user=user, device_id=device_id,
                                          supplier_id=o.supplier_id, supplier_name=None,
                                          items=items, invoice_no=invoice_no,
                                          paid_amount=paid_amount, account_id=account_id,
                                          order_id=order_id) if hasattr(create_purchase, "__wrapped__") \
            else create_purchase(db, user=user, device_id=device_id, supplier_id=o.supplier_id,
                                 supplier_name=None, items=items, invoice_no=invoice_no,
                                 paid_amount=paid_amount, account_id=account_id,
                                 order_id=order_id)
        return pur
    except Exception:
        db.rollback()
        raise
