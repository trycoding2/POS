"""Ledger helpers: customer receivable, supplier payable, account cash position.

Balances are DERIVED from history (spec #49). Cached columns are updated transactionally
alongside the ledger entry so reports stay fast; derivation remains the source of truth.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.transactions import CustomerLedgerEntry, SupplierLedgerEntry
from app.models.parties import AccountTransaction
from app.models.parties import Customer, Supplier, Account


def customer_balance(db: Session, customer_id: int) -> float:
    """+ means customer owes us. opening + credit sales - payments - returns +/- adjustments."""
    c = db.get(Customer, customer_id)
    opening = float(c.opening_balance or 0) if c else 0.0
    debits = db.query(func.coalesce(func.sum(CustomerLedgerEntry.debit), 0)).filter(
        CustomerLedgerEntry.customer_id == customer_id).scalar()
    credits = db.query(func.coalesce(func.sum(CustomerLedgerEntry.credit), 0)).filter(
        CustomerLedgerEntry.customer_id == customer_id).scalar()
    return round(opening + float(debits) - float(credits), 6)


def supplier_balance(db: Session, supplier_id: int) -> float:
    """+ means we owe the supplier. Derived purely from history (spec #49):
    payable = Σ purchase dues (grand_total - paid_amount on received purchases)
              + Σ supplier-return reversals handled via ledger entries
              + opening balance. Ledger entries for payments are already netted
              inside each purchase record's due_amount, so we use purchase rows
              as the authoritative credit source and ledger debits for any
              standalone adjustments/returns."""
    from app.models.transactions import Purchase
    s = db.get(Supplier, supplier_id)
    opening = float(s.opening_balance or 0) if s else 0.0
    pur_due = db.query(func.coalesce(func.sum(Purchase.due_amount), 0)).filter(
        Purchase.supplier_id == supplier_id,
        Purchase.status.in_(["received", "partially_received"])).scalar()
    # extra ledger entries that are NOT purchase/purchase_payment (adjustments, returns)
    other_credit = db.query(func.coalesce(func.sum(SupplierLedgerEntry.credit), 0)).filter(
        SupplierLedgerEntry.supplier_id == supplier_id,
        SupplierLedgerEntry.entity_type.notin_(["purchase", "supplier_payment"])).scalar()
    other_debit = db.query(func.coalesce(func.sum(SupplierLedgerEntry.debit), 0)).filter(
        SupplierLedgerEntry.supplier_id == supplier_id,
        SupplierLedgerEntry.entity_type.notin_(["purchase", "supplier_payment"])).scalar()
    return round(opening + float(pur_due) + float(other_credit) - float(other_debit), 6)


def account_balance(db: Session, account_id: int) -> float:
    a = db.get(Account, account_id)
    opening = float(a.opening_balance or 0) if a else 0.0
    ins = db.query(func.coalesce(func.sum(AccountTransaction.amount), 0)).filter(
        AccountTransaction.account_id == account_id,
        AccountTransaction.direction == "in").scalar()
    outs = db.query(func.coalesce(func.sum(AccountTransaction.amount), 0)).filter(
        AccountTransaction.account_id == account_id,
        AccountTransaction.direction == "out").scalar()
    return round(opening + float(ins) - float(outs), 6)


def add_customer_entry(db: Session, customer_id, *, entry_type, debit=0, credit=0,
                       entity_type="", entity_id=None, entity_ref="", user=None, notes=""):
    e = CustomerLedgerEntry(uuid=__import__("uuid").uuid4().hex, customer_id=customer_id,
                            entry_type=entry_type, debit=debit, credit=credit,
                            entity_type=entity_type or None, entity_id=entity_id,
                            entity_ref=entity_ref or None,
                            user_id=getattr(user, "id", None), notes=notes or None)
    db.add(e)
    db.flush()
    return e


def add_supplier_entry(db: Session, supplier_id, *, entry_type, debit=0, credit=0,
                       entity_type="", entity_id=None, entity_ref="", user=None, notes=""):
    e = SupplierLedgerEntry(uuid=__import__("uuid").uuid4().hex, supplier_id=supplier_id,
                            entry_type=entry_type, debit=debit, credit=credit,
                            entity_type=entity_type or None, entity_id=entity_id,
                            entity_ref=entity_ref or None,
                            user_id=getattr(user, "id", None), notes=notes or None)
    db.add(e)
    db.flush()
    return e


def add_account_tx(db: Session, account_id, *, direction, amount, reason,
                   entity_type="", entity_id=None, entity_ref="", user=None,
                   device_id="", notes=""):
    t = AccountTransaction(uuid=__import__("uuid").uuid4().hex, account_id=account_id,
                           direction=direction, amount=amount, reason=reason,
                           entity_type=entity_type or None, entity_id=entity_id,
                           entity_ref=entity_ref or None,
                           user_id=getattr(user, "id", None), device_id=device_id,
                           notes=notes or None)
    db.add(t)
    db.flush()
    return t
