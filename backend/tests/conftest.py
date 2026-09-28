"""Test fixtures: isolated temp SQLite DB per session, in-memory HTTP client,
owner + cashier tokens. KARYANA_DATA_DIR must be set before app import."""
import os
import shutil
import tempfile

_tmp = tempfile.mkdtemp(prefix="karyana_test_")
os.environ["KARYANA_DATA_DIR"] = _tmp
os.environ["KARYANA_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ["KARYANA_SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    from app.core.database import init_db
    init_db()
    with TestClient(app) as c:
        yield c
    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def owner(client):
    """Run the setup wizard once; return (headers, data)."""
    r = client.post("/api/auth/setup", json={
        "store_name": "Test Karyana Store",
        "owner_username": "owner",
        "owner_password": "owner-pass-123",
        "owner_full_name": "Owner Ji",
        "opening_cash": 5000,
    })
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def cashier(client, owner):
    """Create a cashier user + an authorized device POS-02, log in there."""
    r = client.get("/api/roles", headers=owner)
    assert r.status_code == 200, r.text
    roles = r.json()
    cashier_role = next(x["id"] for x in roles if x["name"] == "Cashier")
    r = client.post("/api/users", headers=owner, json={
        "username": "bilal", "password": "bilal-pass-123",
        "full_name": "Bilal", "role_id": cashier_role,
    })
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/login", json={  # login on second device
        "username": "bilal", "password": "bilal-pass-123", "device_id": "POS-02"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def accounts(client, owner):
    r = client.get("/api/accounts", headers=owner)
    assert r.status_code == 200, r.text
    by_name = {a["name"]: a["id"] for a in r.json()}
    return by_name


@pytest.fixture(scope="session")
def flow(client, owner, cashier, accounts):
    """Execute the spec #63 business flow exactly once; share results via module FLOW."""
    from tests import test_end_to_end as e2e
    if "prod" not in e2e.FLOW:
        e2e.test_full_business_flow(client, owner, cashier, accounts)
    return e2e.FLOW
