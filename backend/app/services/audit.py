"""Audit trail: append-only, hash-chained. No update/delete API for normal users."""
import hashlib
import json
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.system import AuditLog


def _hash(prev_hash: str, payload: dict) -> str:
    data = (prev_hash or "") + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def log(db: Session, *, user=None, device_id: str = "", module: str, action: str,
        entity: str = "", entity_id=None, entity_ref: str = "",
        prev_value=None, new_value=None, reason: str = "",
        related_transaction: str = "", approval_id=None, amount=None):
    """Call inside the SAME transaction as the business change (flushed on commit)."""
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last.row_hash if last else "GENESIS"
    # Normalize exactly as the columns are stored so verify_chain can reproduce the hash.
    norm_prev = json.loads(prev_value) if isinstance(prev_value, str) and prev_value else prev_value
    norm_new = json.loads(new_value) if isinstance(new_value, str) and new_value else new_value
    payload = {
        "user_id": getattr(user, "id", None), "module": module, "action": action,
        "entity": entity, "entity_id": str(entity_id) if entity_id is not None else None,
        "entity_ref": entity_ref or None,
        "prev": norm_prev, "new": norm_new, "reason": reason or None,
        "amount": amount, "related": related_transaction or None,
    }
    row = AuditLog(
        audit_uuid=str(_uuid.uuid4()),
        user_id=getattr(user, "id", None),
        username=getattr(user, "username", None),
        role=(user.role.name if getattr(user, "role", None) else None),
        device_id=device_id or getattr(user, "_device_id", ""),
        timestamp=datetime.now(timezone.utc),
        module=module, action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        entity_ref=entity_ref or None,
        prev_value=json.dumps(norm_prev, default=str) if norm_prev is not None else None,
        new_value=json.dumps(norm_new, default=str) if norm_new is not None else None,
        reason=reason or None, related_transaction=related_transaction or None,
        approval_id=approval_id, amount=amount,
        prev_hash=prev_hash, row_hash=_hash(prev_hash, payload),
    )
    db.add(row)
    return row


def verify_chain(db: Session):
    """Tamper-detection: recompute hashes; returns (ok, first_bad_id)."""
    prev_hash = "GENESIS"
    for row in db.query(AuditLog).order_by(AuditLog.id).all():
        payload = {
            "user_id": row.user_id, "module": row.module, "action": row.action,
            "entity": row.entity, "entity_id": row.entity_id, "entity_ref": row.entity_ref,
            "prev": json.loads(row.prev_value) if row.prev_value else None,
            "new": json.loads(row.new_value) if row.new_value else None,
            "reason": row.reason, "amount": row.amount, "related": row.related_transaction,
        }
        expect = _hash(prev_hash, payload)
        if row.row_hash != expect or row.prev_hash != prev_hash:
            return False, row.id
        prev_hash = row.row_hash
    return True, None
