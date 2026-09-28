"""Core entities: users, roles, permissions, devices, sessions."""
from datetime import datetime, timezone

from sqlalchemy import (Column, Integer, String, Boolean, DateTime, Float, Text,
                        Table, ForeignKey, UniqueConstraint)
from sqlalchemy.orm import relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


role_permission = Table(
    "role_permissions", Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

ALL_PERMISSIONS = [
    "sale.create", "sale.void", "sale.return", "discount.apply", "price.change",
    "cost.change", "customer.create", "supplier.create", "khata.create", "dasti.create",
    "payment.receive", "expense.create", "stock.adjust", "stock.view", "product.manage",
    "purchase.create", "purchase.receive", "order.manage", "profit.view",
    "supplier.balance.view", "customer.balance.view", "settings.edit", "users.manage",
    "data.export", "audit.view", "notification.send", "backup.manage", "approval.grant",
    "cash.manage", "withdrawal.create",
]


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(60), unique=True, nullable=False)
    is_owner_role = Column(Boolean, default=False)   # owner role has every permission
    max_discount_percent = Column(Float, default=0.0)
    requires_approval_above = Column(Float, default=0)  # 0 = no approval threshold
    permissions = relationship("Permission", secondary=role_permission, lazy="joined")

    def has(self, perm: str) -> bool:
        if self.is_owner_role:
            return True
        return any(p.key == perm for p in self.permissions)


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    key = Column(String(60), unique=True, nullable=False)
    description = Column(String(200))


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(100))
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"))
    is_active = Column(Boolean, default=True)
    phone = Column(String(30))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    role = relationship("Role", lazy="joined")

    def role_has_permission(self, perm: str) -> bool:
        return bool(self.role and self.role.has(perm))


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    device_id = Column(String(60), unique=True, nullable=False)
    name = Column(String(80))
    user_id = Column(Integer, ForeignKey("users.id"))
    authorized = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True))
    last_activity_at = Column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    token = Column(String(64), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String(60))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Approval(Base):
    """Sensitive actions can require a second-person approval (configurable thresholds)."""
    __tablename__ = "approvals"
    id = Column(Integer, primary_key=True)
    action = Column(String(60), nullable=False)      # e.g. sale.void, expense.create
    entity_type = Column(String(40))
    payload_json = Column(Text)                      # request details
    amount = Column(Float, default=0)
    requested_by = Column(Integer, ForeignKey("users.id"))
    requested_at = Column(DateTime(timezone=True), default=utcnow)
    status = Column(String(20), default="pending")   # pending/approved/rejected
    decided_by = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime(timezone=True))
    reason = Column(Text)
