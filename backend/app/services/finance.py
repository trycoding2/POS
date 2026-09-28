"""Expenses, owner withdrawals, manual cash adjustments (spec #26-#28)."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.parties import Account
from app.models.transactions import Expense, OwnerWithdrawal, ExpenseCategory
from app.services import ledger, audit, sync
from app.services.refs import next_ref
from app.services.settings_service import get_num


def create_expense(db: Session, *, user, device_id: str, category_id: int, amount: float,
                   account_id: int, description: str = "", attachment_path: str = "",
                   occurred_at=None):
    try:
        if not user.role_has_permission("expense.create"):
            raise HTTPException(403, "You cannot record expenses.")
        cat = db.get(ExpenseCategory, category_id)
        acc = db.get(Account, account_id)
        if not cat:
            raise HTTPException(400, "Expense category not found — choose or create one.")
        if not acc or not acc.is_active:
            raise HTTPException(400, "Payment account unavailable. Nothing was changed.")
        if amount <= 0:
            raise HTTPException(400, "Expense amount must be positive.")
        threshold = get_num(db, "approval.expense_amount", 0)
        status = "approved"
        if threshold and amount > threshold and not user.role_has_permission("approval.grant"):
            status = "pending_approval"   # money NOT moved until approved
        exp = Expense(uuid=__import__("uuid").uuid4().hex, ref=next_ref(db, "EXP"),
                      category_id=cat.id, amount=amount, account_id=acc.id,
                      description=description, user_id=user.id, device_id=device_id,
                      attachment_path=attachment_path, status=status)
        if occurred_at is not None:
            exp.occurred_at = occurred_at
        db.add(exp)
        db.flush()
        if status == "approved":
            ledger.add_account_tx(db, acc.id, direction="out", amount=amount, reason="expense",
                                  entity_type="expense", entity_id=exp.id, entity_ref=exp.ref,
                                  user=user, device_id=device_id)
        audit.log(db, user=user, device_id=device_id, module="expenses", action="create",
                  entity="expense", entity_id=exp.id, entity_ref=exp.ref,
                  new_value={"amount": amount, "category": cat.name, "status": status},
                  amount=amount, related_transaction=exp.ref)
        sync.enqueue(db, "expense", exp.uuid, {"ref": exp.ref, "amount": amount},
                     device_id=device_id)
        db.commit()
        return exp
    except Exception:
        db.rollback()
        raise


def approve_expense(db: Session, *, user, expense_id: int, approve: bool, reason: str = "",
                    device_id: str = ""):
    try:
        if not user.role_has_permission("approval.grant"):
            raise HTTPException(403, "You cannot approve expenses.")
        exp = db.get(Expense, expense_id)
        if not exp or exp.status != "pending_approval":
            raise HTTPException(400, "Expense is not pending approval.")
        exp.status = "approved" if approve else "rejected"
        if approve:
            ledger.add_account_tx(db, exp.account_id, direction="out", amount=exp.amount,
                                  reason="expense", entity_type="expense", entity_id=exp.id,
                                  entity_ref=exp.ref, user=user, device_id=device_id)
        audit.log(db, user=user, device_id=device_id, module="expenses",
                  action="approve" if approve else "reject", entity="expense",
                  entity_id=exp.id, entity_ref=exp.ref, reason=reason, amount=exp.amount)
        db.commit()
        return exp
    except Exception:
        db.rollback()
        raise


def cancel_expense(db: Session, *, user, expense_id: int, reason: str, device_id: str = ""):
    """Cancellation + reversal — never a hard delete."""
    try:
        if not reason.strip():
            raise HTTPException(400, "Reason required to cancel an expense.")
        exp = db.get(Expense, expense_id)
        if not exp or exp.status == "cancelled":
            raise HTTPException(400, "Expense not found or already cancelled.")
        prev = exp.status
        if exp.status == "approved":
            ledger.add_account_tx(db, exp.account_id, direction="in", amount=exp.amount,
                                  reason="expense_cancel", entity_type="expense",
                                  entity_id=exp.id, entity_ref=exp.ref, user=user,
                                  device_id=device_id)
        exp.status = "cancelled"
        exp.cancelled_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        exp.cancel_reason = reason
        audit.log(db, user=user, device_id=device_id, module="expenses", action="cancel",
                  entity="expense", entity_id=exp.id, entity_ref=exp.ref,
                  prev_value={"status": prev}, new_value={"status": "cancelled"},
                  reason=reason, amount=exp.amount)
        db.commit()
        return exp
    except Exception:
        db.rollback()
        raise


def owner_withdrawal(db: Session, *, user, device_id: str, amount: float, account_id: int,
                     notes: str = ""):
    try:
        if not user.role_has_permission("withdrawal.create"):
            raise HTTPException(403, "Only owner-role users can record withdrawals.")
        acc = db.get(Account, account_id)
        if not acc or not acc.is_active:
            raise HTTPException(400, "Account unavailable. Nothing was changed.")
        if amount <= 0:
            raise HTTPException(400, "Amount must be positive.")
        w = OwnerWithdrawal(uuid=__import__("uuid").uuid4().hex, ref=next_ref(db, "WDR"),
                            amount=amount, account_id=acc.id, user_id=user.id,
                            device_id=device_id, notes=notes)
        db.add(w)
        db.flush()
        ledger.add_account_tx(db, acc.id, direction="out", amount=amount, reason="owner_withdrawal",
                              entity_type="withdrawal", entity_id=w.id, entity_ref=w.ref,
                              user=user, device_id=device_id)
        audit.log(db, user=user, device_id=device_id, module="cash", action="withdrawal",
                  entity="owner_withdrawal", entity_id=w.id, entity_ref=w.ref,
                  amount=amount, new_value={"account": acc.name})
        sync.enqueue(db, "owner_withdrawal", w.uuid, {"ref": w.ref, "amount": amount},
                     device_id=device_id)
        db.commit()
        return w
    except Exception:
        db.rollback()
        raise


def adjust_cash(db: Session, *, user, device_id: str, account_id: int, delta: float, reason: str):
    """Manual cash adjustment with mandatory reason + audit (spec #36)."""
    try:
        if not user.role_has_permission("cash.manage"):
            raise HTTPException(403, "You cannot adjust cash accounts.")
        if not reason.strip():
            raise HTTPException(400, "Cash adjustments require a reason.")
        acc = db.get(Account, account_id)
        if not acc:
            raise HTTPException(404, "Account not found.")
        if delta == 0:
            raise HTTPException(400, "No change requested.")
        bal = ledger.account_balance(db, acc.id)
        if bal + delta < 0:
            raise HTTPException(400,
                f"Adjustment would make {acc.name} negative (current Rs.{bal:.0f}). Not applied.")
        ledger.add_account_tx(db, acc.id, direction="in" if delta > 0 else "out",
                              amount=abs(delta), reason="manual_adjustment",
                              entity_type="account", entity_id=acc.id, entity_ref=acc.name,
                              user=user, device_id=device_id, notes=reason)
        audit.log(db, user=user, device_id=device_id, module="cash", action="adjustment",
                  entity="account", entity_id=acc.id, entity_ref=acc.name,
                  prev_value={"balance": bal}, new_value={"balance": bal + delta},
                  reason=reason, amount=abs(delta))
        db.commit()
        return ledger.account_balance(db, acc.id)
    except Exception:
        db.rollback()
        raise
