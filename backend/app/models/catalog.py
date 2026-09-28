"""Catalog: categories, units, brands, products, price history."""
from sqlalchemy import (Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.auth import utcnow


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)


class Unit(Base):
    __tablename__ = "units"
    id = Column(Integer, primary_key=True)
    name = Column(String(40), unique=True, nullable=False)   # Piece, kg, L, Dozen...
    allows_decimal = Column(Boolean, default=False)


class Brand(Base):
    __tablename__ = "brands"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, index=True)          # sync-safe identity
    name = Column(String(150), nullable=False, index=True)
    sku = Column(String(60), unique=True, index=True)
    barcode = Column(String(64), index=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    brand_id = Column(Integer, ForeignKey("brands.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    cost_price = Column(Float, default=0)
    retail_price = Column(Float, default=0)
    wholesale_price = Column(Float)
    special_price = Column(Float)
    stock_qty = Column(Float, default=0)          # current quantity (traceable via movements)
    min_stock = Column(Float, default=0)
    max_stock = Column(Float)
    reorder_level = Column(Float)
    default_supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    track_expiry = Column(Boolean, default=False)
    track_batch = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    category = relationship("Category", lazy="joined")
    brand = relationship("Brand", lazy="joined")
    unit = relationship("Unit", lazy="joined")


class PriceHistory(Base):
    """Prices are never silently overwritten; every change keeps old/new/user/reason."""
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    field = Column(String(20), nullable=False)     # cost/retail/wholesale/special
    old_value = Column(Float)
    new_value = Column(Float)
    reason = Column(Text)
    changed_by = Column(Integer, ForeignKey("users.id"))
    changed_at = Column(DateTime(timezone=True), default=utcnow)


class Batch(Base):
    """Batch/expiry tracking for karyana goods (milk, biscuits, medicine-like items)."""
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    batch_no = Column(String(60))
    expiry_date = Column(DateTime(timezone=True))
    qty_in = Column(Float, default=0)
    qty_remaining = Column(Float, default=0)
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
