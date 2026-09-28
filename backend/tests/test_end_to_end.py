"""End-to-end acceptance tests mirroring spec #63 (sample business flow) and
spec #73/#74 requirements: POS, Khata, Dasti, purchases, supplier payment,
damage adjustment, returns, voids, audit trail, offline sync, permissions."""
import pytest


def _product(client, hdr, name, cost, retail, barcode=None, min_stock=0):
    r = client.post("/api/products", headers=hdr, json={
        "name": name, "cost_price": cost, "retail_price": retail,
        "barcode": barcode, "min_stock": min_stock, "opening_stock": 0})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ basics --
def test_setup_wizard_and_login(client, owner):
    """Setup wizard already run by the owner fixture; verify state + bad login."""
    r = client.get("/api/auth/initialized")
    assert r.status_code == 200 and r.json()["initialized"] is True
    r = client.post("/api/auth/login", json={"username": "owner",
                                             "password": "wrong-password"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"username": "owner",
                                             "password": "owner-pass-123"})
    assert r.status_code == 200 and r.json()["settings"]["store.name"] == "Test Karyana Store"


def test_unauthenticated_blocked(client):
    assert client.get("/api/products/search?q=a").status_code == 401


def test_system_info(client, owner):
    r = client.get("/api/system/info", headers=owner)
    assert r.status_code == 200
    assert r.json()["offline_ready"] is True


# ------------------------------------------------- spec #63 business flow --
FLOW = {}


def test_full_business_flow(client, owner, cashier, accounts):
    """Spec #63 steps 1-9 executed as one deterministic sequence."""
    cash = accounts["Main Cash"]

    # Step 1: product
    p = _product(client, owner, "Surf Excel 1kg", 350, 400,
                 barcode="8961234567890", min_stock=10)
    FLOW["prod"] = p["id"]
    assert p["stock_qty"] == 0

    # Step 2: supplier purchase Rs.7,000 paid 3,000 due 4,000; stock +20
    r = client.post("/api/suppliers", headers=owner, json={"name": "ABC Distributors",
                                                           "phone": "03001112222"})
    assert r.status_code == 200, r.text
    sup = r.json(); FLOW["supplier"] = sup["id"]
    r = client.post("/api/purchases", headers=owner, json={
        "supplier_id": sup["id"],
        "items": [{"product_id": p["id"], "qty": 20, "cost_price": 350}],
        "paid_amount": 3000, "account_id": cash, "invoice_no": "INV-77"})
    assert r.status_code == 200, r.text
    pur = r.json(); FLOW["purchase"] = pur
    assert pur["grand_total"] == 7000 and pur["due_amount"] == 4000
    assert client.get(f"/api/products/{p['id']}", headers=owner).json()["stock_qty"] == 20
    assert abs(sup_payable(client, owner, sup["id"]) - 4000) < 0.01

    # Step 3: walk-in cash sale 2 @ 400 = 800, tendered 1000 -> change 200
    r = client.post("/api/pos/sales", headers=owner, json={
        "items": [{"product_id": p["id"], "qty": 2}],
        "payments": [{"account_id": cash, "amount": 800, "tendered": 1000}]})
    assert r.status_code == 200, r.text
    sale = r.json(); FLOW["sale_cash"] = sale
    assert sale["grand_total"] == 800 and sale["credit_amount"] == 0
    assert sale["change_given"] == 200
    assert client.get(f"/api/products/{p['id']}", headers=owner).json()["stock_qty"] == 18

    # Step 4: Ahmed khata credit sale 3 @ 400 = 1200 by cashier on POS-02
    r = client.post("/api/customers", headers=owner,
                    json={"name": "Ahmed Khan", "phone": "03001234567",
                          "credit_limit": 20000})
    assert r.status_code == 200, r.text
    cust = r.json(); FLOW["ahmed"] = cust["id"]
    r = client.post("/api/pos/sales", headers=cashier, json={
        "items": [{"product_id": p["id"], "qty": 3}],
        "customer_id": cust["id"], "credit_mode": "khata"})
    assert r.status_code == 200, r.text
    s_khata = r.json(); FLOW["sale_khata"] = s_khata
    assert s_khata["credit_amount"] == 1200
    assert s_khata["cashier"] == "Bilal" and s_khata["device"] == "POS-02"
    bal = client.get(f"/api/customers/{cust['id']}", headers=owner).json()["balance"]
    assert abs(bal - 1200) < 0.01
    assert client.get(f"/api/products/{p['id']}", headers=owner).json()["stock_qty"] == 15

    # Step 5: temporary customer dasti Rs.400 due tomorrow
    r = client.post("/api/pos/sales", headers=cashier, json={
        "items": [{"product_id": p["id"], "qty": 1}],
        "credit_mode": "dasti",
        "dasti": {"customer_name": "Shabbi (temporary)", "phone": "",
                  "notes": "1 packet dasti"}})
    assert r.status_code == 200, r.text
    assert r.json()["credit_amount"] == 400
    dst = [d for d in client.get("/api/dastis?status=pending", headers=cashier).json()
           if d["customer_name"] == "Shabbi (temporary)"]
    assert len(dst) == 1 and dst[0]["amount"] == 400
    FLOW["dasti"] = dst[0]
    assert client.get(f"/api/products/{p['id']}", headers=owner).json()["stock_qty"] == 14

    # Step 6: Ahmed pays 700 -> balance 500
    r = client.post("/api/pos/customer-payments", headers=owner, json={
        "customer_id": FLOW["ahmed"], "amount": 700, "account_id": cash})
    assert r.status_code == 200, r.text
    assert abs(r.json()["new_balance"] - 500) < 0.01

    # Step 7: one packet damaged -> stock 13
    r = client.post(f"/api/products/{p['id']}/adjust-stock", headers=owner,
                    json={"delta": -1, "movement_type": "damage",
                          "reason": "Packet torn in storage"})
    assert r.status_code == 200, r.text
    assert r.json()["prev"] == 14 and r.json()["new"] == 13
    tl = client.get(f"/api/products/{p['id']}/timeline", headers=owner).json()
    assert any(m["type"] == "damage" for m in tl["movements"])

    # Step 8: supplier receives 2000 -> payable 2000 remaining
    r = client.post("/api/supplier-payments", headers=owner, json={
        "supplier_id": FLOW["supplier"], "amount": 2000, "account_id": cash,
        "purchase_id": FLOW["purchase"]["id"]})
    assert r.status_code == 200, r.text
    assert abs(sup_payable(client, owner, FLOW["supplier"]) - 2000) < 0.01

    # Step 9: dashboard reconstructs the story
    d = client.get("/api/reports/dashboard", headers=owner).json()
    assert d["today_sales"] >= 2400          # 800 + 1200 + 400
    assert d["receivables"] >= 500
    assert d["payables"] >= 2000
    assert d["dasti_outstanding"] >= 400
    assert "low_stock_count" in d
    inv = client.get("/api/reports/inventory", headers=owner).json()
    assert any(x["id"] == FLOW["prod"] for x in inv["products"])

    # Spec #64 audit trail: every step left a trace
    acts = client.get("/api/activity?limit=300", headers=owner).json()
    mods = {(a["module"], a["action"]) for a in acts}
    for need in [("inventory", "create"), ("purchases", "create"), ("pos", "create"),
                 ("auth", "login")]:
        assert need in mods, (need, sorted(mods))
    modules = {m for m, _ in mods}
    assert {"pos", "purchases", "suppliers", "inventory", "auth"} <= modules, sorted(modules)
    v = client.get("/api/audit/verify", headers=owner).json()
    assert v["ok"] is True


def sup_payable(client, hdr, sid):
    r = client.get(f"/api/suppliers/{sid}", headers=hdr)
    assert r.status_code == 200
    return r.json()["payable"]


# ------------------------------------------------------------------ other --
def test_void_keeps_original(client, owner):
    r = client.post("/api/pos/sales", headers=owner, json={
        "items": [{"product_id": FLOW["prod"], "qty": 1}],
        "payments": []})  # unpaid full -> credit to walk-in? should fail cleanly
    # walk-in with no payment & no credit mode must be rejected (error clarity, spec #58)
    assert r.status_code == 400
    # make a proper cash sale then void it
    r = client.post("/api/pos/sales", headers=owner, json={
        "items": [{"product_id": FLOW["prod"], "qty": 1}], "payments": [] ,
        "credit_mode": "khata", "customer_id": FLOW["ahmed"]})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r = client.post(f"/api/pos/sales/{sid}/void", headers=owner,
                    json={"reason": "Duplicate entry"})
    assert r.status_code == 200
    got = client.get(f"/api/pos/sales/{sid}", headers=owner).json()
    assert got["status"] == "voided" and got["void_reason"] == "Duplicate entry"
    # stock restored
    st = client.get(f"/api/products/{FLOW['prod']}", headers=owner).json()["stock_qty"]
    assert st == 13


def test_return_flow(client, owner, accounts, flow):
    pid = flow["prod"]
    before = client.get(f"/api/products/{pid}", headers=owner).json()["stock_qty"]
    price = client.get(f"/api/products/{pid}", headers=owner).json()["retail_price"]
    r = client.post("/api/pos/sales", headers=owner, json={
        "items": [{"product_id": pid, "qty": 2}],
        "payments": [{"account_id": accounts["Main Cash"], "amount": round(2 * price, 2)}]})
    assert r.status_code == 200, r.text
    sale = r.json()
    item_id = sale["items"][0]["id"]
    r = client.post(f"/api/pos/sales/{sale['id']}/return", headers=owner, json={
        "items": [{"sale_item_id": item_id, "qty": 1}],
        "reason": "Customer changed mind", "account_id": accounts["Main Cash"]})
    assert r.status_code == 200, r.text
    after = client.get(f"/api/products/{FLOW['prod']}", headers=owner).json()["stock_qty"]
    # before was X, sale made X-2, return adds 1 back => X-1
    assert after == before - 1


def test_split_payment_and_partial_khata(client, owner, accounts, flow):
    price = client.get(f"/api/products/{flow['prod']}", headers=owner).json()["retail_price"]
    total = round(5 * price, 2)
    r = client.post("/api/pos/sales", headers=owner, json={
        "items": [{"product_id": flow["prod"], "qty": 5}],
        "customer_id": flow["ahmed"],
        "payments": [{"account_id": accounts["Main Cash"], "amount": 1000},
                     {"account_id": accounts["Easypaisa"], "amount": 500}],
        "credit_mode": "khata"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert abs(s["paid_total"] - 1500) < 0.01
    assert abs(s["credit_amount"] - (total - 1500)) < 0.01


def test_permissions_block_cashier(client, cashier):
    assert client.get("/api/audit/verify", headers=cashier).status_code == 403
    assert client.post("/api/expenses", headers=cashier, json={}).status_code in (403, 422)
    assert client.get("/api/users", headers=cashier).status_code == 403


def test_temporary_supplier_purchase(client, owner, accounts):
    """Spec #19: random seller without permanent supplier record."""
    p = _product(client, owner, "Sugar 1kg", 120, 150)
    r = client.post("/api/purchases", headers=owner, json={
        "supplier_name": "Bazaar boy (unknown)",
        "items": [{"product_id": p["id"], "qty": 10, "cost_price": 120}],
        "paid_amount": 1200, "account_id": accounts["Main Cash"]})
    assert r.status_code == 200, r.text
    assert r.json()["due_amount"] == 0
    temps = client.get("/api/suppliers?filter=temporary", headers=owner).json()
    assert any(s["name"] == "Bazaar boy (unknown)" for s in temps)


def test_expense_and_withdrawal_separated(client, owner, accounts):
    cats = client.get("/api/expense-categories", headers=owner).json()
    rent = next(c["id"] for c in cats if c["name"] == "Rent")
    r = client.post("/api/expenses", headers=owner, json={
        "category_id": rent, "amount": 500, "account_id": accounts["Main Cash"],
        "description": "Shop rent share"})
    assert r.status_code == 200, r.text
    r = client.post("/api/withdrawals", headers=owner, json={
        "amount": 1000, "account_id": accounts["Main Cash"], "notes": "Personal"})
    assert r.status_code == 200, r.text
    prof = client.get("/api/reports/profit?start=&end=", headers=owner).json()
    assert "expenses" in prof and "net_profit" in prof


def test_orders_receive_partial(client, owner, accounts, flow):
    r = client.post("/api/orders", headers=owner, json={
        "supplier_id": flow["supplier"], "send": True,
        "items": [{"product_id": flow["prod"], "qty_ordered": 10}]})
    assert r.status_code == 200, r.text
    order = r.json()
    oid = order["items"][0]["id"]
    r = client.post(f"/api/orders/{order['id']}/receive", headers=owner, json={
        "receipts": [{"order_item_id": oid, "qty": 8}],
        "paid_amount": 0, "account_id": None})
    assert r.status_code == 200, r.text
    o = client.get("/api/orders", headers=owner).json()
    rec = next(x for x in o if x["id"] == order["id"])
    assert rec["items"][0]["qty_received"] == 8
    assert rec["items"][0]["remaining"] == 2


def test_receipt_txt_pdf(client, owner, flow):
    sid = flow["sale_cash"]["id"]
    t = client.get(f"/api/pos/sales/{sid}/receipt.txt", headers=owner)
    assert t.status_code == 200 and "Test Karyana Store" in t.text
    pdf = client.get(f"/api/pos/sales/{sid}/receipt.pdf", headers=owner)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_hold_resume(client, owner):
    r = client.post("/api/pos/hold", headers=owner, json={
        "cart": [{"name": "Surf Excel 1kg", "qty": 2, "price": 420}], "notes": "Table 3"})
    assert r.status_code == 200, r.text
    held = client.get("/api/pos/held", headers=owner).json()
    assert len(held) >= 1
    hid = held[0]["id"]
    r = client.post(f"/api/pos/hold/{hid}/resume", headers=owner)
    assert r.status_code == 200, r.text


def test_offline_sync_queue_idempotent(client, owner):
    """No cloud configured -> transactions succeed, queue stays pending (offline-first)."""
    q = client.get("/api/sync/status", headers=owner).json()
    assert q["pending"] >= 1  # our sales/purchases were enqueued
    r = client.post("/api/sync/run", headers=owner)
    assert r.status_code == 200
    after = client.get("/api/sync/status", headers=owner).json()
    assert after["pending"] >= 1  # nothing lost, still queued for when cloud appears


def test_backup_manual(client, owner):
    r = client.post("/api/backups/create", headers=owner, json={})
    assert r.status_code == 200, r.text
    bids = client.get("/api/backups", headers=owner).json()
    assert len(bids) >= 1
    v = client.get(f"/api/backups/{bids[0]['id']}/verify", headers=owner).json()
    assert v["ok"] is True


def test_device_revoke_blocks_requests(client, owner, cashier):
    devs = client.get("/api/devices", headers=owner).json()
    pos2 = next(d for d in devs if d["device_id"] == "POS-02")
    r = client.post(f"/api/devices/{pos2['id']}/revoke", headers=owner,
                    json={"reason": "Lost device"})
    assert r.status_code == 200, r.text
    # cashier session on POS-02 is now blocked
    assert client.get("/api/products/search?q=surf", headers=cashier).status_code == 403
    # restore for subsequent runs
    client.post(f"/api/devices/{pos2['id']}/restore", headers=owner)


def test_settings_actually_apply(client, owner, flow):
    """Spec #71: changing currency symbol affects formatted outputs."""
    r = client.put("/api/settings", headers=owner,
                   json={"currency.symbol": "Rs"})
    assert r.status_code == 200, r.text
    sid = flow["sale_cash"]["id"]
    t = client.get(f"/api/pos/sales/{sid}/receipt.txt", headers=owner).text
    assert "Rs" in t
    # disabling dasti blocks new dasti sales
    client.put("/api/settings", headers=owner, json={"payments.dasti": False})
    r = client.post("/api/pos/sales", headers=owner, json={
        "items": [{"product_id": FLOW["prod"], "qty": 1}], "credit_mode": "dasti",
        "dasti": {"customer_name": "X"}})
    assert r.status_code == 400
    client.put("/api/settings", headers=owner, json={"payments.dasti": True})


def test_export_import_csv(client, owner):
    ex = client.get("/api/export/products", headers=owner)
    assert ex.status_code == 200 and "Surf" in ex.text
    csv_data = "name,cost_price,retail_price,unit\nMaggi 70g,45,55,Packet\n"
    r = client.post("/api/import/products", headers=owner,
                    files={"file": ("products.csv", csv_data, "text/csv")})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["created"] >= 1
