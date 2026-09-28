"""First-run setup wizard (spec #62). Idempotent bootstrap: roles, permissions, walk-in
customer, default accounts, expense categories, units, and the owner account."""
import uuid as _uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.auth import User, Role, Permission, ALL_PERMISSIONS
from app.models.catalog import Unit
from app.models.parties import Customer, Account
from app.models.transactions import ExpenseCategory
from app.services import audit
from app.services.settings_service import ensure_defaults, set_setting

DEFAULT_ROLES = {
    "Owner": {"owner": True, "discount": 100},
    "Manager": {"perms": [p for p in ALL_PERMISSIONS if p != "withdrawal.create"], "discount": 20},
    "Cashier": {"perms": ["sale.create", "discount.apply", "customer.create", "khata.create",
                          "dasti.create", "payment.receive", "stock.view",
                          "customer.balance.view", "sale.return"], "discount": 5},
    "Stock Manager": {"perms": ["stock.adjust", "stock.view", "product.manage", "purchase.receive",
                               "data.export"], "discount": 0},
    "Purchase Manager": {"perms": ["purchase.create", "purchase.receive", "supplier.create",
                                   "cost.change", "order.manage", "supplier.balance.view",
                                   "stock.view", "data.export"], "discount": 0},
    "Accountant": {"perms": ["profit.view", "audit.view", "data.export", "expense.create",
                             "cash.manage", "customer.balance.view", "supplier.balance.view",
                             "payment.receive", "approval.grant"], "discount": 0},
}

DEFAULT_UNITS = [("Piece", False), ("Packet", False), ("Box", False), ("Carton", False),
                 ("Bottle", False), ("Dozen", False), ("kg", True), ("gram", True),
                 ("Litre", True), ("Millilitre", True)]

DEFAULT_EXPENSE_CATEGORIES = ["Rent", "Electricity", "Salary", "Transport", "Internet",
                              "Phone", "Maintenance", "Packaging", "Cleaning", "Miscellaneous"]


def is_initialized(db: Session) -> bool:
    return db.query(User).count() > 0


def seed_static(db: Session):
    """Permissions/roles/units/categories/accounts/walk-in — safe to call repeatedly."""
    ensure_defaults(db)
    for key in ALL_PERMISSIONS:
        if not db.query(Permission).filter(Permission.key == key).first():
            db.add(Permission(key=key, description=key.replace(".", " ")))
    for rname, cfg in DEFAULT_ROLES.items():
        role = db.query(Role).filter(Role.name == rname).first()
        if not role:
            role = Role(name=rname, is_owner_role=cfg.get("owner", False),
                        max_discount_percent=cfg["discount"])
            db.add(role)
            db.flush()
        if cfg.get("owner"):
            role.max_discount_percent = 100
        else:
            perms = db.query(Permission).filter(Permission.key.in_(cfg["perms"])).all()
            role.permissions = perms
    for uname, dec in DEFAULT_UNITS:
        if not db.query(Unit).filter(Unit.name == uname).first():
            db.add(Unit(name=uname, allows_decimal=dec))
    for cname in DEFAULT_EXPENSE_CATEGORIES:
        if not db.query(ExpenseCategory).filter(ExpenseCategory.name == cname).first():
            db.add(ExpenseCategory(name=cname))
    if not db.query(Customer).filter(Customer.name == "Walk-in Customer").first():
        db.add(Customer(uuid=str(_uuid.uuid4()), name="Walk-in Customer"))
    if not db.query(Account).filter(Account.name == "Main Cash").first():
        db.add(Account(uuid=str(_uuid.uuid4()), name="Main Cash", type="cash",
                       is_default_sale=True))
    for nm, tp in [("Bank Account", "bank"), ("Easypaisa", "wallet"), ("JazzCash", "wallet")]:
        if not db.query(Account).filter(Account.name == nm).first():
            db.add(Account(uuid=str(_uuid.uuid4()), name=nm, type=tp))
    db.commit()


def run_setup(db: Session, *, store_name: str, owner_username: str, owner_password: str,
              owner_full_name: str = "", currency_symbol: str | None = None,
              address: str = "", phone: str = "", whatsapp: str = "",
              opening_cash: float = 0, device_id: str = "POS-01") -> dict:
    """Create the owner + apply wizard answers. Refuses if already initialized."""
    from app.core.security import hash_password
    if is_initialized(db):
        raise HTTPException(400, "System is already initialized. Add users from Users & Employees.")
    if not store_name.strip() or not owner_username.strip() or len(owner_password) < 6:
        raise HTTPException(400,
            "Store name, owner username and a password of at least 6 characters are required.")
    seed_static(db)
    if owner_password.lower() in ("password", "123456", owner_username.lower()):
        raise HTTPException(400, "Password is too weak/common — choose a stronger one.")
    role = db.query(Role).filter(Role.name == "Owner").first()
    owner = User(username=owner_username.strip(), full_name=owner_full_name or owner_username,
                 password_hash=hash_password(owner_password), role_id=role.id)
    db.add(owner)
    db.flush()
    set_setting(db, "store.name", store_name.strip(), owner.id)
    set_setting(db, "store.address", address, owner.id)
    set_setting(db, "store.phone", phone, owner.id)
    set_setting(db, "store.whatsapp", whatsapp, owner.id)
    if currency_symbol:
        set_setting(db, "currency.symbol", currency_symbol, owner.id)
    main_cash = db.query(Account).filter(Account.name == "Main Cash").first()
    if opening_cash and main_cash:
        from app.services import ledger
        ledger.add_account_tx(db, main_cash.id, direction="in", amount=opening_cash,
                              reason="opening_balance", entity_type="account",
                              entity_id=main_cash.id, entity_ref="Main Cash",
                              user=owner, device_id=device_id, notes="Setup wizard opening cash")
    audit.log(db, user=owner, device_id=device_id, module="system", action="setup",
              entity="system", new_value={"store": store_name, "owner": owner_username},
              reason="Initial setup wizard completed")
    db.commit()
    return {"ok": True, "owner_id": owner.id}
