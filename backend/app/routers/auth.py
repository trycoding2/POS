from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (get_current_user, hash_password, verify_password,
                               create_session, revoke_session)
from app.models.auth import User, Device
from app.services import audit, setup
from app.services.settings_service import all_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginReq(BaseModel):
    username: str
    password: str
    device_id: str = "POS-01"


class SetupReq(BaseModel):
    store_name: str
    owner_username: str
    owner_password: str = Field(min_length=6)
    owner_full_name: str = ""
    currency_symbol: str | None = None
    address: str = ""
    phone: str = ""
    whatsapp: str = ""
    opening_cash: float = 0


@router.get("/initialized")
def initialized(db: Session = Depends(get_db)):
    return {"initialized": setup.is_initialized(db)}


@router.post("/setup")
def setup_wizard(req: SetupReq, db: Session = Depends(get_db)):
    res = setup.run_setup(db, **req.model_dump())
    token = create_session(db, res["owner_id"], "POS-01")
    return {"ok": True, "token": token}


@router.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username.strip()).first()
    ok = bool(user and user.is_active and verify_password(req.password, user.password_hash))
    if not ok:
        # failed logins are audited too — but without a valid user we still record by name
        audit.log(db, module="auth", action="login_failed", entity="user",
                  entity_ref=req.username, device_id=req.device_id,
                  reason="Bad credentials or disabled account")
        db.commit()
        raise HTTPException(401, "Incorrect username or password.")
    token = create_session(db, user.id, req.device_id)
    dev = db.query(Device).filter(Device.device_id == req.device_id).first()
    if not dev:
        db.add(Device(device_id=req.device_id, name=req.device_id, user_id=user.id))
    else:
        dev.last_activity_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    audit.log(db, user=user, device_id=req.device_id, module="auth", action="login",
              entity="user", entity_id=user.id, entity_ref=user.username)
    db.commit()
    return {"token": token, "user": _user_out(db, user), "settings": all_settings(db)}


@router.post("/logout")
def logout(user=Depends(get_current_user), db: Session = Depends(get_db)):
    tok = getattr(user, "_token", None)
    if tok:
        revoke_session(db, tok)
    audit.log(db, user=user, module="auth", action="logout", entity="user",
              entity_id=user.id, entity_ref=user.username)
    db.commit()
    return {"ok": True}


def _user_out(db: Session, user: User) -> dict:
    return {
        "id": user.id, "username": user.username, "full_name": user.full_name,
        "role": user.role.name if user.role else None,
        "is_owner": bool(user.role and user.role.is_owner_role),
        "permissions": sorted(list_all_perms(user)),
        "max_discount_percent": user.role.max_discount_percent if user.role else 0,
    }


def list_all_perms(user: User) -> set:
    from app.models.auth import ALL_PERMISSIONS
    if user.role and user.role.is_owner_role:
        return set(ALL_PERMISSIONS)
    return {p.key for p in (user.role.permissions if user.role else [])}


@router.get("/me")
def me(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {"user": _user_out(db, user), "settings": all_settings(db)}
