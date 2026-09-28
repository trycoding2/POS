"""Parties: customers (Khata), suppliers, dasti temporary credit, and money accounts."""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.auth import utcnow


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    phone = Column(String(30), index=True)
    alt_phone = Column(String(30))
    address = Column(Text)
    notes = Column(Text)
    credit_limit = Column(Float, default=0)          # 0 = no limit configured
    opening_balance = Column(Float, default=0)       # + means customer owes us
    is_khata = Column(Boolean, default=False)        # has a saved Khata account
    whatsapp_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    company = Column(String(120))
    phone = Column(String(30), index=True)
    address = Column(Text)
    contact_person = Column(String(80))
    payment_terms = Column(String(120))
    notes = Column(Text)
    opening_balance = Column(Float, default=0)       # + means we owe supplier
    is_temporary = Column(Boolean, default=False)    # random/local seller marker
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))


class Dasti(Base):
    """Temporary short-term credit, separate from long-term Khata accounts."""
    __tablename__ = "dastis"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True, index=True)         # DST-YYYYMMDD-000001
    customer_id = Column(Integer, ForeignKey("customers.id"))  # optional link if later saved
    customer_name = Column(String(120))                        # optional free text
    phone = Column(String(30))
    amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0)                     # derived also from payments
    items_json = Column(Text)                                  # snapshot of items given
    created_at = Column(DateTime(timezone=True), default=utcnow)
    due_date = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    status = Column(String(20), default="pending")             # pending/partial/settled/cancelled
    notes = Column(Text)
    closed_at = Column(DateTime(timezone=True))


class DastiPayment(Base):
    __tablename__ = "dasti_payments"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True)
    dasti_id = Column(Integer, ForeignKey("dastis.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    paid_at = Column(DateTime(timezone=True), default=utcnow)
    received_by = Column(Integer, ForeignKey("users.id"))
    notes = Column(Text)


class Account(Base):
    """Cash drawer, bank accounts, Easypaisa/JazzCash wallets etc. Configurable by owner."""
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    name = Column(String(80), nullable=False, unique=True)
    type = Column(String(20), default="cash")   # cash/bank/wallet
    is_default_sale = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    opening_balance = Column(Float, default=0)


class AccountTransaction(Base):
    """Every money movement. Balance derived from history, never blindly overwritten."""
    __tablename__ = "account_transactions"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    direction = Column(String(10), nullable=False)     # in/out
    amount = Column(Float, nullable=False)
    reason = Column(String(60), nullable=False)        # sale/payment/expense/withdrawal/adjustment/opening
    entity_type = Column(String(40))
    entity_id = Column(Integer)
    entity_ref = Column(String(40))
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    occurred_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)
