"""System entities: settings, audit log, notifications, sync queue, backups."""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey, Index

from app.core.database import Base
from app.models.auth import utcnow


class Setting(Base):
    """Key-value store; UI/business reads settings here — nothing hardcoded."""
    __tablename__ = "settings"
    key = Column(String(80), primary_key=True)
    value = Column(Text)
    description = Column(String(200))
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))


class AuditLog(Base):
    """Append-only, tamper-resistant (no update/delete API exposed to normal users).
    Each row chains a hash of the previous row so tampering is detectable."""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    audit_uuid = Column(String(36), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    username = Column(String(50))
    role = Column(String(60))
    device_id = Column(String(60))
    timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)
    module = Column(String(40), index=True)     # pos/inventory/purchases/...
    action = Column(String(40), index=True)     # create/update/void/payment/price_change/login/...
    entity = Column(String(40))
    entity_id = Column(String(40))
    entity_ref = Column(String(40))
    prev_value = Column(Text)
    new_value = Column(Text)
    reason = Column(Text)
    related_transaction = Column(String(40))
    approval_id = Column(Integer)
    amount = Column(Float)
    prev_hash = Column(String(64))
    row_hash = Column(String(64))
    __table_args__ = (Index("ix_audit_user_time", "user_id", "timestamp"),)


class Notification(Base):
    """WhatsApp/SMS/in-app notification queue. Never blocks a business transaction."""
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    channel = Column(String(20), default="whatsapp")   # whatsapp/sms/inapp/email
    to_phone = Column(String(30))
    customer_name = Column(String(120))
    template = Column(String(60))                       # sale_receipt/khata_reminder/dasti_reminder/...
    message = Column(Text)
    status = Column(String(20), default="pending")      # pending/sending/sent/failed/cancelled/retry
    error = Column(Text)
    retry_count = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    entity_type = Column(String(40))
    entity_ref = Column(String(40))
    created_by = Column(Integer, ForeignKey("users.id"))


class SyncQueue(Base):
    """Offline-first sync engine state per record."""
    __tablename__ = "sync_queue"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(40), nullable=False)
    entity_uuid = Column(String(36), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), default="pending")   # pending/uploading/synced/failed/conflict/attention
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_attempt_at = Column(DateTime(timezone=True))
    retry_count = Column(Integer, default=0)
    error = Column(Text)
    server_version = Column(Integer)
    device_id = Column(String(60))
    __table_args__ = (Index("ix_sync_status", "status", "created_at"),)


class BackupRecord(Base):
    __tablename__ = "backups"
    id = Column(Integer, primary_key=True)
    file_path = Column(String(255), nullable=False)
    size_bytes = Column(Integer)
    version = Column(String(20))
    kind = Column(String(10), default="local")       # local/cloud
    status = Column(String(20), default="ok")        # ok/failed/restored_from
    created_at = Column(DateTime(timezone=True), default=utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    sha256 = Column(String(64))


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(40))
    entity_id = Column(Integer)
    file_path = Column(String(255))
    file_name = Column(String(150))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime(timezone=True), default=utcnow)
