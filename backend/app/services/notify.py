"""Notification engine (spec #42). Queue + worker. WhatsApp via official Business Platform API.

Business transactions NEVER block on notifications; failures are recorded and retryable.
If credentials are not configured, sending is attempted only when enabled and a clear
status ('failed: not configured') is stored — the UI shows exactly what to configure.
"""
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.system import Notification
from app.services.settings_service import get_bool, get_setting
from app.core.config import get_settings


def queue_whatsapp(db: Session, *, to: str, template: str, message: str,
                   entity_type: str = "", entity_ref: str = "", user=None,
                   customer_name: str = "") -> Notification:
    n = Notification(uuid=str(_uuid.uuid4()), channel="whatsapp", to_phone=to,
                     customer_name=customer_name, template=template, message=message,
                     status="pending", entity_type=entity_type or None,
                     entity_ref=entity_ref or None, created_by=getattr(user, "id", None))
    db.add(n)
    db.flush()
    return n


def process_pending(db: Session, limit: int = 20) -> dict:
    """Send queued notifications. Safe to call from background loop / manual button."""
    s = get_settings()
    cfg_ok = bool(s.whatsapp_api_url and s.whatsapp_api_token and s.whatsapp_phone_number_id)
    sent = failed = 0
    rows = db.query(Notification).filter(
        Notification.status.in_(["pending", "retry"])).order_by(Notification.id).limit(limit).all()
    for n in rows:
        n.status = "sending"
        n.last_attempt_at = datetime.now(timezone.utc)
        if not cfg_ok or not get_bool(db, "whatsapp.enabled"):
            n.status = "failed"
            n.error = ("WhatsApp is not configured. Set KARYANA_WHATSAPP_API_URL / TOKEN / "
                       "PHONE_NUMBER_ID (official WhatsApp Business Platform) and enable in Settings.")
            failed += 1
            db.commit()
            continue
        try:
            import httpx
            resp = httpx.post(
                f"{s.whatsapp_api_url.rstrip('/')}/{s.whatsapp_phone_number_id}/messages",
                headers={"Authorization": f"Bearer {s.whatsapp_api_token}"},
                json={"messaging_product": "whatsapp", "to": n.to_phone,
                      "type": "text", "text": {"body": n.message}},
                timeout=15)
            if resp.status_code == 200:
                n.status = "sent"
                sent += 1
            else:
                n.status = "retry" if n.retry_count < 3 else "failed"
                n.retry_count = (n.retry_count or 0) + 1
                n.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                failed += 1
        except Exception as e:  # network down etc. — never crash caller
            n.status = "retry" if (n.retry_count or 0) < 3 else "failed"
            n.retry_count = (n.retry_count or 0) + 1
            n.error = str(e)[:300]
            failed += 1
        db.commit()
    return {"processed": len(rows), "sent": sent, "failed": failed}
