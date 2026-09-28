"""Password hashing + bearer-token sessions (server-side session records, revocable)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()
    return hmac.compare_digest(check, digest)


def create_session(db: Session, user_id: int, device_id: str) -> str:
    from app.models.auth import Session as SessionModel
    token = secrets.token_urlsafe(32)
    s = get_settings()
    sess = SessionModel(
        token=token, user_id=user_id, device_id=device_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=s.token_ttl_hours),
    )
    db.add(sess)
    db.commit()
    return token


def revoke_session(db: Session, token: str):
    from app.models.auth import Session as SessionModel
    db.query(SessionModel).filter(SessionModel.token == token).delete()
    db.commit()


def _as_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer),
                     db: Session = Depends(get_db)):
    from app.models.auth import User, Session as SessionModel
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    sess = db.query(SessionModel).filter(SessionModel.token == credentials.credentials).first()
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again")
    if _as_utc(sess.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")
    # Device authorization (spec #46/#65): revoked devices cannot operate the system
    from app.models.auth import Device
    dev = db.query(Device).filter(Device.device_id == sess.device_id).first()
    if dev is not None and not dev.authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Device {sess.device_id} has been revoked by the owner.")
    user._device_id = sess.device_id  # type: ignore[attr-defined]
    user._token = credentials.credentials  # type: ignore[attr-defined]
    return user


def require_permission(perm: str):
    """Dependency factory enforcing granular permissions server-side."""
    def checker(user=Depends(get_current_user)):
        if not user.role_has_permission(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail=f"You do not have permission: {perm}")
        return user
    return checker
