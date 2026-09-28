"""Business transactions: sales, purchases, orders, returns, expenses, withdrawals,
customer/supplier ledgers and inventory movements. Nothing is hard-deleted; void/cancel instead."""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.auth import utcnow


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)          # idempotent sync identity
    ref = Column(String(40), unique=True, index=True)           # SALE-YYYYMMDD-000001
    customer_id = Column(Integer, ForeignKey("customers.id"))   # NULL/1 = walk-in
    subtotal = Column(Float, default=0)
    discount_total = Column(Float, default=0)
    tax_total = Column(Float, default=0)
    grand_total = Column(Float, default=0)
    paid_total = Column(Float, default=0)
    change_given = Column(Float, default=0)
    credit_amount = Column(Float, default=0)                    # goes to Khata receivable
    status = Column(String(20), default="completed")  # completed/held/voided/partially_returned/returned
    void_reason = Column(Text)
    voided_by = Column(Integer, ForeignKey("users.id"))
    voided_at = Column(DateTime(timezone=True))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String(60))
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    notes = Column(Text)
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan", lazy="selectin")
    payments = relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan", lazy="selectin")


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)      # price at time of sale (snapshot)
    cost_price = Column(Float, default=0)           # COGS snapshot for profit calc
    discount = Column(Float, default=0)
    line_total = Column(Float, default=0)
    sale = relationship("Sale", back_populates="items")


class SalePayment(Base):
    """Split payments supported: multiple rows per sale."""
    __tablename__ = "sale_payments"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(30))   # cash/bank/wallet copied from account type
    sale = relationship("Sale", back_populates="payments")


class CustomerLedgerEntry(Base):
    """Customer balance derived from history: opening + credits - payments - returns +/- adjustments."""
    __tablename__ = "customer_ledger"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    entry_type = Column(String(30), nullable=False)  # opening/credit_sale/payment/return/adjustment/dasti_converted
    debit = Column(Float, default=0)     # increases what customer owes
    credit = Column(Float, default=0)    # reduces what customer owes
    entity_type = Column(String(40))
    entity_id = Column(Integer)
    entity_ref = Column(String(40))
    user_id = Column(Integer, ForeignKey("users.id"))
    occurred_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)


class SupplierLedgerEntry(Base):
    """Supplier payable: opening + purchases_on_credit - payments - returns +/- adjustments."""
    __tablename__ = "supplier_ledger"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    entry_type = Column(String(30), nullable=False)  # opening/purchase/purchase_payment/return/adjustment
    debit = Column(Float, default=0)     # reduces what we owe
    credit = Column(Float, default=0)    # increases what we owe
    entity_type = Column(String(40))
    entity_id = Column(Integer)
    entity_ref = Column(String(40))
    user_id = Column(Integer, ForeignKey("users.id"))
    occurred_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)


class StockMovement(Base):
    """Every stock change with previous/change/new quantity, reason, user, device, transaction."""
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True)                       # ADJ-... for manual adjustments
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    movement_type = Column(String(30), nullable=False)
    # opening/purchase/sale/customer_return/supplier_return/damage/expiry/adjustment/transfer/free_item/correction
    prev_qty = Column(Float, nullable=False)
    change = Column(Float, nullable=False)
    new_qty = Column(Float, nullable=False)
    reason = Column(Text)
    entity_type = Column(String(40))
    entity_id = Column(Integer)
    entity_ref = Column(String(40))
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    occurred_at = Column(DateTime(timezone=True), default=utcnow, index=True)


class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True, index=True)           # PUR-YYYYMMDD-000001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    invoice_no = Column(String(60))
    subtotal = Column(Float, default=0)
    discount_total = Column(Float, default=0)
    grand_total = Column(Float, default=0)
    paid_amount = Column(Float, default=0)
    due_amount = Column(Float, default=0)
    status = Column(String(25), default="received")
    # draft/ordered/partially_received/received/cancelled/returned
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String(60))
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    notes = Column(Text)
    attachment_path = Column(String(255))
    items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan", lazy="selectin")
    payments = relationship("PurchasePayment", back_populates="purchase", lazy="selectin")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id = Column(Integer, primary_key=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty_ordered = Column(Float, default=0)
    qty_received = Column(Float, default=0)
    qty_free = Column(Float, default=0)
    cost_price = Column(Float, nullable=False)
    discount = Column(Float, default=0)
    line_total = Column(Float, default=0)
    batch_no = Column(String(60))
    expiry_date = Column(DateTime(timezone=True))
    purchase = relationship("Purchase", back_populates="items")


class PurchasePayment(Base):
    __tablename__ = "purchase_payments"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True)                        # PAY-YYYYMMDD-000001
    purchase_id = Column(Integer, ForeignKey("purchases.id"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    paid_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)
    purchase = relationship("Purchase", back_populates="payments")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True, index=True)            # ORD-YYYYMMDD-000001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    status = Column(String(20), default="draft")  # draft/sent/ordered/partially_received/received/cancelled
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)
    items = relationship("PurchaseOrderItem", cascade="all, delete-orphan", lazy="selectin")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty_ordered = Column(Float, nullable=False)
    qty_received = Column(Float, default=0)
    expected_cost = Column(Float, default=0)


class Return(Base):
    """Customer or supplier returns referencing the original transaction. Originals never deleted."""
    __tablename__ = "returns"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True, index=True)            # RET-YYYYMMDD-000001
    kind = Column(String(20), nullable=False)                     # customer/supplier
    sale_id = Column(Integer, ForeignKey("sales.id"))
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    total_amount = Column(Float, default=0)
    refund_method = Column(String(30))   # cash/account_reduction/khata_reduction/supplier_credit/replacement
    account_id = Column(Integer, ForeignKey("accounts.id"))
    stock_condition = Column(String(30)) # good/damaged/expired
    restock = Column(Boolean, default=True)
    reason = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    items = relationship("ReturnItem", cascade="all, delete-orphan", lazy="selectin")


class ReturnItem(Base):
    __tablename__ = "return_items"
    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("returns.id", ondelete="CASCADE"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Float, nullable=False)
    unit_price = Column(Float, default=0)
    line_total = Column(Float, default=0)


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True, index=True)            # EXP-YYYYMMDD-000001
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=False)
    amount = Column(Float, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    description = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    occurred_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    attachment_path = Column(String(255))
    status = Column(String(20), default="approved")   # pending_approval/approved/rejected/cancelled
    cancelled_at = Column(DateTime(timezone=True))
    cancel_reason = Column(Text)


class OwnerWithdrawal(Base):
    """Separate from operating expenses — never classified as expense."""
    __tablename__ = "owner_withdrawals"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True)                        # WDR-YYYYMMDD-000001
    amount = Column(Float, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    occurred_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)


class CustomerPayment(Base):
    """Khata payment received from a saved customer."""
    __tablename__ = "customer_payments"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)
    ref = Column(String(40), unique=True)                        # PAY-YYYYMMDD-000001
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String(60))
    paid_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)
