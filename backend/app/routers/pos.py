"""POS endpoints: sales, holds, voids, receipts, payments, returns."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.transactions import Sale
from app.services import sales as sales_svc, operations, receipts, audit, reports
from app.services.ledger import customer_balance

router = APIRouter(prefix="/api/pos", tags=["pos"])


class SaleItemIn(BaseModel):
    product_id: int
    qty: float
    unit_price: float | None = None
    discount: float = 0


class SalePayIn(BaseModel):
    account_id: int
    amount: float
    tendered: float | None = None      # cash given; change computed server-side


class SaleIn(BaseModel):
    items: list[SaleItemIn]
    customer_id: int | None = None
    payments: list[SalePayIn] = []
    credit_mode: str = "none"          # none | khata | dasti
    dasti: dict | None = None
    extra_discount: float = 0
    notes: str = ""


def sale_out(db: Session, s: Sale) -> dict:
    from app.models.auth import User
    from app.models.parties import Customer
    u = db.get(User, s.user_id)
    c = db.get(Customer, s.customer_id) if s.customer_id else None
    return {"id": s.id, "uuid": s.uuid, "ref": s.ref, "status": s.status,
            "subtotal": s.subtotal, "discount_total": s.discount_total,
            "tax_total": s.tax_total, "grand_total": s.grand_total,
            "paid_total": s.paid_total, "credit_amount": s.credit_amount,
            "customer": c.name if c else "Walk-in", "customer_id": s.customer_id,
            "cashier": (u.full_name or u.username) if u else None, "user_id": s.user_id,
            "device": s.device_id, "created_at": s.created_at.isoformat(),
            "void_reason": s.void_reason, "notes": s.notes,
            "items": [{"id": i.id, "product_id": i.product_id, "qty": i.qty,
                       "unit_price": i.unit_price, "discount": i.discount,
                       "line_total": i.line_total} for i in s.items],
            "payments": [{"account_id": p.account_id, "amount": p.amount,
                          "method": p.method} for p in s.payments]}


@router.post("/sales")
def create_sale(body: SaleIn, db: Session = Depends(get_db),
                user=Depends(require_permission("sale.create"))):
    s = sales_svc.create_sale(db, user=user, device_id=user._device_id,
                              items=[i.model_dump() for i in body.items],
                              customer_id=body.customer_id,
                              payments=[p.model_dump(exclude_none=True) for p in body.payments],
                              credit_mode=body.credit_mode, dasti_data=body.dasti,
                              extra_discount=body.extra_discount, notes=body.notes)
    out = sale_out(db, s)
    out["receipt"] = receipts.receipt_text(db, s)
    out["change_given"] = round(getattr(s, "_change_given", 0.0), 2)
    return out


@router.get("/sales")
def list_sales(limit: int = 50, offset: int = 0, status: str | None = None,
               q: str | None = None, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    stmt = db.query(Sale)
    if status:
        stmt = stmt.filter(Sale.status == status)
    if q:
        stmt = stmt.filter(Sale.ref.ilike(f"%{q}%"))
    rows = stmt.order_by(Sale.id.desc()).offset(offset).limit(min(limit, 200)).all()
    return [sale_out(db, s) for s in rows]


@router.get("/sales/{sid}")
def get_sale(sid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.get(Sale, sid)
    if not s:
        raise HTTPException(404, "Sale not found.")
    return sale_out(db, s)


@router.post("/sales/{sid}/void")
def void_sale(sid: int, body: dict, db: Session = Depends(get_db),
              user=Depends(require_permission("sale.void"))):
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "A reason is required to void a sale.")
    s = sales_svc.void_sale(db, user=user, sale_id=sid, reason=reason,
                            device_id=user._device_id)
    return sale_out(db, s)


class HoldIn(BaseModel):
    cart: list[dict] = []          # frontend cart snapshot [{name, qty, price}]
    customer_id: int | None = None
    notes: str = ""


@router.post("/hold")
def hold(body: HoldIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    import json as _json
    s = sales_svc.hold_sale(db, user=user, device_id=user._device_id,
                            cart=body.cart, customer_id=body.customer_id,
                            notes=body.notes or _json.dumps(body.cart))
    return {"id": s.id, "ref": s.ref}


@router.get("/held")
def held(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.query(Sale).filter(Sale.status == "held").order_by(Sale.id.desc()).all()
    return [{"id": s.id, "ref": s.ref, "at": s.created_at.isoformat(), "cart": s.notes}
            for s in rows]


@router.post("/sales/{sid}/return")
def return_sale(sid: int, body: dict, db: Session = Depends(get_db),
                user=Depends(require_permission("sale.return"))):
    ret = operations.customer_return(db, user=user, device_id=user._device_id, sale_id=sid,
                                     items=body.get("items", []), reason=body.get("reason", ""),
                                     refund_method=body.get("refund_method", "cash"),
                                     account_id=body.get("account_id"),
                                     stock_condition=body.get("stock_condition", "good"))
    return {"ref": ret.ref, "total": ret.total_amount, "restock": ret.restock}


@router.get("/sales/{sid}/receipt.txt")
def receipt_txt(sid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.get(Sale, sid)
    if not s:
        raise HTTPException(404, "Sale not found.")
    txt = receipts.receipt_text(db, s)
    if getattr(s, "_change_given", 0):
        txt += f"\nChange given: {receipts.fmt_money(db, s._change_given)}\n"
    return Response(txt, media_type="text/plain")


@router.get("/sales/{sid}/receipt.pdf")
def receipt_pdf(sid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.get(Sale, sid)
    if not s:
        raise HTTPException(404, "Sale not found.")
    return Response(receipts.receipt_pdf_bytes(db, s), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{s.ref}.pdf"'})


class CustPayIn(BaseModel):
    customer_id: int
    amount: float
    account_id: int
    notes: str = ""


@router.post("/customer-payments")
def receive_customer_payment(body: CustPayIn, db: Session = Depends(get_db),
                             user=Depends(require_permission("payment.receive"))):
    pay = sales_svc.receive_customer_payment(db, user=user, customer_id=body.customer_id,
                                             amount=body.amount, account_id=body.account_id,
                                             device_id=user._device_id, notes=body.notes)
    bal = reports and __import__("app.services.ledger", fromlist=["x"]).customer_balance(
        db, body.customer_id)
    return {"ref": pay.ref, "new_balance": bal}
