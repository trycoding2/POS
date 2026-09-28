"""Import/Export (spec #61). CSV with validation; imports never silently corrupt data —
rows are validated, errors reported per-row, and everything happens in one transaction."""
import csv
import io
import uuid as _uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.catalog import Product, Category, Unit, Brand
from app.models.parties import Customer, Supplier
from app.services import audit
from app.services.settings_service import get_bool


def export_products_csv(db: Session) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "sku", "barcode", "category", "brand", "unit",
                "cost_price", "retail_price", "wholesale_price", "stock_qty", "min_stock"])
    for p in db.query(Product).all():
        w.writerow([p.name, p.sku or "", p.barcode or "",
                    p.category.name if p.category else "", p.brand.name if p.brand else "",
                    p.unit.name if p.unit else "", p.cost_price, p.retail_price,
                    p.wholesale_price or "", p.stock_qty, p.min_stock])
    return buf.getvalue()


def export_customers_csv(db: Session) -> str:
    from app.services import ledger
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "alt_phone", "address", "credit_limit",
                "opening_balance", "is_khata", "current_balance"])
    for c in db.query(Customer).all():
        w.writerow([c.name, c.phone or "", c.alt_phone or "", (c.address or "").replace("\n", " "),
                    c.credit_limit or 0, c.opening_balance or 0, int(c.is_khata or False),
                    ledger.customer_balance(db, c.id)])
    return buf.getvalue()


def export_suppliers_csv(db: Session) -> str:
    from app.services import ledger
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "company", "phone", "address", "contact_person",
                "payment_terms", "opening_balance", "current_payable"])
    for s in db.query(Supplier).all():
        w.writerow([s.name, s.company or "", s.phone or "", (s.address or "").replace("\n", " "),
                    s.contact_person or "", s.payment_terms or "", s.opening_balance or 0,
                    ledger.supplier_balance(db, s.id)])
    return buf.getvalue()


def _get_or_create(db: Session, model, name):
    if not name:
        return None
    row = db.query(model).filter(model.name == name).first()
    if not row:
        row = model(name=name)
        db.add(row)
        db.flush()
    return row


def import_products_csv(db: Session, content: str, *, user, device_id: str,
                        update_existing: bool = True) -> dict:
    """Validated import. Either all valid rows commit or nothing does."""
    try:
        reader = csv.DictReader(io.StringIO(content))
        required = {"name", "retail_price"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise HTTPException(400,
                "CSV must have at least columns: name, retail_price "
                "(optional: sku, barcode, category, brand, unit, cost_price, stock_qty, min_stock)")
        errors, created, updated = [], 0, 0
        seen_skus = set()
        for i, row in enumerate(reader, start=2):   # line numbers incl header
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Line {i}: empty product name"); continue
            try:
                rp = float(row.get("retail_price") or 0)
            except ValueError:
                errors.append(f"Line {i}: retail_price not a number"); continue
            if rp < 0:
                errors.append(f"Line {i}: retail_price cannot be negative"); continue
            sku = (row.get("sku") or "").strip() or None
            if sku:
                if sku in seen_skus:
                    errors.append(f"Line {i}: duplicate SKU '{sku}' inside file"); continue
                seen_skus.add(sku)
            existing = db.query(Product).filter(
                (Product.name == name) | ((Product.sku != None) & (Product.sku == sku))  # noqa: E711
            ).first() if sku else db.query(Product).filter(Product.name == name).first()
            if existing and not update_existing:
                errors.append(f"Line {i}: '{name}' already exists (update disabled)"); continue
            cat = _get_or_create(db, Category, (row.get("category") or "").strip())
            br = _get_or_create(db, Brand, (row.get("brand") or "").strip())
            un = _get_or_create(db, Unit, (row.get("unit") or "").strip() or "Piece")
            if un and un.name == "Piece" and not db.query(Unit).filter(Unit.name == "Piece").first():
                pass
            vals = dict(cost_price=float(row.get("cost_price") or 0 or 0) if row.get("cost_price") else None,
                        retail_price=rp,
                        wholesale_price=(float(row["wholesale_price"]) if row.get("wholesale_price") else None),
                        min_stock=float(row.get("min_stock") or 0),
                        barcode=(row.get("barcode") or "").strip() or None)
            vals = {k: v for k, v in vals.items() if v is not None}
            if existing:
                old = {k: getattr(existing, k) for k in vals}
                for k, v in vals.items():
                    setattr(existing, k, v)
                if cat: existing.category_id = cat.id
                if br: existing.brand_id = br.id
                if un: existing.unit_id = un.id
                updated += 1
                audit.log(db, user=user, device_id=device_id, module="inventory",
                          action="import_update", entity="product", entity_id=existing.id,
                          entity_ref=existing.name, prev_value=old, new_value=vals)
            else:
                opening = float(row.get("stock_qty") or 0)
                p = Product(uuid=str(_uuid.uuid4()), name=name, sku=sku,
                            category_id=cat.id if cat else None,
                            brand_id=br.id if br else None,
                            unit_id=un.id if un else None, **vals, stock_qty=0)
                db.add(p)
                db.flush()
                if opening > 0:
                    from app.services import inventory
                    inventory.move(db, p, qty_change=opening, movement_type="opening",
                                   user=user, device_id=device_id, reason="CSV import opening stock")
                created += 1
                audit.log(db, user=user, device_id=device_id, module="inventory",
                          action="import_create", entity="product", entity_id=p.id,
                          entity_ref=p.name, new_value={"retail": rp, "opening": opening})
        if errors:
            db.rollback()
            return {"ok": False, "created": 0, "updated": 0, "errors": errors,
                    "message": "Import aborted — no rows were saved so your data stays consistent."}
        db.commit()
        return {"ok": True, "created": created, "updated": updated, "errors": []}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def import_customers_csv(db: Session, content: str, *, user, device_id: str) -> dict:
    try:
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise HTTPException(400, "CSV must include a 'name' column.")
        errors, created = [], 0
        for i, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Line {i}: missing name"); continue
            if db.query(Customer).filter(Customer.name == name).first():
                errors.append(f"Line {i}: customer '{name}' already exists"); continue
            try:
                ob = float(row.get("opening_balance") or 0)
            except ValueError:
                errors.append(f"Line {i}: opening_balance not numeric"); continue
            c = Customer(uuid=str(_uuid.uuid4()), name=name, phone=(row.get("phone") or "").strip(),
                         address=(row.get("address") or "").strip(), opening_balance=ob,
                         credit_limit=float(row.get("credit_limit") or 0),
                         is_khata=str(row.get("is_khata") or "") in ("1", "true", "True"),
                         created_by=user.id)
            db.add(c)
            if ob:
                from app.services import ledger
                ledger.add_customer_entry(db, c.id, entry_type="opening", debit=ob,
                                          user=user, notes="CSV import")
            created += 1
        if errors:
            db.rollback()
            return {"ok": False, "created": 0, "errors": errors,
                    "message": "Import aborted — nothing was saved."}
        audit.log(db, user=user, device_id=device_id, module="customers", action="import",
                  entity="customer", new_value={"created": created})
        db.commit()
        return {"ok": True, "created": created, "errors": []}
    except HTTPException:
        db.rollback()
        raise
