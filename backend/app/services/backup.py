"""Backup & restore (spec #47). Real SQLite file backups with checksums. Restore requires
strong confirmation + permission; a safety snapshot of current data is taken first."""
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.system import BackupRecord
from app.services.settings_service import get_num
from app.core.config import get_settings


def _db_path(db: Session) -> str:
    url = db.bind.url.database if hasattr(db.bind.url, "database") else None
    if not url or not str(db.bind.url).startswith("sqlite"):
        raise HTTPException(400, "File-level backup is available for the local SQLite database. "
                                 "For PostgreSQL use pg_dump (see docs/CLOUD_SETUP.md).")
    return url


def create_backup(db: Session, *, user=None, kind: str = "local") -> BackupRecord:
    s = get_settings()
    path = _db_path(db)
    bdir = os.path.join(s.data_dir, "backups")
    os.makedirs(bdir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(bdir, f"karyana-backup-{stamp}.sqlite")
    # online backup API so we never copy a half-written DB
    src = sqlite3.connect(path)
    dst = sqlite3.connect(dest)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close(); dst.close()
    h = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    rec = BackupRecord(file_path=dest, size_bytes=os.path.getsize(dest), version=s.version,
                       kind=kind, status="ok", created_by=getattr(user, "id", None), sha256=h)
    db.add(rec)
    db.commit()
    # prune old backups per setting
    keep = int(get_num(db, "backup.keep_count", 14))
    rows = db.query(BackupRecord).filter(BackupRecord.kind == "local") \
             .order_by(BackupRecord.created_at.desc()).offset(keep).all()
    for r in rows:
        if os.path.exists(r.file_path):
            os.remove(r.file_path)
        db.delete(r)
    db.commit()
    return rec


def list_backups(db: Session) -> list[dict]:
    out = []
    for b in db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(100).all():
        out.append({"id": b.id, "file": os.path.basename(b.file_path), "size_bytes": b.size_bytes,
                    "version": b.version, "kind": b.kind, "status": b.status,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                    "sha256": b.sha256})
    return out


def verify_backup(db: Session, backup_id: int) -> dict:
    b = db.get(BackupRecord, backup_id)
    if not b:
        raise HTTPException(404, "Backup not found.")
    if not os.path.exists(b.file_path):
        return {"ok": False, "error": "Backup file missing from disk."}
    h = hashlib.sha256(open(b.file_path, "rb").read()).hexdigest()
    ok = h == b.sha256
    return {"ok": ok, "expected": b.sha256, "actual": h}


def restore_backup(db: Session, *, backup_id: int, confirm_text: str, user=None) -> dict:
    """Dangerous operation: requires typing RESTORE. Current DB is backed up first."""
    if confirm_text != "RESTORE":
        raise HTTPException(400, "Type exactly 'RESTORE' to confirm. Nothing was changed.")
    if not user or not user.role_has_permission("backup.manage"):
        raise HTTPException(403, "You do not have backup/restore permission.")
    b = db.get(BackupRecord, backup_id)
    if not b or not os.path.exists(b.file_path):
        raise HTTPException(404, "Backup file not found.")
    v = verify_backup(db, backup_id)
    if not v["ok"]:
        raise HTTPException(400, "Backup checksum verification failed — refusing to restore.")
    path = _db_path(db)
    safety = create_backup(db, user=user, kind="local")   # never silently overwrite current data
    db.commit()
    dst_conn = sqlite3.connect(path)
    try:
        src_conn = sqlite3.connect(b.file_path)
        try:
            with dst_conn:
                src_conn.backup(dst_conn)   # in-place online restore, no file-lock issues
        finally:
            src_conn.close()
    finally:
        dst_conn.close()
    from app.services import audit as audit_service
    audit_service.log(db, user=user, module="backup", action="restore", entity="backup",
                      entity_id=b.id, reason=f"Restored {os.path.basename(b.file_path)}",
                      new_value={"safety_backup": safety.file_path})
    db.commit()
    return {"restored": True, "safety_backup": os.path.basename(safety.file_path)}
