import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test-pricing.db"

from fastapi.testclient import TestClient

from app import app


def test_employee_cannot_see_costs():
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
        bodies = client.get("/api/catalog/bodies").json()
        accessories = client.get("/api/catalog/accessories").json()
        assert all("cost" not in item for item in bodies + accessories)


def test_quote_snapshot_is_publicly_safe():
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "employee", "password": "employee123"})
        body = client.get("/api/catalog/bodies").json()[0]
        required = [x for x in client.get("/api/catalog/accessories").json() if x["required"]]
        payload = {"body_id": body["id"], "lines": [{"accessory_id": x["id"], "quantity": 1} for x in required]}
        created = client.post("/api/quotes", json=payload).json()
        detail = client.get(f"/api/quotes/{created['quote_no']}").json()
        assert "private" not in detail
        assert all("line_cost" not in line for line in detail["lines"])

