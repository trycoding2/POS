"""Inventory movement service — every stock change is recorded with prev/change/new + reason.

Stock current quantity is always traceable through movements (spec #50).
Call inside the caller's transaction; never commits itself.
"""
import uuid as _uuid
from sqlalchemy.orm import Session

from app.models.transactions import StockMovement
from app.services.refs import next_ref

MOVEMENT_TYPES = ["opening", "purchase", "sale", "customer_return", "supplier_return",
                  "damage", "expiry", "adjustment", "transfer_in", "transfer_out",
                  "free_item", "correction"]


def move(db: Session, product, *, qty_change: float, movement_type: str, user=None,
         device_id: str = "", reason: str = "", entity_type: str = "", entity_id=None,
         entity_ref: str = "", make_ref: bool = False) -> StockMovement:
    assert movement_type in MOVEMENT_TYPES, f"Unknown movement type {movement_type}"
    prev = float(product.stock_qty or 0)
    new = round(prev + qty_change, 6)
    ref = next_ref(db, "ADJ") if make_ref else None
    mv = StockMovement(
        uuid=str(_uuid.uuid4()), ref=ref, product_id=product.id,
        movement_type=movement_type, prev_qty=prev, change=qty_change, new_qty=new,
        reason=reason or movement_type, entity_type=entity_type or None,
        entity_id=entity_id, entity_ref=entity_ref or None,
        user_id=getattr(user, "id", None), device_id=device_id,
    )
    db.add(mv)
    product.stock_qty = new
    db.flush()
    return mv
