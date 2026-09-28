"""POS / Sales service — ATOMIC: sale + items + payments + stock + ledger + audit + sync queue.

A sale can never partially complete (spec #48). All effects happen in one DB transaction;
on any error nothing is committed and the user gets an understandable message (spec #58).
"""
import json
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.parties import Customer, Account, Dasti
from app.models.transactions import Sale, SaleItem, SalePayment, CustomerPayment
from app.services import inventory, ledger, audit, notify, sync
from app.services.refs import next_ref
from app.services.settings_service import get_setting, get_bool, get_num


def _get_walkin(db: Session) -> Customer:
    c = db.query(Customer).filter(Customer.name == "Walk-in Customer").first()
    if not c:
        c = Customer(uuid=str(_uuid.uuid4()), name="Walk-in Customer", is_khata=False)
        db.add(c)
        db.flush()
    return c


def create_sale(db: Session, *, user, device_id: str, items: list[dict],
                customer_id: int | None = None, payments: list[dict] | None = None,
                credit_mode: str = "none", dasti_data: dict | None = None,
                extra_discount: float = 0, tax_override: float | None = None,
                notes: str = "", allow_negative: bool | None = None,
                approver=None) -> Sale:
    """credit_mode: none | khata | dasti. payments: [{account_id, amount}] (split supported)."""
    try:
        if not items:
            raise HTTPException(400, "Cart is empty — nothing to sell.")

        walkin = _get_walkin(db)
        customer = db.get(Customer, customer_id) if customer_id else walkin
        if customer is None:
            raise HTTPException(400, "Selected customer no longer exists.")

        # ---- validate lines & compute totals --------------------------------
        subtotal = discount_total = 0.0
        resolved = []
        max_disc_pct = user.role.max_discount_percent or 0
        need_approval = False
        approval_threshold = get_num(db, "approval.discount_percent", 0)
        neg_allowed = allow_negative if allow_negative is not None \
            else get_bool(db, "pos.allow_negative_stock")

        for line in items:
            p = db.get(Product, line["product_id"])
            if not p or not p.is_active:
                raise HTTPException(400, f"Product not found or inactive (id {line.get('product_id')}).")
            qty = float(line.get("qty", 0))
            if qty <= 0:
                raise HTTPException(400, f"Quantity must be positive for {p.name}.")
            unit = float(line.get("unit_price") if line.get("unit_price") is not None
                       else (p.retail_price or 0))
            disc = float(line.get("discount", 0))
            if disc < 0 or disc > round(qty * unit, 6):
                raise HTTPException(400, f"Invalid discount on {p.name}: Rs.{disc}")
            if unit != float(p.retail_price or 0) and not user.role_has_permission("price.change"):
                raise HTTPException(403, f"You may not change the selling price of {p.name}.")
            if disc > 0 and not user.role_has_permission("discount.apply"):
                raise HTTPException(403, "You do not have discount permission.")
            if qty * unit > 0 and disc / (qty * unit) * 100 > max_disc_pct > 0:
                raise HTTPException(400, f"Discount exceeds your maximum allowed {max_disc_pct}%.")
            if approval_threshold and disc / (qty * unit) * 100 >= approval_threshold:
                need_approval = True
            if not neg_allowed and p.stock_qty < qty:
                raise HTTPException(400,
                    f"Not enough stock for {p.name}: available {p.stock_qty}, needed {qty}. "
                    f"No stock or money was changed.")
            line_total = round(qty * unit - disc, 6)
            subtotal += qty * unit
            discount_total += disc
            resolved.append((p, qty, unit, disc, line_total, float(p.cost_price or 0)))

        if extra_discount:
            if not user.role_has_permission("discount.apply"):
                raise HTTPException(403, "You do not have discount permission.")
            discount_total += extra_discount

        tax_total = 0.0
        if tax_override is not None:
            tax_total = float(tax_override)
        elif get_bool(db, "tax.enabled"):
            tax_total = round((subtotal - discount_total) * get_num(db, "tax.percent") / 100.0, 6)
        grand = round(subtotal - discount_total + tax_total, 6)

        # ---- payments --------------------------------------------------------
        payments = payments or []
        paid_total = round(sum(float(p["amount"]) for p in payments), 6)
        if need_approval and approver is None:
            raise HTTPException(409, detail={
                "code": "APPROVAL_REQUIRED",
                "message": f"This discount requires approval (threshold {approval_threshold}%). "
                           f"Ask a manager/owner to approve."})

        if credit_mode == "khata":
            if not user.role_has_permission("khata.create"):
                raise HTTPException(403, "You cannot create Khata (credit) sales.")
            if customer.id == walkin.id:
                raise HTTPException(400, "Khata sale needs a saved customer, not walk-in.")
        if credit_mode == "dasti":
            if not user.role_has_permission("dasti.create"):
                raise HTTPException(403, "You cannot create Dasti.")
            if not get_bool(db, "payments.dasti"):
                raise HTTPException(400, "Dasti is disabled in settings.")

        remaining = round(grand - paid_total, 6)
        if remaining < -0.0001 and credit_mode == "none":
            raise HTTPException(400, f"Paid amount Rs.{paid_total} is less than total Rs.{grand}.")
        if remaining > 0.0001 and credit_mode == "none":
            raise HTTPException(400,
                f"Rs.{remaining} still unpaid. Choose Khata/Dasti credit or complete the payment.")
        if paid_total > grand + 0.0001 and len(payments) > 1:
            raise HTTPException(400, "Split payments cannot overpay; use cash tendered field instead.")

        # ---- persist atomically ---------------------------------------------
        sale = Sale(uuid=str(_uuid.uuid4()), ref=next_ref(db, "SALE"),
                    customer_id=customer.id, subtotal=round(subtotal, 6),
                    discount_total=round(discount_total, 6), tax_total=round(tax_total, 6),
                    grand_total=grand, paid_total=paid_total,
                    credit_amount=max(remaining, 0),
                    status="completed", user_id=user.id, device_id=device_id, notes=notes)
        db.add(sale)
        db.flush()

        change_given = 0.0
        for acc_pay in payments:
            acc = db.get(Account, acc_pay["account_id"])
            if not acc or not acc.is_active:
                raise HTTPException(400,
                    "The sale could not be completed because the payment account is unavailable. "
                    "No stock or money was changed.")
            amt = float(acc_pay["amount"])
            tendered = float(acc_pay.get("tendered", 0) or 0)
            if tendered > amt:                       # cash given by customer -> change out
                change_given += tendered - amt
                ledger.add_account_tx(db, acc.id, direction="out", amount=tendered - amt,
                                      reason="change", entity_type="sale", entity_id=sale.id,
                                      entity_ref=sale.ref, user=user, device_id=device_id)
            sp = SalePayment(uuid=str(_uuid.uuid4()), sale_id=sale.id, account_id=acc.id,
                             amount=amt, method=acc.type)
            db.add(sp)
            ledger.add_account_tx(db, acc.id, direction="in", amount=amt, reason="sale",
                                  entity_type="sale", entity_id=sale.id, entity_ref=sale.ref,
                                  user=user, device_id=device_id)

        for (p, qty, unit, disc, line_total, cost) in resolved:
            si = SaleItem(sale_id=sale.id, product_id=p.id, qty=qty, unit_price=unit,
                          cost_price=cost, discount=disc, line_total=line_total)
            db.add(si)
            inventory.move(db, p, qty_change=-qty, movement_type="sale", user=user,
                           device_id=device_id, entity_type="sale",
                           entity_id=sale.id, entity_ref=sale.ref)

        # credit side
        dasti = None
        if remaining > 0.0001:
            if credit_mode == "khata":
                ledger.add_customer_entry(db, customer.id, entry_type="credit_sale",
                                          debit=remaining, entity_type="sale",
                                          entity_id=sale.id, entity_ref=sale.ref, user=user)
                limit = float(customer.credit_limit or 0)
                if limit:
                    bal = ledger.customer_balance(db, customer.id)
                    if bal > limit:
                        db.rollback()
                        raise HTTPException(400,
                            f"{customer.name}'s credit limit is Rs.{limit}; new balance would be "
                            f"Rs.{bal:.0f}. Sale NOT recorded.")
            elif credit_mode == "dasti":
                due_days = get_num(db, "dasti.default_due_days", 1)
                dd = (dasti_data or {})
                dasti = Dasti(uuid=str(_uuid.uuid4()), ref=next_ref(db, "DST"),
                              customer_name=dd.get("customer_name") or customer.name,
                              phone=dd.get("phone") or customer.phone,
                              amount=remaining,
                              items_json=json.dumps([{"product": r[0].name, "qty": r[1]}
                                                     for r in resolved]),
                              due_date=datetime.now(timezone.utc).timestamp() and
                                       datetime.fromtimestamp(
                                           datetime.now(timezone.utc).timestamp() + due_days * 86400,
                                           timezone.utc),
                              created_by=user.id, status="pending",
                              notes=dd.get("notes", ""))
                db.add(dasti)
                db.flush()

        db.refresh(sale)
        audit.log(db, user=user, device_id=device_id, module="pos", action="create",
                  entity="sale", entity_id=sale.id, entity_ref=sale.ref,
                  new_value={"grand_total": grand, "paid": paid_total,
                             "credit": max(remaining, 0), "items": len(resolved),
                             **({"approved_by": approver.username} if approver else {})},
                  amount=grand, related_transaction=sale.ref)

        # notifications queued AFTER business success — never blocks the sale (spec #42)
        if get_bool(db, "whatsapp.enabled") and get_bool(db, "whatsapp.auto_sale_receipt") \
                and customer.phone and customer.whatsapp_enabled:
            notify.queue_whatsapp(db, to=customer.phone, template="sale_receipt",
                                  message=f"{get_setting(db,'store.name')} — Sale {sale.ref} "
                                          f"total Rs.{grand:.0f}. Thank you!")
        sync.enqueue(db, "sale", sale.uuid, {"ref": sale.ref, "grand_total": grand},
                     device_id=device_id)
        db.commit()
        sale._change_given = change_given
        return sale
    except Exception:
        db.rollback()
        raise


def void_sale(db: Session, *, user, sale_id: int, reason: str, device_id: str):
    """No hard delete — sale stays with void trace (spec #33). Reverses stock/ledger/accounts."""
    try:
        sale = db.get(Sale, sale_id)
        if not sale:
            raise HTTPException(404, "Sale not found.")
        if sale.status == "voided":
            raise HTTPException(400, "Sale is already voided.")
        if get_bool(db, "approval.void_sale") and not user.role_has_permission("sale.void"):
            raise HTTPException(403, "Voiding requires manager approval/permission.")
        for si in sale.items:
            p = db.get(Product, si.product_id)
            inventory.move(db, p, qty_change=si.qty, movement_type="correction", user=user,
                           device_id=device_id, reason=f"Void of {sale.ref}",
                           entity_type="sale", entity_id=sale.id, entity_ref=sale.ref)
        for sp in sale.payments:
            ledger.add_account_tx(db, sp.account_id, direction="out", amount=sp.amount,
                                  reason="sale_void", entity_type="sale", entity_id=sale.id,
                                  entity_ref=sale.ref, user=user, device_id=device_id)
        if sale.credit_amount and sale.customer_id:
            ledger.add_customer_entry(db, sale.customer_id, entry_type="adjustment",
                                      credit=sale.credit_amount, entity_type="sale",
                                      entity_id=sale.id, entity_ref=sale.ref,
                                      user=user, notes=f"Void of {sale.ref}")
        prev_status = sale.status
        sale.status = "voided"
        sale.void_reason = reason
        sale.voided_by = user.id
        sale.voided_at = datetime.now(timezone.utc)
        audit.log(db, user=user, device_id=device_id, module="pos", action="void",
                  entity="sale", entity_id=sale.id, entity_ref=sale.ref,
                  prev_value={"status": prev_status}, new_value={"status": "voided"},
                  reason=reason, amount=sale.grand_total, related_transaction=sale.ref)
        db.commit()
        return sale
    except Exception:
        db.rollback()
        raise


def hold_sale(db: Session, *, user, device_id: str, cart: list, customer_id=None, notes=""):
    sale = Sale(uuid=str(_uuid.uuid4()), ref=next_ref(db, "SALE"), status="held",
                customer_id=customer_id, user_id=user.id, device_id=device_id,
                notes=notes or json.dumps(cart))
    db.add(sale)
    audit.log(db, user=user, device_id=device_id, module="pos", action="hold",
              entity="sale", entity_id=sale.id, entity_ref=sale.ref)
    db.commit()
    return sale


def receive_customer_payment(db: Session, *, user, customer_id: int, amount: float,
                             account_id: int, device_id: str, notes: str = ""):
    """Khata payment: ledger + account + audit atomically."""
    try:
        if not user.role_has_permission("payment.receive"):
            raise HTTPException(403, "You cannot receive payments.")
        cust = db.get(Customer, customer_id)
        if not cust:
            raise HTTPException(404, "Customer not found.")
        acc = db.get(Account, account_id)
        if not acc or not acc.is_active:
            raise HTTPException(400, "Payment account unavailable. Nothing was changed.")
        if amount <= 0:
            raise HTTPException(400, "Payment amount must be positive.")
        ref = next_ref(db, "PAY")
        pay = CustomerPayment(uuid=str(_uuid.uuid4()), ref=ref, customer_id=cust.id,
                              amount=amount, account_id=acc.id, user_id=user.id,
                              device_id=device_id, notes=notes)
        db.add(pay)
        db.flush()
        ledger.add_customer_entry(db, cust.id, entry_type="payment", credit=amount,
                                  entity_type="customer_payment", entity_id=pay.id,
                                  entity_ref=ref, user=user, notes=notes)
        ledger.add_account_tx(db, acc.id, direction="in", amount=amount, reason="customer_payment",
                              entity_type="customer_payment", entity_id=pay.id, entity_ref=ref,
                              user=user, device_id=device_id)
        audit.log(db, user=user, device_id=device_id, module="khata", action="payment",
                  entity="customer_payment", entity_id=pay.id, entity_ref=ref,
                  amount=amount, related_transaction=ref,
                  new_value={"customer": cust.name, "paid": amount})
        sync.enqueue(db, "customer_payment", pay.uuid, {"ref": ref, "amount": amount},
                     device_id=device_id)
        db.commit()
        if get_bool(db, "whatsapp.enabled") and cust.whatsapp_enabled and cust.phone:
            notify.queue_whatsapp(db, to=cust.phone, template="payment_receipt",
                                  message=f"Received Rs.{amount:.0f}. New outstanding: "
                                          f"Rs.{ledger.customer_balance(db, cust.id):.0f} "
                                          f"— {get_setting(db,'store.name')}")
            db.commit()
        return pay
    except Exception:
        db.rollback()
        raise
