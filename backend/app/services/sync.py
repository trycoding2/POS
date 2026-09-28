"""Offline-first sync engine (spec #43-#46).

Local writes always succeed and are enqueued. Sync pushes queued records to the cloud
server using UUID-keyed idempotent upserts — replays never duplicate transactions.
Works fully offline: queue simply stays 'pending' until connectivity returns.
"""
import json
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.system import SyncQueue
from app.services.settings_service import get_bool, get_setting
from app.core.config import get_settings


def enqueue(db: Session, entity_type: str, entity_uuid: str, payload: dict,
            device_id: str = ""):
    """Called inside business transactions (flush only; commit by caller)."""
    existing = db.query(SyncQueue).filter(SyncQueue.entity_uuid == entity_uuid).first()
    if existing:
        existing.payload_json = json.dumps(payload, default=str)
        if existing.status in ("synced",):
            existing.status = "pending"   # updated after sync -> re-push
        return existing
    q = SyncQueue(entity_type=entity_type, entity_uuid=entity_uuid,
                  payload_json=json.dumps(payload, default=str), status="pending",
                  device_id=device_id)
    db.add(q)
    db.flush()
    return q


def pending_count(db: Session) -> int:
    return db.query(SyncQueue).filter(SyncQueue.status.in_(["pending", "failed", "retry"])).count()


def run_sync(db: Session) -> dict:
    """Push all pending rows to configured cloud endpoint. Idempotent via entity_uuid."""
    s = get_settings()
    stats = {"pushed": 0, "failed": 0, "skipped": 0}
    if not s.cloud_url or not s.cloud_api_key:
        stats["skipped"] = pending_count(db)
        stats["error"] = ("Cloud sync is not configured. Set KARYANA_CLOUD_URL and "
                          "KARYANA_CLOUD_API_KEY (your sync server / PostgreSQL backend).")
        return stats
    if not get_bool(db, "sync.enabled"):
        stats["skipped"] = pending_count(db)
        stats["error"] = "Sync disabled in settings."
        return stats
    rows = db.query(SyncQueue).filter(
        SyncQueue.status.in_(["pending", "failed", "retry"])).order_by(SyncQueue.id).all()
    import httpx
    for q in rows:
        q.status = "uploading"
        q.last_attempt_at = datetime.now(timezone.utc)
        try:
            resp = httpx.post(f"{s.cloud_url.rstrip('/')}/api/sync/push",
                              headers={"X-API-Key": s.cloud_api_key},
                              json={"device_id": q.device_id or s.device_id,
                                    "record": {"entity_type": q.entity_type,
                                               "entity_uuid": q.entity_uuid,
                                               "payload": json.loads(q.payload_json)}},
                              timeout=20)
            if resp.status_code in (200, 201, 208):     # 208 = already reported (idempotent)
                q.status = "synced"
                q.error = None
                stats["pushed"] += 1
            elif resp.status_code == 409:
                q.status = "conflict"
                q.error = resp.text[:300]
                stats["failed"] += 1
            else:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            q.status = "failed" if (q.retry_count or 0) >= 5 else "retry"
            q.retry_count = (q.retry_count or 0) + 1
            q.error = str(e)[:300]
            stats["failed"] += 1
        db.commit()
    return stats


def pull_changes(db: Session) -> dict:
    """Pull remote records (other devices) — idempotent upsert by uuid. Requires cloud config."""
    s = get_settings()
    if not s.cloud_url or not s.cloud_api_key:
        return {"error": "Cloud sync is not configured.", "pulled": 0}
    import httpx
    since = db.query(SyncQueue).filter(SyncQueue.server_version.isnot(None)) \
              .with_entities(SyncQueue.server_version).order_by(SyncQueue.server_version.desc()).first()
    try:
        resp = httpx.get(f"{s.cloud_url.rstrip('/')}/api/sync/pull",
                         headers={"X-API-Key": s.cloud_api_key},
                         params={"since": since[0] if since else 0, "device_id": s.device_id},
                         timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)[:300], "pulled": 0}
    pulled = 0
    for rec in data.get("records", []):
        existing = db.query(SyncQueue).filter(SyncQueue.entity_uuid == rec["entity_uuid"]).first()
        if existing and (existing.server_version or 0) >= rec.get("version", 0):
            continue
        if existing:
            existing.server_version = rec.get("version")
            existing.status = "synced"
        else:
            db.add(SyncQueue(entity_type=rec["entity_type"], entity_uuid=rec["entity_uuid"],
                             payload_json=json.dumps(rec.get("payload", {})),
                             status="synced", server_version=rec.get("version"),
                             device_id="remote"))
        pulled += 1
    db.commit()
    return {"pulled": pulled, "cursor_version": data.get("cursor")}
