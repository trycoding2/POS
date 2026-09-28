"""Karyana Manager — FastAPI application entry point.

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000   (from backend/)
Desktop: Tauri spawns this binary; frontend talks to /api/* on localhost.
"""
import csv
import io
import json
import os
import sys
import threading
import uuid as _uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi import UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db, init_db
from app.core.security import get_current_user, require_permission
from app.routers import auth, catalog, pos
from app.routers.pos import SaleIn
from app.services import setup as setup_svc


def _background_loop(stop: threading.Event):
    """Lightweight scheduler: WhatsApp queue processing + automatic local backups.
    No Redis/Celery needed for a single shop; can be swapped later."""
    from app.services import notify, backup
    s = get_settings()
    while not stop.wait(30):
        db = SessionLocal()
        try:
            notify.process_pending(db)
        except Exception:
            db.rollback()
        finally:
            db.close()
        # hourly auto-backup if enabled
        db = SessionLocal()
        try:
            from app.services.settings_service import get_bool, get_setting
            if get_bool(db, "backup.auto_local"):
                last = get_setting(db, "backup.last_auto_at", "")
                now = datetime.now(timezone.utc)
                if not last or (now - datetime.fromisoformat(last)).total_seconds() > 3600:
                    rec = backup.create_backup(db, kind="local")
                    from app.services.settings_service import set_setting
                    set_setting(db, "backup.last_auto_at", now.isoformat())
                    del rec
        except Exception:
            db.rollback()
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        setup_svc.seed_static(db)      # idempotent: roles/perms/units/accounts even pre-setup
    finally:
        db.close()
    stop = threading.Event()
    t = threading.Thread(target=_background_loop, args=(stop,), daemon=True)
    t.start()
    yield
    stop.set()


s = get_settings()
app = FastAPI(title=s.app_name, version=s.version, lifespan=lifespan)

# CORS: only the local desktop/web frontends (Tauri dev server, built app).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:1420", "http://tauri.localhost", "tauri://localhost"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in (auth.router, catalog.router, pos.router):
    app.include_router(r)


@app.exception_handler(HTTPException)
async def friendly_errors(request: Request, exc: HTTPException):
    """Spec #58: never leave the user wondering whether the transaction succeeded."""
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail,
                                 "committed": exc.status_code < 400 or exc.status_code == 409})


@app.get("/api/system/info")
def system_info(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services import sync
    return {"app": s.app_name, "version": s.version, "device_id": s.device_id,
            "offline_ready": True, "sync_pending": sync.pending_count(db),
            "cloud_configured": bool(s.cloud_url and s.cloud_api_key),
            "whatsapp_configured": bool(s.whatsapp_api_url and s.whatsapp_api_token)}


@app.post("/api/system/process-notifications")
def process_notifications(db: Session = Depends(get_db),
                          user=Depends(require_permission("notification.send"))):
    from app.services import notify
    return notify.process_pending(db)


@app.get("/api/sync/status")
def sync_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.system import SyncQueue
    rows = db.query(SyncQueue).order_by(SyncQueue.id.desc()).limit(200).all()
    return {
        "pending": sum(1 for r in rows if r.status in ("pending", "retry")),
        "failed": sum(1 for r in rows if r.status == "failed"),
        "conflicts": sum(1 for r in rows if r.status in ("conflict", "attention")),
        "cloud_configured": bool(s.cloud_url and s.cloud_api_key),
        "recent": [{"id": r.id, "entity_type": r.entity_type, "status": r.status,
                    "retries": r.retry_count, "error": r.error,
                    "created_at": r.created_at.isoformat() if r.created_at else None}
                   for r in rows],
    }


@app.post("/api/sync/run")
def sync_run(db: Session = Depends(get_db), user=Depends(require_permission("settings.edit"))):
    from app.services import sync
    res = sync.run_sync(db)
    db.commit()
    return res


@app.get("/api/devices")
def list_devices(db: Session = Depends(get_db), user=Depends(require_permission("users.manage"))):
    from app.models.auth import Device, User
    out = []
    for d in db.query(Device).all():
        u = db.get(User, d.user_id) if d.user_id else None
        out.append({"id": d.id, "device_id": d.device_id, "name": d.name,
                    "user": (u.username if u else None), "authorized": d.authorized,
                    "last_sync_at": d.last_sync_at.isoformat() if d.last_sync_at else None,
                    "last_activity_at": d.last_activity_at.isoformat() if d.last_activity_at else None})
    return out


@app.post("/api/devices/{dev_id}/revoke")
def revoke_device(dev_id: int, db: Session = Depends(get_db),
                  user=Depends(require_permission("users.manage"))):
    from app.models.auth import Device
    from app.services import audit
    d = db.get(Device, dev_id)
    if not d:
        raise HTTPException(404, "Device not found.")
    prev = d.authorized
    d.authorized = False
    # sessions stay but are blocked at auth time with a clear 403 "device revoked" message
    audit.log(db, user=user, module="security", action="update", entity="device",
              entity_id=d.id, entity_ref=d.device_id,
              prev_value={"authorized": prev}, new_value={"authorized": False},
              reason="Device revoked by owner")
    db.commit()
    return {"ok": True, "device_id": d.device_id}


@app.post("/api/devices/{dev_id}/restore")
def restore_device(dev_id: int, db: Session = Depends(get_db),
                   user=Depends(require_permission("users.manage"))):
    from app.models.auth import Device
    from app.services import audit
    d = db.get(Device, dev_id)
    if not d:
        raise HTTPException(404, "Device not found.")
    d.authorized = True
    audit.log(db, user=user, module="security", action="update", entity="device",
              entity_id=d.id, entity_ref=d.device_id, new_value={"authorized": True},
              reason="Device re-authorized")
    db.commit()
    return {"ok": True}


@app.get("/api/activity")
def activity_feed(limit: int = Query(60, le=300), user_id: int | None = None,
                  module: str | None = None, action: str | None = None,
                  device_id: str | None = None, q: str | None = None,
                  date_from: str | None = None, date_to: str | None = None,
                  db: Session = Depends(get_db),
                  user=Depends(require_permission("audit.view"))):
    """Live activity monitor + global audit search (spec #31/#54)."""
    from app.models.system import AuditLog
    stmt = db.query(AuditLog)
    if user_id:
        stmt = stmt.filter(AuditLog.user_id == user_id)
    if module:
        stmt = stmt.filter(AuditLog.module == module)
    if action:
        stmt = stmt.filter(AuditLog.action == action)
    if device_id:
        stmt = stmt.filter(AuditLog.device_id == device_id)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.filter(or_(AuditLog.username.ilike(like),
                               AuditLog.entity_ref.ilike(like),
                               AuditLog.related_transaction.ilike(like)))
    if date_from:
        stmt = stmt.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from))
    if date_to:
        stmt = stmt.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to))
    rows = stmt.order_by(AuditLog.id.desc()).limit(limit).all()
    return [{
        "id": a.id, "at": a.timestamp.isoformat() if a.timestamp else None,
        "user": a.username, "role": a.role, "device": a.device_id,
        "module": a.module, "action": a.action, "entity": a.entity,
        "entity_ref": a.entity_ref, "prev": a.prev_value, "new": a.new_value,
        "reason": a.reason, "related": a.related_transaction, "amount": a.amount,
    } for a in rows]


@app.get("/api/audit/verify")
def audit_verify(db: Session = Depends(get_db),
                 user=Depends(require_permission("audit.view"))):
    from app.services import audit
    ok, bad = audit.verify_chain(db)
    return {"ok": ok, "chain_ok": ok, "first_bad_row": bad}


# ---------------------------------------------------------------- settings ---
@app.get("/api/settings")
def settings_get(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services.settings_service import all_settings
    return all_settings(db)


@app.put("/api/settings")
def settings_put(body: dict, db: Session = Depends(get_db),
                 user=Depends(require_permission("settings.edit"))):
    """Every setting here actually drives behavior (spec #71) — validated keys only."""
    from app.services.settings_service import set_setting, DEFAULTS, get_setting
    from app.services import audit
    changed = {}
    for k, v in body.items():
        if k.startswith("ref.seq."):
            raise HTTPException(400, "Sequence counters cannot be edited.")
        old = get_setting(db, k, DEFAULTS.get(k, ""))
        set_setting(db, k, str(v), user.id)
        changed[k] = {"old": old, "new": str(v)}
    audit.log(db, user=user, module="settings", action="update", entity="settings",
              new_value=changed, reason="Settings changed via control center")
    db.commit()
    return {"ok": True, "changed": list(changed.keys())}


# ------------------------------------------------------------- parties -----
def _cust_out(c, bal=None):
    d = {"id": c.id, "uuid": c.uuid, "name": c.name, "phone": c.phone,
         "alt_phone": c.alt_phone, "address": c.address, "notes": c.notes,
         "credit_limit": c.credit_limit, "opening_balance": c.opening_balance,
         "is_khata": c.is_khata, "whatsapp_enabled": c.whatsapp_enabled,
         "is_active": c.is_active,
         "created_at": c.created_at.isoformat() if c.created_at else None}
    if bal is not None:
        d["balance"] = round(bal, 2)
    return d


@app.get("/api/customers")
def customers_list(q: str = "", filter: str = "all", limit: int = 100, offset: int = 0,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.parties import Customer
    from app.services.ledger import customer_balance
    stmt = db.query(Customer).filter(Customer.name != "Walk-in Customer")
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    rows = stmt.order_by(Customer.name).offset(offset).limit(min(limit, 500)).all()
    show_bal = user.role_has_permission("customer.balance.view")
    out = []
    for c in rows:
        bal = customer_balance(db, c.id) if show_bal else None
        out.append(_cust_out(c, bal))
    if filter == "khata":
        out = [c for c in out if c["is_khata"]]
    elif filter == "outstanding" and show_bal:
        out = [c for c in out if (c["balance"] or 0) > 0.004]
    elif filter == "inactive":
        out = [c for c in out if not c["is_active"]]
    return out


class CustomerIn(BaseModel):
    name: str
    phone: str = ""
    alt_phone: str = ""
    address: str = ""
    notes: str = ""
    credit_limit: float = 0
    opening_balance: float = 0
    is_khata: bool = True
    whatsapp_enabled: bool = False


@app.post("/api/customers")
def customer_create(body: CustomerIn, db: Session = Depends(get_db),
                    user=Depends(require_permission("customer.create"))):
    from app.models.parties import Customer
    from app.services import audit, ledger
    if not body.name.strip():
        raise HTTPException(400, "Customer name is required.")
    c = Customer(uuid=str(_uuid.uuid4()), **body.model_dump(exclude={"opening_balance"}),
                 created_by=user.id)
    db.add(c)
    db.flush()
    if body.opening_balance:
        ledger.add_customer_entry(db, c.id, entry_type="opening",
                                  debit=body.opening_balance, entity_type="customer",
                                  entity_id=c.id, user=user, notes="Opening balance")
    audit.log(db, user=user, module="customers", action="create", entity="customer",
              entity_id=c.id, entity_ref=c.name, new_value=body.model_dump())
    db.commit()
    return _cust_out(c, body.opening_balance)


@app.put("/api/customers/{cid}")
def customer_update(cid: int, body: dict, db: Session = Depends(get_db),
                    user=Depends(require_permission("customer.create"))):
    from app.models.parties import Customer
    from app.services import audit
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "Customer not found.")
    allowed = {"name", "phone", "alt_phone", "address", "notes", "credit_limit",
               "is_khata", "whatsapp_enabled", "is_active"}
    prev, new = {}, {}
    for k, v in body.items():
        if k in allowed and getattr(c, k) != v:
            prev[k] = getattr(c, k)
            setattr(c, k, v)
            new[k] = v
    if new:
        audit.log(db, user=user, module="customers", action="update", entity="customer",
                  entity_id=c.id, entity_ref=c.name, prev_value=prev, new_value=new)
    db.commit()
    from app.services.ledger import customer_balance
    return _cust_out(c, customer_balance(db, c.id))


@app.get("/api/customers/{cid}")
def customer_detail(cid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.parties import Customer
    from app.services.ledger import customer_balance
    from app.services import reports
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "Customer not found.")
    out = _cust_out(c, customer_balance(db, c.id))
    show_fin = user.role_has_permission("customer.balance.view")
    if show_fin:
        from app.models.transactions import Sale, CustomerPayment
        from sqlalchemy import func
        out["total_purchases"] = float(db.query(func.coalesce(func.sum(Sale.grand_total), 0))
                                       .filter(Sale.customer_id == cid,
                                               Sale.status.notin_(["voided"])).scalar() or 0)
        out["total_payments"] = float(db.query(func.coalesce(func.sum(CustomerPayment.amount), 0))
                                      .filter(CustomerPayment.customer_id == cid).scalar() or 0)
        out["timeline"] = reports.customer_timeline(db, cid)
    return out


def _sup_out(sp, bal=None):
    d = {"id": sp.id, "uuid": sp.uuid, "name": sp.name, "company": sp.company,
         "phone": sp.phone, "address": sp.address, "contact_person": sp.contact_person,
         "payment_terms": sp.payment_terms, "notes": sp.notes,
         "opening_balance": sp.opening_balance, "is_temporary": sp.is_temporary,
         "is_active": sp.is_active}
    if bal is not None:
        d["payable"] = round(bal, 2)
    return d


@app.get("/api/suppliers")
def suppliers_list(q: str = "", filter: str = "all", db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    from app.models.parties import Supplier
    from app.services.ledger import supplier_balance
    stmt = db.query(Supplier)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.filter(or_(Supplier.name.ilike(like), Supplier.company.ilike(like),
                               Supplier.phone.ilike(like)))
    rows = stmt.order_by(Supplier.name).all()
    show_bal = user.role_has_permission("supplier.balance.view")
    out = [_sup_out(sp, supplier_balance(db, sp.id) if show_bal else None) for sp in rows]
    if filter == "outstanding" and show_bal:
        out = [x for x in out if (x["payable"] or 0) > 0.004]
    elif filter == "temporary":
        out = [x for x in out if x["is_temporary"]]
    elif filter == "inactive":
        out = [x for x in out if not x["is_active"]]
    return out


@app.post("/api/suppliers")
def supplier_create(body: dict, db: Session = Depends(get_db),
                    user=Depends(require_permission("supplier.create"))):
    from app.models.parties import Supplier
    from app.services import audit, ledger
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Supplier name is required.")
    sp = Supplier(uuid=str(_uuid.uuid4()), name=name, company=body.get("company", ""),
                  phone=body.get("phone", ""), address=body.get("address", ""),
                  contact_person=body.get("contact_person", ""),
                  payment_terms=body.get("payment_terms", ""), notes=body.get("notes", ""),
                  opening_balance=float(body.get("opening_balance") or 0), created_by=user.id)
    db.add(sp)
    db.flush()
    if sp.opening_balance:
        ledger.add_supplier_entry(db, sp.id, entry_type="opening", debit=0,
                                  credit=sp.opening_balance, entity_type="supplier",
                                  entity_id=sp.id, user=user, notes="Opening payable")
    audit.log(db, user=user, module="suppliers", action="create", entity="supplier",
              entity_id=sp.id, entity_ref=sp.name, new_value={"name": name})
    db.commit()
    from app.services.ledger import supplier_balance
    return _sup_out(sp, supplier_balance(db, sp.id))


@app.put("/api/suppliers/{sid}")
def supplier_update(sid: int, body: dict, db: Session = Depends(get_db),
                    user=Depends(require_permission("supplier.create"))):
    from app.models.parties import Supplier
    from app.services import audit
    sp = db.get(Supplier, sid)
    if not sp:
        raise HTTPException(404, "Supplier not found.")
    allowed = {"name", "company", "phone", "address", "contact_person", "payment_terms",
               "notes", "is_temporary", "is_active"}
    prev, new = {}, {}
    for k, v in body.items():
        if k in allowed and getattr(sp, k) != v:
            prev[k] = getattr(sp, k)
            setattr(sp, k, v)
            new[k] = v
    if new:
        audit.log(db, user=user, module="suppliers", action="update", entity="supplier",
                  entity_id=sp.id, entity_ref=sp.name, prev_value=prev, new_value=new)
    db.commit()
    from app.services.ledger import supplier_balance
    return _sup_out(sp, supplier_balance(db, sp.id))


@app.get("/api/suppliers/{sid}")
def supplier_detail(sid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.parties import Supplier
    from app.services.ledger import supplier_balance
    from app.services import reports
    sp = db.get(Supplier, sid)
    if not sp:
        raise HTTPException(404, "Supplier not found.")
    out = _sup_out(sp, supplier_balance(db, sp.id))
    if user.role_has_permission("supplier.balance.view"):
        out["timeline"] = reports.supplier_timeline(db, sid)
    return out


@app.post("/api/suppliers/{sid}/convert-from-temporary")
def convert_temporary(sid: int, body: dict, db: Session = Depends(get_db),
                      user=Depends(require_permission("supplier.create"))):
    """Spec #19: turn a random/local seller record into a saved supplier."""
    from app.models.parties import Supplier
    from app.services import audit
    sp = db.get(Supplier, sid)
    if not sp or not sp.is_temporary:
        raise HTTPException(400, "Not a temporary supplier record.")
    sp.is_temporary = False
    sp.name = body.get("name", sp.name)
    sp.phone = body.get("phone", sp.phone)
    sp.company = body.get("company", sp.company)
    audit.log(db, user=user, module="suppliers", action="update", entity="supplier",
              entity_id=sp.id, entity_ref=sp.name,
              new_value={"is_temporary": False}, reason="Converted from temporary seller")
    db.commit()
    return _sup_out(sp)


# ------------------------------------------------------------- accounts ----
@app.get("/api/accounts")
def accounts_list(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.parties import Account
    from app.services.ledger import account_balance
    out = []
    for a in db.query(Account).order_by(Account.name).all():
        d = {"id": a.id, "name": a.name, "type": a.type, "is_active": a.is_active,
             "is_default_sale": a.is_default_sale}
        if user.role_has_permission("cash.manage") or user.role_has_permission("profit.view"):
            d["balance"] = round(account_balance(db, a.id), 2)
        out.append(d)
    return out


class AccountIn(BaseModel):
    name: str
    type: str = "cash"          # cash/bank/wallet
    opening_balance: float = 0
    is_default_sale: bool = False


@app.post("/api/accounts")
def account_create(body: AccountIn, db: Session = Depends(get_db),
                   user=Depends(require_permission("cash.manage"))):
    from app.models.parties import Account
    from app.services import audit, ledger
    if not body.name.strip():
        raise HTTPException(400, "Account name required.")
    if db.query(Account).filter(Account.name == body.name.strip()).first():
        raise HTTPException(400, "An account with that name already exists.")
    a = Account(uuid=str(_uuid.uuid4()), name=body.name.strip(), type=body.type,
                is_default_sale=body.is_default_sale)
    db.add(a)
    db.flush()
    if body.opening_balance:
        ledger.add_account_tx(db, a.id, direction="in", amount=body.opening_balance,
                              reason="opening_balance", entity_type="account",
                              entity_id=a.id, entity_ref=a.name, user=user)
    audit.log(db, user=user, module="accounts", action="create", entity="account",
              entity_id=a.id, entity_ref=a.name, new_value=body.model_dump())
    db.commit()
    return {"id": a.id, "name": a.name, "type": a.type}


@app.put("/api/accounts/{aid}")
def account_update(aid: int, body: dict, db: Session = Depends(get_db),
                   user=Depends(require_permission("cash.manage"))):
    from app.models.parties import Account
    from app.services import audit
    a = db.get(Account, aid)
    if not a:
        raise HTTPException(404, "Account not found.")
    prev, new = {}, {}
    for k in ("name", "type", "is_active", "is_default_sale"):
        if k in body and getattr(a, k) != body[k]:
            prev[k] = getattr(a, k)
            setattr(a, k, body[k])
            new[k] = body[k]
    if new:
        audit.log(db, user=user, module="accounts", action="update", entity="account",
                  entity_id=a.id, entity_ref=a.name, prev_value=prev, new_value=new)
    db.commit()
    return {"ok": True}


@app.get("/api/accounts/{aid}/transactions")
def account_transactions(aid: int, limit: int = 200, db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    from app.models.parties import AccountTransaction
    rows = db.query(AccountTransaction).filter(
        AccountTransaction.account_id == aid).order_by(
        AccountTransaction.id.desc()).limit(min(limit, 500)).all()
    return [{"id": t.id, "direction": t.direction, "amount": t.amount, "reason": t.reason,
             "ref": t.entity_ref, "at": t.occurred_at.isoformat() if t.occurred_at else None,
             "user_id": t.user_id, "device": t.device_id, "notes": t.notes} for t in rows]


@app.post("/api/accounts/{aid}/adjust")
def account_adjust(aid: int, body: dict, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    from app.services import finance
    res = finance.adjust_cash(db, user=user, device_id=user._device_id, account_id=aid,
                              delta=float(body.get("delta", 0)),
                              reason=body.get("reason", ""))
    return {"ok": True, "ref": res.ref if hasattr(res, "ref") else None}


# --------------------------------------------------------------- khata -----
@app.get("/api/khata/dashboard")
def khata_dashboard(db: Session = Depends(get_db),
                    user=Depends(require_permission("customer.balance.view"))):
    from app.services import reports
    return reports.receivables(db)


@app.post("/api/khata/reminders/{cid}")
def khata_reminder(cid: int, db: Session = Depends(get_db),
                   user=Depends(require_permission("notification.send"))):
    from app.models.parties import Customer
    from app.services import notify, audit, ledger
    from app.services.settings_service import get_bool, get_setting
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "Customer not found.")
    if not c.phone:
        raise HTTPException(400, "This customer has no phone number saved.")
    bal = ledger.customer_balance(db, cid)
    n = notify.queue_whatsapp(db, to=c.phone, template="khata_reminder",
                              message=f"Dear {c.name}, your outstanding balance at "
                                      f"{get_setting(db, 'store.name')} is Rs.{bal:.0f}. Kindly clear it. Thank you.",
                              entity_type="customer", entity_ref=c.name, user=user,
                              customer_name=c.name)
    audit.log(db, user=user, module="notifications", action="queue", entity="notification",
              entity_id=n.id, entity_ref=c.name, new_value={"template": "khata_reminder"})
    db.commit()
    sent_now = notify.process_pending(db)
    db.commit()
    return {"queued": True, "status": n.status, "error": n.error,
            "whatsapp_enabled_globally": get_bool(db, "whatsapp.enabled")}


# --------------------------------------------------------------- dasti -----
@app.get("/api/dastis")
def dasti_list(status: str = "", q: str = "", db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    from app.models.parties import Dasti
    stmt = db.query(Dasti)
    if status:
        stmt = stmt.filter(Dasti.status == status)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.filter(or_(Dasti.ref.ilike(like), Dasti.customer_name.ilike(like),
                               Dasti.phone.ilike(like)))
    now = datetime.now(timezone.utc)
    out = []
    for d in stmt.order_by(Dasti.id.desc()).limit(200).all():
        due = d.due_date
        if due and due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        overdue = bool(due and d.status in ("pending", "partial") and due < now)
        out.append({"id": d.id, "ref": d.ref, "customer_name": d.customer_name,
                    "phone": d.phone, "amount": d.amount, "paid_amount": d.paid_amount or 0,
                    "outstanding": round((d.amount or 0) - (d.paid_amount or 0), 2),
                    "overdue": overdue, "status": d.status,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "due_date": due.isoformat() if due else None,
                    "items": json.loads(d.items_json) if d.items_json else [],
                    "notes": d.notes, "created_by": d.created_by})
    return out


class DastiCreateIn(BaseModel):
    customer_name: str = ""
    phone: str = ""
    items: list[dict] = []          # [{product_id, qty}] or [{name, qty, price}]
    amount: float | None = None     # override total; else derived from items
    due_days: int | None = None
    notes: str = ""


@app.post("/api/dastis")
def dasti_create(body: DastiCreateIn, db: Session = Depends(get_db),
                 user=Depends(require_permission("dasti.create"))):
    """Standalone Dasti (temporary credit) without a POS sale (spec #15).
    If items reference products, stock is decremented with full movement records."""
    import uuid as _uu
    from datetime import timedelta
    from app.models.parties import Dasti
    from app.models.catalog import Product
    from app.services import audit, inventory, sync
    from app.services.refs import next_ref
    from app.services.settings_service import get_num
    items_out = []
    derived = 0.0
    for it in body.items:
        pid = it.get("product_id")
        qty = float(it.get("qty", 1) or 1)
        if pid:
            p = db.get(Product, int(pid))
            if not p:
                raise HTTPException(400, f"Product id {pid} not found.")
            price = float(it.get("price") or p.retail_price or 0)
            if (p.stock_qty or 0) < qty:
                raise HTTPException(400,
                    f"Not enough stock for {p.name} (have {p.stock_qty}, need {qty}). "
                    f"Dasti NOT created.")
            inventory.move(db, p, qty_change=-qty, movement_type="sale", user=user,
                           device_id=user._device_id, reason="Dasti (temporary credit)")
            items_out.append({"product": p.name, "product_id": p.id, "qty": qty,
                              "price": price})
            derived += qty * price
        else:
            name = (it.get("name") or "").strip()
            price = float(it.get("price", 0) or 0)
            if not name:
                raise HTTPException(400, "Each item needs a product_id or a name.")
            items_out.append({"product": name, "qty": qty, "price": price})
            derived += qty * price
    amount = round(float(body.amount) if body.amount is not None else derived, 2)
    if amount <= 0:
        raise HTTPException(400, "Dasti amount must be greater than zero.")
    dd = int(body.due_days if body.due_days is not None
             else get_num(db, "dasti.default_due_days", 1))
    d = Dasti(uuid=str(_uu.uuid4()), ref=next_ref(db, "DST"),
              customer_name=body.customer_name.strip(), phone=body.phone.strip(),
              amount=amount, paid_amount=0,
              items_json=json.dumps(items_out),
              due_date=datetime.now(timezone.utc) + timedelta(days=max(dd, 0)),
              created_by=user.id, status="pending", notes=body.notes)
    db.add(d)
    db.flush()
    audit.log(db, user=user, module="dasti", action="create", entity="dasti",
              entity_id=d.id, entity_ref=d.ref, amount=amount,
              new_value={"items": len(items_out), "due_days": dd})
    sync.enqueue(db, "dasti", d.uuid, {"ref": d.ref, "amount": amount},
                 device_id=user._device_id)
    db.commit()
    return {"id": d.id, "ref": d.ref, "amount": d.amount, "status": d.status,
            "due_date": d.due_date.isoformat()}


class DastiPayIn(BaseModel):
    amount: float
    account_id: int
    notes: str = ""


@app.post("/api/dastis/{did}/pay")
def dasti_pay(did: int, body: DastiPayIn, db: Session = Depends(get_db),
              user=Depends(require_permission("payment.receive"))):
    from app.services import operations
    p = operations.pay_dasti(db, user=user, device_id=user._device_id, dasti_id=did,
                             amount=body.amount, account_id=body.account_id, notes=body.notes)
    return {"ref": p.ref, "amount": p.amount}


@app.post("/api/dastis/{did}/extend")
def dasti_extend(did: int, body: dict, db: Session = Depends(get_db),
                 user=Depends(require_permission("dasti.create"))):
    from app.services import operations
    d = operations.extend_dasti(db, user=user, device_id=user._device_id, dasti_id=did,
                                days=int(body.get("days", 1)),
                                reason=body.get("reason", "Due date extension"))
    return {"ref": d.ref, "new_due": d.due_date.isoformat()}


@app.post("/api/dastis/{did}/cancel")
def dasti_cancel(did: int, body: dict, db: Session = Depends(get_db),
                 user=Depends(require_permission("dasti.create"))):
    from app.services import operations
    d = operations.cancel_dasti(db, user=user, device_id=user._device_id, dasti_id=did,
                               reason=body.get("reason", ""))
    return {"ref": d.ref, "status": d.status}


# ------------------------------------------------------------ purchases ----
class PurchaseItemIn(BaseModel):
    product_id: int
    qty: float
    cost_price: float
    discount: float = 0
    qty_free: float = 0
    batch_no: str = ""
    expiry_date: str | None = None


class PurchaseIn(BaseModel):
    supplier_id: int | None = None
    supplier_name: str | None = None       # random/temporary seller (spec #19)
    items: list[PurchaseItemIn]
    invoice_no: str = ""
    paid_amount: float = 0
    account_id: int | None = None
    discount_total: float = 0
    notes: str = ""
    order_id: int | None = None


def _pur_out(p):
    return {"id": p.id, "uuid": p.uuid, "ref": p.ref, "supplier_id": p.supplier_id,
            "invoice_no": p.invoice_no, "subtotal": p.subtotal,
            "discount_total": p.discount_total, "grand_total": p.grand_total,
            "paid_amount": p.paid_amount, "due_amount": p.due_amount, "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "notes": p.notes,
            "items": [{"id": i.id, "product_id": i.product_id, "qty_received": i.qty_received,
                       "qty_ordered": i.qty_ordered, "qty_free": i.qty_free,
                       "cost_price": i.cost_price, "discount": i.discount,
                       "line_total": i.line_total, "batch_no": i.batch_no} for i in p.items]}


@app.post("/api/purchases")
def purchase_create(body: PurchaseIn, db: Session = Depends(get_db),
                    user=Depends(require_permission("purchase.create"))):
    from app.services import purchases
    p = purchases.create_purchase(db, user=user, device_id=user._device_id,
                                  supplier_id=body.supplier_id, supplier_name=body.supplier_name,
                                  items=[i.model_dump() for i in body.items],
                                  invoice_no=body.invoice_no, paid_amount=body.paid_amount,
                                  account_id=body.account_id, discount_total=body.discount_total,
                                  notes=body.notes, order_id=body.order_id)
    return _pur_out(p)


@app.get("/api/purchases")
def purchases_list(q: str = "", status: str = "", limit: int = 100,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.transactions import Purchase
    stmt = db.query(Purchase)
    if q:
        stmt = stmt.filter(Purchase.ref.ilike(f"%{q}%"))
    if status:
        stmt = stmt.filter(Purchase.status == status)
    return [_pur_out(p) for p in stmt.order_by(Purchase.id.desc()).limit(min(limit, 300)).all()]


@app.get("/api/purchases/{pid}")
def purchase_detail(pid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.transactions import Purchase
    p = db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Purchase not found.")
    return _pur_out(p)


class SupPayIn(BaseModel):
    supplier_id: int
    amount: float
    account_id: int
    purchase_id: int | None = None
    notes: str = ""


@app.post("/api/supplier-payments")
def supplier_payment(body: SupPayIn, db: Session = Depends(get_db),
                     user=Depends(require_permission("purchase.create"))):
    from app.services import purchases
    pay = purchases.pay_supplier(db, user=user, supplier_id=body.supplier_id,
                                 amount=body.amount, account_id=body.account_id,
                                 device_id=user._device_id, purchase_id=body.purchase_id,
                                 notes=body.notes)
    if isinstance(pay, dict):        # approval-required response (spec #36)
        return pay
    from app.services.ledger import supplier_balance
    return {"ref": pay.ref, "amount": pay.amount,
            "supplier_payable": round(supplier_balance(db, body.supplier_id), 2)}


# ---------------------------------------------------------------- orders ---
class OrderIn(BaseModel):
    supplier_id: int
    items: list[dict]           # [{product_id, qty_ordered, expected_cost}]
    notes: str = ""
    send: bool = False          # create directly in 'sent' state


def _ord_out(o):
    return {"id": o.id, "ref": o.ref, "supplier_id": o.supplier_id, "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None, "notes": o.notes,
            "items": [{"id": i.id, "product_id": i.product_id, "qty_ordered": i.qty_ordered,
                       "qty_received": i.qty_received or 0,
                       "remaining": round((i.qty_ordered or 0) - (i.qty_received or 0), 3),
                       "expected_cost": i.expected_cost} for i in o.items]}


@app.post("/api/orders")
def order_create(body: OrderIn, db: Session = Depends(get_db),
                 user=Depends(require_permission("order.manage"))):
    from app.services import purchases
    o = purchases.create_order(db, user=user, device_id=user._device_id,
                               supplier_id=body.supplier_id, items=body.items,
                               notes=body.notes, status="sent" if body.send else "draft")
    return _ord_out(o)


@app.get("/api/orders")
def orders_list(status: str = "", db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    from app.models.transactions import PurchaseOrder
    stmt = db.query(PurchaseOrder)
    if status:
        stmt = stmt.filter(PurchaseOrder.status == status)
    return [_ord_out(o) for o in stmt.order_by(PurchaseOrder.id.desc()).limit(200).all()]


@app.post("/api/orders/{oid}/status")
def order_status(oid: int, body: dict, db: Session = Depends(get_db),
                 user=Depends(require_permission("order.manage"))):
    from app.services import purchases
    o = purchases.set_order_status(db, user=user, order_id=oid,
                                   status=body.get("status", ""),
                                   device_id=user._device_id)
    return _ord_out(o)


class ReceiveIn(BaseModel):
    receipts: list[dict]        # [{order_item_id, qty}]
    paid_amount: float = 0
    account_id: int | None = None
    invoice_no: str = ""


@app.post("/api/orders/{oid}/receive")
def order_receive(oid: int, body: ReceiveIn, db: Session = Depends(get_db),
                  user=Depends(require_permission("purchase.receive"))):
    from app.services import purchases
    p = purchases.receive_against_order(db, user=user, device_id=user._device_id,
                                        order_id=oid, receipts=body.receipts,
                                        paid_amount=body.paid_amount,
                                        account_id=body.account_id, invoice_no=body.invoice_no)
    return _pur_out(p)


# -------------------------------------------------------------- returns ----
@app.get("/api/returns")
def returns_list(kind: str = "", q: str = "", db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    from app.models.transactions import Return
    stmt = db.query(Return)
    if kind:
        stmt = stmt.filter(Return.kind == kind)
    if q:
        stmt = stmt.filter(Return.ref.ilike(f"%{q}%"))
    return [{"id": r.id, "ref": r.ref, "kind": r.kind, "total": r.total_amount,
             "reason": r.reason, "refund_method": r.refund_method,
             "stock_condition": r.stock_condition, "sale_id": r.sale_id,
             "purchase_id": r.purchase_id, "at": r.created_at.isoformat() if r.created_at else None,
             "items": [{"product_id": i.product_id, "qty": i.qty,
                        "line_total": i.line_total} for i in r.items]}
            for r in stmt.order_by(Return.id.desc()).limit(200).all()]


@app.post("/api/purchases/{pid}/return")
def purchase_return(pid: int, body: dict, db: Session = Depends(get_db),
                    user=Depends(require_permission("purchase.create"))):
    from app.services import operations
    r = operations.supplier_return(db, user=user, device_id=user._device_id,
                                   purchase_id=pid, items=body.get("items", []),
                                   reason=body.get("reason", ""),
                                   resolution=body.get("resolution", "supplier_credit"),
                                   account_id=body.get("account_id"),
                                   condition=body.get("condition", "damaged"))
    return {"ref": r.ref, "total": r.total_amount}


# ------------------------------------------------------------- expenses ----
@app.get("/api/expense-categories")
def expense_categories(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.transactions import ExpenseCategory
    return [{"id": c.id, "name": c.name} for c in db.query(ExpenseCategory).order_by(
        ExpenseCategory.name).all()]


class ExpenseCatIn(BaseModel):
    name: str


@app.post("/api/expense-categories")
def expense_category_add(body: ExpenseCatIn, db: Session = Depends(get_db),
                         user=Depends(require_permission("settings.edit"))):
    from app.models.transactions import ExpenseCategory
    from app.services import audit
    if db.query(ExpenseCategory).filter(ExpenseCategory.name == body.name).first():
        raise HTTPException(400, "Category already exists.")
    c = ExpenseCategory(name=body.name.strip())
    db.add(c)
    audit.log(db, user=user, module="settings", action="create", entity="expense_category",
              entity_ref=body.name)
    db.commit()
    return {"id": c.id, "name": c.name}


class ExpenseIn(BaseModel):
    category_id: int
    amount: float
    account_id: int
    description: str = ""
    occurred_at: str | None = None


@app.post("/api/expenses")
def expense_create(body: ExpenseIn, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    from app.services import finance
    e = finance.create_expense(db, user=user, device_id=user._device_id,
                               category_id=body.category_id, amount=body.amount,
                               account_id=body.account_id, description=body.description,
                               occurred_at=_parse_dt(body.occurred_at))
    return {"id": e.id, "ref": e.ref, "amount": e.amount, "status": e.status}


@app.get("/api/expenses")
def expenses_list(limit: int = 200, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    from app.models.transactions import Expense, ExpenseCategory
    rows = db.query(Expense).order_by(Expense.id.desc()).limit(min(limit, 500)).all()
    cats = {c.id: c.name for c in db.query(ExpenseCategory).all()}
    return [{"id": e.id, "ref": e.ref, "category": cats.get(e.category_id),
             "amount": e.amount, "account_id": e.account_id, "description": e.description,
             "status": e.status, "at": e.occurred_at.isoformat() if e.occurred_at else None,
             "user_id": e.user_id} for e in rows]


@app.post("/api/expenses/{eid}/approve")
def expense_approve(eid: int, body: dict, db: Session = Depends(get_db),
                    user=Depends(require_permission("approval.grant"))):
    from app.services import finance
    e = finance.approve_expense(db, user=user, expense_id=eid,
                                approve=bool(body.get("approve", True)),
                                reason=body.get("reason", ""), device_id=user._device_id)
    return {"ref": e.ref, "status": e.status}


@app.post("/api/expenses/{eid}/cancel")
def expense_cancel(eid: int, body: dict, db: Session = Depends(get_db),
                   user=Depends(require_permission("expense.create"))):
    from app.services import finance
    e = finance.cancel_expense(db, user=user, expense_id=eid,
                               reason=body.get("reason", ""), device_id=user._device_id)
    return {"ref": e.ref, "status": e.status}


# -------------------------------------------------------- withdrawals ------
class WithdrawIn(BaseModel):
    amount: float
    account_id: int
    notes: str = ""


@app.post("/api/withdrawals")
def withdrawal_create(body: WithdrawIn, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    from app.services import finance
    w = finance.owner_withdrawal(db, user=user, device_id=user._device_id,
                                 amount=body.amount, account_id=body.account_id,
                                 notes=body.notes)
    return {"ref": w.ref, "amount": w.amount}


@app.get("/api/withdrawals")
def withdrawals_list(db: Session = Depends(get_db),
                     user=Depends(require_permission("profit.view"))):
    from app.models.transactions import OwnerWithdrawal
    return [{"ref": w.ref, "amount": w.amount, "account_id": w.account_id,
             "at": w.occurred_at.isoformat() if w.occurred_at else None, "notes": w.notes}
            for w in db.query(OwnerWithdrawal).order_by(OwnerWithdrawal.id.desc()).limit(200).all()]


# --------------------------------------------------------------- reports ---
def _parse_dt(s: str | None):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, f"Bad date '{s}' — use YYYY-MM-DD.")


@app.get("/api/reports/dashboard")
def report_dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services import reports
    d = reports.dashboard(db)
    if not user.role_has_permission("profit.view"):
        d.pop("today_gross_profit", None)
        d.pop("today_net_profit_estimate", None)
    return d


@app.get("/api/reports/profit")
def report_profit(start: str = "", end: str = "", db: Session = Depends(get_db),
                  user=Depends(require_permission("profit.view"))):
    from app.services import reports
    return reports.profit_summary(db, _parse_dt(start), _parse_dt(end))


@app.get("/api/reports/sales")
def report_sales(start: str = "", end: str = "", group_by: str = "day",
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services import reports
    return reports.sales_report(db, _parse_dt(start), _parse_dt(end), group_by)


@app.get("/api/reports/sales-by-product")
def report_sales_product(start: str = "", end: str = "", db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    from app.services import reports
    return reports.product_sales_report(db, _parse_dt(start), _parse_dt(end))


@app.get("/api/reports/payments")
def report_payments(start: str = "", end: str = "", db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    from app.services import reports
    return reports.payment_method_report(db, _parse_dt(start), _parse_dt(end))


@app.get("/api/reports/inventory")
def report_inventory(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services import reports
    return reports.inventory_snapshot(db)


@app.get("/api/reports/receivables")
def report_receivables(db: Session = Depends(get_db),
                       user=Depends(require_permission("customer.balance.view"))):
    from app.services import reports
    return reports.receivables(db)


@app.get("/api/reports/payables")
def report_payables(db: Session = Depends(get_db),
                    user=Depends(require_permission("supplier.balance.view"))):
    from app.services import reports
    return reports.payables(db)


@app.get("/api/reports/cash")
def report_cash(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services import reports
    return reports.cash_position(db)


@app.get("/api/reports/export.csv")
def report_export_csv(kind: str = "sales", start: str = "", end: str = "",
                      db: Session = Depends(get_db),
                      user=Depends(require_permission("data.export"))):
    from app.services import reports
    buf = io.StringIO()
    w = csv.writer(buf)
    if kind == "sales":
        rows = reports.sales_report(db, _parse_dt(start), _parse_dt(end), "day")
        w.writerow(["date", "sales_count", "gross", "discounts", "net"])
        for r in rows:
            w.writerow([r.get("period"), r.get("count"), r.get("gross"),
                        r.get("discounts"), r.get("net")])
    elif kind == "products":
        rows = reports.product_sales_report(db, _parse_dt(start), _parse_dt(end))
        w.writerow(["product", "qty", "amount", "cogs", "margin"])
        for r in rows:
            w.writerow([r.get("name"), r.get("qty"), r.get("amount"), r.get("cogs"),
                        r.get("margin")])
    elif kind == "profit":
        ps = reports.profit_summary(db, _parse_dt(start), _parse_dt(end))
        w.writerow(["metric", "value"])
        for k, v in ps.items():
            w.writerow([k, v])
    elif kind == "receivables":
        rc = reports.receivables(db)
        w.writerow(["customer", "balance"])
        for c in rc.get("customers", []):
            w.writerow([c.get("name"), c.get("balance")])
    elif kind == "payables":
        py = reports.payables(db)
        w.writerow(["supplier", "payable"])
        for sp in py.get("suppliers", []):
            w.writerow([sp.get("name"), sp.get("payable")])
    else:
        raise HTTPException(400, "kind must be sales|products|profit|receivables|payables")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})


# ------------------------------------------------------- notifications -----
@app.get("/api/notifications")
def notifications_list(status: str = "", limit: int = 200, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    from app.models.system import Notification
    stmt = db.query(Notification)
    if status:
        stmt = stmt.filter(Notification.status == status)
    return [{"id": n.id, "channel": n.channel, "to": n.to_phone, "template": n.template,
             "message": n.message, "status": n.status, "error": n.error,
             "retries": n.retry_count, "at": n.created_at.isoformat() if n.created_at else None}
            for n in stmt.order_by(Notification.id.desc()).limit(min(limit, 500)).all()]


class NotifyIn(BaseModel):
    to: str
    message: str
    template: str = "manual"
    customer_name: str = ""


@app.post("/api/notifications/send")
def notification_send(body: NotifyIn, db: Session = Depends(get_db),
                      user=Depends(require_permission("notification.send"))):
    from app.services import notify, audit
    n = notify.queue_whatsapp(db, to=body.to, template=body.template, message=body.message,
                              user=user, customer_name=body.customer_name)
    audit.log(db, user=user, module="notifications", action="queue", entity="notification",
              entity_id=n.id, new_value={"to": body.to, "template": body.template})
    db.commit()
    res = notify.process_pending(db)
    db.commit()
    return {"id": n.id, "status": n.status, "error": n.error, "processed": res}


@app.post("/api/notifications/{nid}/retry")
def notification_retry(nid: int, db: Session = Depends(get_db),
                       user=Depends(require_permission("notification.send"))):
    from app.models.system import Notification
    n = db.get(Notification, nid)
    if not n:
        raise HTTPException(404, "Notification not found.")
    if n.status not in ("failed", "cancelled"):
        raise HTTPException(400, f"Only failed/cancelled messages can be retried (status: {n.status}).")
    n.status = "retry"
    n.error = None
    db.commit()
    res = notify.process_pending(db)
    db.commit()
    return {"status": n.status, "processed": res}


# --------------------------------------------------------- users & roles ---
@app.get("/api/users")
def users_list(db: Session = Depends(get_db), user=Depends(require_permission("users.manage"))):
    from app.models.auth import User
    return [{"id": u.id, "username": u.username, "full_name": u.full_name,
             "role": u.role.name if u.role else None, "role_id": u.role_id,
             "is_active": u.is_active, "phone": u.phone}
            for u in db.query(User).order_by(User.username).all()]


class UserIn(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role_id: int
    phone: str = ""


@app.post("/api/users")
def user_create(body: UserIn, db: Session = Depends(get_db),
                user=Depends(require_permission("users.manage"))):
    from app.models.auth import User, Role
    from app.core.security import hash_password
    from app.services import audit
    if db.query(User).filter(User.username == body.username.strip()).first():
        raise HTTPException(400, "Username already exists.")
    role = db.get(Role, body.role_id)
    if not role:
        raise HTTPException(400, "Role not found.")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    u = User(username=body.username.strip(), full_name=body.full_name or body.username,
             password_hash=hash_password(body.password), role_id=role.id, phone=body.phone)
    db.add(u)
    audit.log(db, user=user, module="users", action="create", entity="user",
              entity_ref=u.username, new_value={"role": role.name})
    db.commit()
    return {"id": u.id, "username": u.username}


@app.put("/api/users/{uid}")
def user_update(uid: int, body: dict, db: Session = Depends(get_db),
                user=Depends(require_permission("users.manage"))):
    from app.models.auth import User
    from app.services import audit
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found.")
    prev, new = {}, {}
    if "role_id" in body and body["role_id"] != u.role_id:
        prev["role_id"] = u.role_id
        u.role_id = body["role_id"]
        new["role_id"] = body["role_id"]
    if "is_active" in body and bool(body["is_active"]) != bool(u.is_active):
        if not u.is_active and u.role and u.role.is_owner_role and \
                db.query(User).filter(User.is_active == True).count() <= 1:  # noqa: E712
            raise HTTPException(400, "Cannot disable the last active owner account.")
        prev["is_active"] = u.is_active
        u.is_active = bool(body["is_active"])
        new["is_active"] = u.is_active
        if not u.is_active:
            from app.models.auth import Session as Sess
            db.query(Sess).filter(Sess.user_id == u.id).delete()   # force logout
    for k in ("full_name", "phone"):
        if k in body and getattr(u, k) != body[k]:
            setattr(u, k, body[k])
            new[k] = body[k]
    if "password" in body and body["password"]:
        from app.core.security import hash_password
        if len(str(body["password"])) < 6:
            raise HTTPException(400, "Password must be at least 6 characters.")
        u.password_hash = hash_password(str(body["password"]))
        new["password"] = "***changed***"
        from app.models.auth import Session as Sess
        db.query(Sess).filter(Sess.user_id == u.id).delete()
    if new:
        audit.log(db, user=user, module="users", action="update", entity="user",
                  entity_id=u.id, entity_ref=u.username, prev_value=prev, new_value=new)
    db.commit()
    return {"ok": True}


@app.get("/api/roles")
def roles_list(db: Session = Depends(get_db), user=Depends(require_permission("users.manage"))):
    from app.models.auth import Role
    return [{"id": r.id, "name": r.name, "is_owner_role": r.is_owner_role,
             "max_discount_percent": r.max_discount_percent,
             "permissions": sorted(p.key for p in r.permissions)}
            for r in db.query(Role).order_by(Role.name).all()]


class RolePermsIn(BaseModel):
    permissions: list[str]
    max_discount_percent: float | None = None


@app.put("/api/roles/{rid}/permissions")
def role_permissions_set(rid: int, body: RolePermsIn, db: Session = Depends(get_db),
                         user=Depends(require_permission("users.manage"))):
    """Granular, configurable permissions (spec #34/#35) — audited."""
    from app.models.auth import Role, Permission
    from app.services import audit
    r = db.get(Role, rid)
    if not r:
        raise HTTPException(404, "Role not found.")
    if r.is_owner_role:
        raise HTTPException(400, "The Owner role always has every permission and cannot be edited.")
    perms = db.query(Permission).filter(Permission.key.in_(body.permissions)).all()
    prev = sorted(p.key for p in r.permissions)
    r.permissions = perms
    if body.max_discount_percent is not None:
        r.max_discount_percent = float(body.max_discount_percent)
    audit.log(db, user=user, module="users", action="permission_change", entity="role",
              entity_id=r.id, entity_ref=r.name,
              prev_value={"permissions": prev},
              new_value={"permissions": sorted(p.key for p in perms),
                         "max_discount_percent": r.max_discount_percent})
    db.commit()
    return {"ok": True, "permissions": sorted(p.key for p in perms)}


@app.get("/api/permissions")
def permissions_list(db: Session = Depends(get_db),
                     user=Depends(require_permission("users.manage"))):
    from app.models.auth import Permission
    return [{"key": p.key, "description": p.description}
            for p in db.query(Permission).order_by(Permission.key).all()]


# -------------------------------------------------------------- approvals --
@app.get("/api/approvals")
def approvals_list(status: str = "pending", db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    from app.models.auth import Approval
    stmt = db.query(Approval)
    if status:
        stmt = stmt.filter(Approval.status == status)
    return [{"id": a.id, "action": a.action, "amount": a.amount, "status": a.status,
             "payload": a.payload_json, "requested_by": a.requested_by,
             "requested_at": a.requested_at.isoformat() if a.requested_at else None,
             "reason": a.reason} for a in stmt.order_by(Approval.id.desc()).limit(200).all()]


@app.post("/api/approvals/{aid}/decide")
def approval_decide(aid: int, body: dict, db: Session = Depends(get_db),
                    user=Depends(require_permission("approval.grant"))):
    from app.models.auth import Approval
    from app.services import audit, sales as sales_svc, finance
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404, "Approval request not found.")
    if a.status != "pending":
        raise HTTPException(400, f"Already {a.status}.")
    approve = bool(body.get("approve"))
    a.status = "approved" if approve else "rejected"
    a.decided_by = user.id
    a.decided_at = datetime.now(timezone.utc)
    a.reason = body.get("reason", a.reason or "")
    result = None
    payload = json.loads(a.payload_json) if a.payload_json else {}
    if approve and a.action == "sale.create":
        s_obj = sales_svc.create_sale(db, user=user, device_id=user._device_id,
                                      items=payload["items"],
                                      customer_id=payload.get("customer_id"),
                                      payments=payload.get("payments", []),
                                      credit_mode=payload.get("credit_mode", "none"),
                                      dasti_data=payload.get("dasti"),
                                      extra_discount=payload.get("extra_discount", 0),
                                      notes=payload.get("notes", ""))
        result = {"sale_ref": s_obj.ref, "grand_total": s_obj.grand_total}
    elif approve and a.action == "expense.create" and payload.get("expense_id"):
        e = finance.approve_expense(db, user=user, expense_id=payload["expense_id"],
                                    approve=True, reason=a.reason, device_id=user._device_id)
        result = {"expense_ref": e.ref, "status": e.status}
    elif not approve and a.action == "expense.create" and payload.get("expense_id"):
        e = finance.approve_expense(db, user=user, expense_id=payload["expense_id"],
                                    approve=False, reason=a.reason, device_id=user._device_id)
        result = {"expense_ref": e.ref, "status": e.status}
    audit.log(db, user=user, module="approvals", action="approve" if approve else "reject",
              entity="approval", entity_id=a.id, amount=a.amount,
              reason=a.reason, approval_id=a.id)
    db.commit()
    return {"ok": True, "status": a.status, "result": result}


@app.post("/api/pos/sales/request-approval")
def request_sale_approval(body: SaleIn,
                          total_estimate: float = 0,
                          manager_username: str = "", manager_password: str = "",
                          reason: str = "", db: Session = Depends(get_db),
                          user=Depends(require_permission("sale.create"))):
    """Cashier hits discount approval threshold -> manager PIN approves inline
    (typical karyana flow) OR queues for owner review."""
    from app.models.auth import Approval, User as U, Session as Sess
    from app.core.security import verify_password
    from app.services import sales as sales_svc, audit
    items = [i.model_dump(exclude_none=True) for i in body.items]
    if not items:
        raise HTTPException(400, "No sale to approve.")
    pin_user = None
    if manager_username and manager_password:
        pu = db.query(U).filter(U.username == manager_username.strip()).first()
        if pu and pu.is_active and verify_password(manager_password, pu.password_hash):
            if pu.role_has_permission("approval.grant"):
                pin_user = pu
            else:
                raise HTTPException(403, f"{pu.username} does not have approval rights.")
        else:
            raise HTTPException(401, "Manager credentials are incorrect.")
    total = float(total_estimate or 0)
    ap = Approval(action="sale.create", entity_type="sale",
                  payload_json=json.dumps({"items": items,
                                           "customer_id": body.customer_id,
                                           "payments": [p.model_dump(exclude_none=True)
                                                       for p in body.payments],
                                           "credit_mode": body.credit_mode,
                                           "dasti": body.dasti,
                                           "extra_discount": body.extra_discount,
                                           "notes": body.notes}),
                  amount=total, requested_by=user.id, status="pending")
    db.add(ap)
    db.flush()
    if pin_user:
        ap.status = "approved"
        ap.decided_by = pin_user.id
        ap.decided_at = datetime.now(timezone.utc)
        ap.reason = reason or "Manager approved at counter"
        s_obj = sales_svc.create_sale(db, user=user, device_id=user._device_id,
                                      items=items, customer_id=body.customer_id,
                                      payments=[p.model_dump(exclude_none=True)
                                                for p in body.payments],
                                      credit_mode=body.credit_mode, dasti_data=body.dasti,
                                      extra_discount=body.extra_discount,
                                      notes=body.notes, approver=pin_user)
        from app.services import receipts
        audit.log(db, user=pin_user, device_id=user._device_id, module="approvals",
                  action="approve", entity="approval", entity_id=ap.id, amount=total,
                  reason=ap.reason, approval_id=ap.id)
        db.commit()
        return {"approved_inline": True, "sale": sale_out(db, s_obj),
                "receipt": receipts.receipt_text(db, s_obj)}
    audit.log(db, user=user, module="approvals", action="request", entity="approval",
              entity_id=ap.id, amount=total, new_value={"queued_for": "owner/manager"})
    db.commit()
    return {"queued": True, "approval_id": ap.id}


# ---------------------------------------------------------------- backup ---
@app.get("/api/backups")
def backups_list(db: Session = Depends(get_db),
                 user=Depends(require_permission("backup.manage"))):
    from app.services import backup
    return backup.list_backups(db)


@app.post("/api/backups/create")
def backup_create(db: Session = Depends(get_db),
                  user=Depends(require_permission("backup.manage"))):
    from app.services import backup, audit
    rec = backup.create_backup(db, user=user, kind="local")
    audit.log(db, user=user, module="backup", action="backup", entity="backup",
              entity_id=rec.id, new_value={"file": rec.file_path, "size": rec.size_bytes})
    db.commit()
    return {"id": rec.id, "file": rec.file_path.split("/")[-1], "size_bytes": rec.size_bytes,
            "sha256": rec.sha256}


@app.get("/api/backups/{bid}/verify")
def backup_verify(bid: int, db: Session = Depends(get_db),
                  user=Depends(require_permission("backup.manage"))):
    from app.services import backup
    return backup.verify_backup(db, bid)


@app.get("/api/backups/{bid}/download")
def backup_download(bid: int, db: Session = Depends(get_db),
                    user=Depends(require_permission("backup.manage"))):
    from app.models.system import BackupRecord
    b = db.get(BackupRecord, bid)
    if not b or not os.path.exists(b.file_path):
        raise HTTPException(404, "Backup file not found on disk.")
    return FileResponse(b.file_path, filename=os.path.basename(b.file_path),
                        media_type="application/octet-stream")


class RestoreIn(BaseModel):
    confirm_text: str


@app.post("/api/backups/{bid}/restore")
def backup_restore(bid: int, body: RestoreIn, db: Session = Depends(get_db),
                   user=Depends(require_permission("backup.manage"))):
    from app.services import backup
    res = backup.restore_backup(db, backup_id=bid, confirm_text=body.confirm_text, user=user)
    return res


# ---------------------------------------------------------- import/export --
@app.get("/api/export/{what}")
def export_csv(what: str, db: Session = Depends(get_db),
               user=Depends(require_permission("data.export"))):
    from app.services import io_import_export as io_svc
    fn = {"products": io_svc.export_products_csv,
          "customers": io_svc.export_customers_csv,
          "suppliers": io_svc.export_suppliers_csv}.get(what)
    if not fn:
        raise HTTPException(400, "Choose products|customers|suppliers.")
    return PlainTextResponse(fn(db), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{what}.csv"'})


@app.post("/api/import/products")
async def import_products(file: UploadFile,
                          db: Session = Depends(get_db),
                          user=Depends(require_permission("product.manage"))):
    from app.services import io_import_export as io_svc
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    return io_svc.import_products_csv(db, content, user=user, device_id=user._device_id)


@app.post("/api/import/customers")
async def import_customers(file: UploadFile,
                           db: Session = Depends(get_db),
                           user=Depends(require_permission("customer.create"))):
    from app.services import io_import_export as io_svc
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    return io_svc.import_customers_csv(db, content, user=user, device_id=user._device_id)


# ------------------------------------------------------ static frontend --
# When the built React app is present, serve it from the same origin so
# users only need ONE process. Search order (first hit wins):
#   1. bundled inside a frozen PyInstaller EXE  (_MEIPASS/dist)
#   2. backend/dist/frontend                    (populated by build_windows.bat)
#   3. ../frontend/dist                         (dev layout)
_DIST_CANDIDATES = [
    Path(getattr(sys, "_MEIPASS", "")) / "dist" if hasattr(sys, "_MEIPASS") else None,
    Path(__file__).resolve().parent.parent / "dist" / "frontend",
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
]
_dist = next((p for p in _DIST_CANDIDATES if p and p.is_dir() and (p / "index.html").exists()), None)
if _dist:
    from fastapi.staticfiles import StaticFiles

    if (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="spa-assets")

    @app.get("/{full_path:path}")
    def _spa_fallback(full_path: str):
        # Real files (favicon, icons) are served directly; everything else
        # falls through to the React router (SPA deep links like /pos).
        f = _dist / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
