"""Catalog + inventory endpoints."""
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.transactions import Sale
from app.models.catalog import Product, Category, Brand, Unit, PriceHistory
from app.services import audit, inventory, reports
from app.services.settings_service import get_num

router = APIRouter(prefix="/api", tags=["catalog"])


class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    sku: str | None = None
    barcode: str | None = None
    category_id: int | None = None
    brand_id: int | None = None
    unit_id: int | None = None
    cost_price: float = 0
    retail_price: float = 0
    wholesale_price: float | None = None
    special_price: float | None = None
    min_stock: float = 0
    max_stock: float | None = None
    reorder_level: float | None = None
    default_supplier_id: int | None = None
    track_expiry: bool = False
    track_batch: bool = False
    opening_stock: float = 0
    notes: str = ""


def product_out(db: Session, p: Product) -> dict:
    margin = None
    if p.retail_price and p.cost_price is not None:
        margin = round((p.retail_price - p.cost_price) / p.retail_price * 100, 1) \
            if p.retail_price else None
    return {"id": p.id, "uuid": p.uuid, "name": p.name, "sku": p.sku, "barcode": p.barcode,
            "category": p.category.name if p.category else None,
            "category_id": p.category_id,
            "brand": p.brand.name if p.brand else None, "brand_id": p.brand_id,
            "unit": p.unit.name if p.unit else "Piece", "unit_id": p.unit_id,
            "cost_price": p.cost_price, "retail_price": p.retail_price,
            "wholesale_price": p.wholesale_price, "special_price": p.special_price,
            "stock_qty": p.stock_qty, "min_stock": p.min_stock, "max_stock": p.max_stock,
            "margin_percent": margin, "is_active": p.is_active,
            "track_expiry": p.track_expiry, "track_batch": p.track_batch,
            "default_supplier_id": p.default_supplier_id, "notes": p.notes}


@router.get("/products/search")
def search_products(q: str = Query("", description="name/sku/barcode/brand/category"),
                    limit: int = 25, include_inactive: bool = False,
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Live search-as-you-type (spec #6). Barcode exact match first. Indexed LIKE for speed."""
    term = f"%{q.strip()}%"
    stmt = db.query(Product)
    if not include_inactive:
        stmt = stmt.filter(Product.is_active == True)  # noqa: E712
    if q.strip():
        conds = [Product.name.ilike(term), Product.sku.ilike(term), Product.barcode == q.strip()]
        stmt = stmt.outerjoin(Category, Product.category_id == Category.id) \
                    .outerjoin(Brand, Product.brand_id == Brand.id)
        conds += [Category.name.ilike(term), Brand.name.ilike(term)]
        stmt = stmt.filter(or_(*conds))
    prods = stmt.order_by(Product.name).limit(limit).all()
    return [product_out(db, p) for p in prods]


@router.get("/products/{pid}")
def get_product(pid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found.")
    out = product_out(db, p)
    out["price_history"] = [{"field": h.field, "old": h.old_value, "new": h.new_value,
                             "at": h.changed_at.isoformat() if h.changed_at else None,
                             "by": h.changed_by, "reason": h.reason}
                            for h in db.query(PriceHistory).filter(
                                PriceHistory.product_id == pid).order_by(
                                PriceHistory.id.desc()).limit(50).all()]
    return out


@router.post("/products")
def create_product(body: ProductIn, db: Session = Depends(get_db),
                   user=Depends(require_permission("product.manage"))):
    data = body.model_dump()
    opening = data.pop("opening_stock", 0)
    if db.query(Product).filter(Product.name == data["name"]).first():
        raise HTTPException(400, f"A product named '{data['name']}' already exists.")
    p = Product(uuid=str(_uuid.uuid4()), **data, stock_qty=0)
    db.add(p)
    db.flush()
    if opening:
        inventory.move(db, p, qty_change=opening, movement_type="opening", user=user,
                       device_id=user._device_id, reason="Opening stock")
    audit.log(db, user=user, module="inventory", action="create", entity="product",
              entity_id=p.id, entity_ref=p.name, new_value={"retail": p.retail_price})
    db.commit()
    return product_out(db, p)


class ProductUpdate(BaseModel):
    name: str | None = None
    barcode: str | None = None
    sku: str | None = None
    retail_price: float | None = None
    cost_price: float | None = None
    wholesale_price: float | None = None
    special_price: float | None = None
    min_stock: float | None = None
    max_stock: float | None = None
    category_id: int | None = None
    brand_id: int | None = None
    unit_id: int | None = None
    default_supplier_id: int | None = None
    is_active: bool | None = None
    notes: str | None = None
    reason: str = ""      # required for price changes


PRICE_FIELDS = {"retail_price": "retail", "cost_price": "cost",
                "wholesale_price": "wholesale", "special_price": "special"}


@router.put("/products/{pid}")
def update_product(pid: int, body: ProductUpdate, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found.")
    changes = {}
    prev = {}
    for k, v in body.model_dump(exclude_none=True, exclude={"reason"}).items():
        old = getattr(p, k)
        if old == v:
            continue
        if k in PRICE_FIELDS:
            perm = "price.change" if k != "cost_price" else "cost.change"
            if not user.role_has_permission(perm):
                raise HTTPException(403, f"You do not have permission to change {k}.")
            if not body.reason.strip():
                raise HTTPException(400, "A reason is required when changing prices.")
            db.add(PriceHistory(product_id=p.id, field=PRICE_FIELDS[k], old_value=old,
                                new_value=v, reason=body.reason, changed_by=user.id))
        setattr(p, k, v)
        prev[k] = old
        changes[k] = v
    if changes:
        audit.log(db, user=user, module="inventory", action="update", entity="product",
                  entity_id=p.id, entity_ref=p.name, prev_value=prev, new_value=changes,
                  reason=body.reason)
        db.commit()
    return product_out(db, p)


@router.post("/products/{pid}/adjust-stock")
def adjust_stock(pid: int, body: dict, db: Session = Depends(get_db),
                 user=Depends(require_permission("stock.adjust"))):
    from app.services.operations import adjust_stock as adj
    mv = adj(db, user=user, device_id=user._device_id, product_id=pid,
             new_qty=body.get("new_qty"), delta=body.get("delta"),
             movement_type=body.get("movement_type", "adjustment"),
             reason=body.get("reason", ""))
    return {"ref": mv.ref, "prev": mv.prev_qty, "change": mv.change, "new": mv.new_qty}


@router.get("/products/{pid}/timeline")
def product_timeline(pid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.models.auth import User as UserModel
    hist = []
    for h in (db.query(PriceHistory).filter(PriceHistory.product_id == pid)
              .order_by(PriceHistory.id).all()):
        u = db.get(UserModel, h.changed_by) if h.changed_by else None
        hist.append({"field": h.field, "old_price": h.old_value, "new_price": h.new_value,
                     "changed_by": (u.full_name or u.username) if u else None,
                     "reason": h.reason,
                     "at": h.changed_at.isoformat() if h.changed_at else None})
    return {"movements": reports.product_timeline(db, pid),
            "price_history": hist,
            "traceability": reports.stock_traceability_check(db, pid)}


@router.post("/pos/hold/{hid}/resume")
def resume_held(hid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Return held cart contents to the POS; the hold record stays for the audit trail."""
    s = db.query(Sale).filter(Sale.id == hid, Sale.status == "held").first()
    if not s:
        raise HTTPException(404, "Held sale not found (already resumed or completed?).")
    import json as _json
    cart = _json.loads(s.notes) if s.notes and s.notes.strip().startswith("[") else []
    audit.log(db, user=user, device_id=user._device_id, module="pos", action="resume",
              entity="sale", entity_id=s.id, entity_ref=s.ref)
    db.commit()
    return {"id": s.id, "ref": s.ref, "cart": cart}


# ---- categories / brands / units -------------------------------------------

@router.get("/catalog/meta")
def catalog_meta(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {
        "categories": [{"id": c.id, "name": c.name} for c in db.query(Category).all()],
        "brands": [{"id": b.id, "name": b.name} for b in db.query(Brand).all()],
        "units": [{"id": u.id, "name": u.name, "allows_decimal": u.allows_decimal}
                  for u in db.query(Unit).all()],
    }


class NameIn(BaseModel):
    name: str = Field(min_length=1)


@router.post("/catalog/categories")
def add_category(body: NameIn, db: Session = Depends(get_db),
                 user=Depends(require_permission("product.manage"))):
    if db.query(Category).filter(Category.name == body.name).first():
        raise HTTPException(400, "Category already exists.")
    c = Category(name=body.name)
    db.add(c)
    audit.log(db, user=user, module="settings", action="create", entity="category",
              entity_ref=body.name)
    db.commit()
    return {"id": c.id, "name": c.name}


@router.post("/catalog/brands")
def add_brand(body: NameIn, db: Session = Depends(get_db),
              user=Depends(require_permission("product.manage"))):
    if db.query(Brand).filter(Brand.name == body.name).first():
        raise HTTPException(400, "Brand already exists.")
    b = Brand(name=body.name)
    db.add(b)
    audit.log(db, user=user, module="settings", action="create", entity="brand",
              entity_ref=body.name)
    db.commit()
    return {"id": b.id, "name": b.name}


@router.post("/catalog/units")
def add_unit(body: dict, db: Session = Depends(get_db),
             user=Depends(require_permission("product.manage"))):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Unit name required.")
    if db.query(Unit).filter(Unit.name == name).first():
        raise HTTPException(400, "Unit already exists.")
    u = Unit(name=name, allows_decimal=bool(body.get("allows_decimal")))
    db.add(u)
    audit.log(db, user=user, module="settings", action="create", entity="unit", entity_ref=name)
    db.commit()
    return {"id": u.id, "name": u.name}


@router.get("/inventory/dashboard")
def inventory_dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    snap = reports.inventory_snapshot(db)
    # fast/slow moving from last-30-day sales
    from datetime import datetime, timezone, timedelta
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.query(Product.name, func.sum(reports.SaleItem.qty)) \
             .join(reports.SaleItem, reports.SaleItem.product_id == Product.id) \
             .join(reports.Sale, reports.Sale.id == reports.SaleItem.sale_id) \
             .filter(reports.Sale.created_at >= since, reports.Sale.status != "voided") \
             .group_by(Product.id).all()
    sold = {n: float(q or 0) for n, q in rows}
    fast = sorted(sold.items(), key=lambda x: -x[1])[:10]
    allnames = {p.name: float(p.stock_qty or 0) for p in db.query(Product).filter(
        Product.is_active == True).all()}  # noqa: E712
    slow = sorted([(n, s) for n, s in allnames.items() if sold.get(n, 0) <= 0],
                  key=lambda x: -x[1])[:10]
    snap["fast_moving"] = [{"name": n, "qty_30d": q} for n, q in fast]
    snap["slow_or_dead_stock"] = [{"name": n, "stock": s} for n, s in slow]
    return snap
