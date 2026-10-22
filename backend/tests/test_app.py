import os
import tempfile
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "test-runtime.db"
TEST_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
TEST_UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="pricing-upload-tests-"))
os.environ["UPLOAD_DIR"] = str(TEST_UPLOAD_DIR)

from fastapi.testclient import TestClient

from app import app


def admin_client() -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return client


def catalog_for_quote(client: TestClient) -> tuple[int, int]:
    body = client.post(
        "/api/admin/bodies",
        json={"name": "测试主体", "model": "TEST-BODY", "description": "", "cost": 100, "active": True},
    )
    accessory = client.post(
        "/api/admin/accessories",
        json={
            "name": "测试配件",
            "model": "TEST-ACC",
            "category": "手喷",
            "attributes": {},
            "cost": 10,
            "default_qty": 1,
            "min_qty": 0,
            "max_qty": 2,
            "active": True,
        },
    )
    assert body.status_code == 200
    assert accessory.status_code == 200
    return body.json()["id"], accessory.json()["id"]


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
        accessories = client.get("/api/catalog/accessories").json()
        if not accessories:
            admin = admin_client()
            _, accessory_id = catalog_for_quote(admin)
            accessories = [{"id": accessory_id}]
        payload = {"body_id": body["id"], "lines": [{"accessory_id": accessories[0]["id"], "quantity": 1}]}
        created = client.post("/api/quotes", json=payload).json()
        detail = client.get(f"/api/quotes/{created['quote_no']}").json()
        assert "private" not in detail
        assert all("line_cost" not in line for line in detail["lines"])


def test_hard_delete_user_preserves_quote_and_audit_snapshots():
    admin = admin_client()
    body_id, accessory_id = catalog_for_quote(admin)
    created_user = admin.post(
        "/api/admin/users",
        json={"username": "delete-me", "password": "delete-me123", "role": "employee", "active": True},
    )
    assert created_user.status_code == 200
    user_id = created_user.json()["id"]

    employee = TestClient(app)
    assert employee.post("/api/auth/login", json={"username": "delete-me", "password": "delete-me123"}).status_code == 200
    quote = employee.post("/api/quotes", json={"body_id": body_id, "lines": [{"accessory_id": accessory_id, "quantity": 1}]}).json()

    deleted = admin.delete(f"/api/admin/users/{user_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "deleted": True, "id": user_id}
    assert all(row["username"] != "delete-me" for row in admin.get("/api/admin/users").json())

    quotes = admin.get("/api/admin/quotes").json()
    saved = next(row for row in quotes if row["quote_no"] == quote["quote_no"])
    assert saved["username"] == "delete-me"
    logs = admin.get("/api/admin/audit-logs").json()
    assert any(row["username"] == "delete-me" and row["target_type"] == "session" for row in logs)
    assert any(row["target_type"] == "user" and row["target_id"] == str(user_id) and row["target_deleted"] for row in logs)


def test_bundle_quote_replacement_and_reference_guards():
    admin = admin_client()
    body_id, accessory_id = catalog_for_quote(admin)
    second = admin.post("/api/admin/accessories", json={"name":"替换配件","model":"TEST-ACC-2","category":"手喷","attributes":{},"cost":20,"default_qty":1,"min_qty":0,"max_qty":2,"active":True}).json()
    bundle = admin.post("/api/admin/bundles", json={"name":"测试套装","description":"说明","body_id":body_id,"active":True,"items":[{"accessory_id":accessory_id,"quantity":1,"position":1}]}).json()
    assert bundle["name"] == "测试套装"
    assert admin.patch(f"/api/admin/bodies/{body_id}", json={"name":"测试主体","model":"TEST-BODY","description":"","cost":100,"active":False}).status_code == 409
    assert admin.delete(f"/api/admin/accessories/{accessory_id}").status_code == 409

    employee = TestClient(app)
    assert employee.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
    detail = employee.get(f"/api/catalog/bundles/{bundle['id']}").json()
    assert "cost" not in detail["body"]
    assert second["id"] in [x["id"] for x in detail["replacement_candidates"]["手喷"]]
    quote = employee.post("/api/quotes", json={"bundle_id": bundle["id"], "lines": [{"bundle_item_id": bundle["items"][0]["id"], "accessory_id": second["id"], "quantity": 1}]}).json()
    saved_detail = employee.get(f"/api/quotes/{quote['quote_no']}").json()
    assert saved_detail["bundle"]["id"] == bundle["id"]
    assert saved_detail["replacements"][0]["replacement_accessory_id"] == second["id"]
    assert employee.get(f"/api/catalog/bundles/{bundle['id']}").json()["items"][0]["accessory"]["id"] == accessory_id
    duplicated = employee.post(f"/api/quotes/{quote['quote_no']}/duplicate")
    assert duplicated.status_code == 200

    assert admin.delete(f"/api/admin/bundles/{bundle['id']}").json()["deleted"] is True
    assert admin.delete(f"/api/admin/bodies/{body_id}").json()["deleted"] is True
    assert admin.delete(f"/api/admin/accessories/{accessory_id}").json()["deleted"] is True
    assert any(row["quote_no"] == quote["quote_no"] for row in admin.get("/api/admin/quotes").json())

    deleted_quote = admin.delete(f"/api/admin/quotes/{quote['quote_no']}")
    assert deleted_quote.json() == {"ok": True, "deleted": True, "id": quote["quote_no"]}
    assert all(row["quote_no"] != quote["quote_no"] for row in admin.get("/api/admin/quotes").json())
    logs = admin.get("/api/admin/audit-logs").json()
    assert any(row["target_type"] == "quote" and row["target_id"] == quote["quote_no"] and row["target_deleted"] for row in logs)


def test_current_admin_cannot_be_deleted():
    admin = admin_client()
    current = next(row for row in admin.get("/api/admin/users").json() if row["username"] == "admin")
    response = admin.delete(f"/api/admin/users/{current['id']}")
    assert response.status_code == 400
    assert response.json()["message"] == "不能删除当前登录账号"


def test_shared_upload_is_removed_only_after_last_reference():
    admin = admin_client()
    image = TEST_UPLOAD_DIR / "shared.png"
    image.write_bytes(b"test-image")
    image_url = "/uploads/shared.png"
    payload = {"name": "图片主体", "model": "IMG", "image_url": image_url, "description": "", "cost": 1, "active": True}
    first = admin.post("/api/admin/bodies", json=payload).json()
    second = admin.post("/api/admin/bodies", json={**payload, "model": "IMG-2"}).json()

    assert admin.delete(f"/api/admin/bodies/{first['id']}").status_code == 200
    assert image.exists()
    assert admin.delete(f"/api/admin/bodies/{second['id']}").status_code == 200
    assert not image.exists()
