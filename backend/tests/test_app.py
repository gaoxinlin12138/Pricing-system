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


def test_admin_routes_require_authentication():
    with TestClient(app) as client:
        assert client.get("/api/admin/users").status_code == 401
        assert client.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
        assert client.get("/api/admin/users").status_code == 403


def test_logout_revokes_server_session():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert response.status_code == 200
        stale_cookie = response.cookies.get("shower_session")
        assert stale_cookie
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/admin/users", cookies={"shower_session": stale_cookie}).status_code == 401


def catalog_for_quote(client: TestClient) -> tuple[int, int]:
    body = client.post(
        "/api/admin/accessories",
        json={
            "name": "测试主体",
            "model": "TEST-BODY",
            "category": "主体",
            "description": "",
            "attributes": {},
            "cost": 100,
            "default_qty": 1,
            "min_qty": 1,
            "max_qty": 1,
            "active": True,
        },
    )
    accessory = client.post(
        "/api/admin/accessories",
        json={
            "name": "测试配件",
            "model": "TEST-ACC",
            "category": "花洒喷头",
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
        admin = admin_client()
        body_id, accessory_id = catalog_for_quote(admin)
        bundle = admin.post("/api/admin/bundles", json={"name":"安全快照套装","description":"","body_id":body_id,"active":True,"items":[{"accessory_id":accessory_id,"quantity":1,"position":1}]}).json()
        payload = {"bundle_id": bundle["id"], "lines": [{"bundle_item_id": bundle["items"][0]["id"], "accessory_id": accessory_id, "quantity": 1}]}
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
    bundle = admin.post("/api/admin/bundles", json={"name":"删除账号套装","description":"","body_id":body_id,"active":True,"items":[{"accessory_id":accessory_id,"quantity":1,"position":1}]}).json()
    quote = employee.post("/api/quotes", json={"bundle_id": bundle["id"], "lines": [{"bundle_item_id": bundle["items"][0]["id"], "accessory_id": accessory_id, "quantity": 1}]}).json()

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
    second = admin.post("/api/admin/accessories", json={"name":"替换配件","model":"TEST-ACC-2","category":"花洒喷头","attributes":{},"cost":20,"default_qty":1,"min_qty":0,"max_qty":2,"active":True}).json()
    bundle = admin.post("/api/admin/bundles", json={"name":"测试套装","description":"说明","body_id":body_id,"active":True,"items":[{"accessory_id":accessory_id,"quantity":1,"position":1}]}).json()
    assert bundle["name"] == "测试套装"
    assert admin.patch(f"/api/admin/accessories/{body_id}", json={"name":"测试主体","model":"TEST-BODY","category":"主体","description":"","attributes":{},"cost":100,"default_qty":1,"min_qty":1,"max_qty":1,"active":False}).status_code == 409
    assert admin.delete(f"/api/admin/accessories/{accessory_id}").status_code == 409

    employee = TestClient(app)
    assert employee.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
    detail = employee.get(f"/api/catalog/bundles/{bundle['id']}").json()
    assert "cost" not in detail["body"]
    assert second["id"] in [x["id"] for x in detail["replacement_candidates"]["花洒喷头"]]
    quote = employee.post("/api/quotes", json={"bundle_id": bundle["id"], "lines": [{"bundle_item_id": bundle["items"][0]["id"], "accessory_id": second["id"], "quantity": 1}]}).json()
    saved_detail = employee.get(f"/api/quotes/{quote['quote_no']}").json()
    assert saved_detail["bundle"]["id"] == bundle["id"]
    assert saved_detail["replacements"][0]["replacement_accessory_id"] == second["id"]
    assert employee.get(f"/api/catalog/bundles/{bundle['id']}").json()["items"][0]["accessory"]["id"] == accessory_id
    duplicated = employee.post(f"/api/quotes/{quote['quote_no']}/duplicate")
    assert duplicated.status_code == 200

    assert admin.delete(f"/api/admin/bundles/{bundle['id']}").json()["deleted"] is True
    assert admin.delete(f"/api/admin/accessories/{body_id}").json()["deleted"] is True
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
    deactivate = admin.patch(
        f"/api/admin/users/{current['id']}",
        json={"username": "admin", "password": None, "role": "admin", "active": False},
    )
    assert deactivate.status_code == 400
    assert deactivate.json()["message"] == "不能停用当前登录账号"


def test_employee_cannot_create_legacy_freeform_quote():
    admin = admin_client()
    body_id, accessory_id = catalog_for_quote(admin)
    employee = TestClient(app)
    assert employee.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
    response = employee.post("/api/quotes", json={"body_id": body_id, "lines": [{"accessory_id": accessory_id, "quantity": 1}]})
    assert response.status_code == 403


def test_employee_can_replace_bundle_body_but_quantity_stays_one():
    admin = admin_client()
    body_id, accessory_id = catalog_for_quote(admin)
    second_body = admin.post(
        "/api/admin/accessories",
        json={
            "name": "替换主体",
            "model": "TEST-BODY-2",
            "category": "主体",
            "description": "",
            "attributes": {},
            "cost": 120,
            "default_qty": 1,
            "min_qty": 1,
            "max_qty": 1,
            "active": True,
        },
    ).json()
    bundle = admin.post(
        "/api/admin/bundles",
        json={
            "name": "主体可替换套装",
            "description": "",
            "body_id": body_id,
            "active": True,
            "items": [{"accessory_id": accessory_id, "quantity": 1, "position": 1}],
        },
    ).json()
    employee = TestClient(app)
    assert employee.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
    detail = employee.get(f"/api/catalog/bundles/{bundle['id']}").json()
    assert second_body["id"] in [row["id"] for row in detail["replacement_candidates"]["主体"]]

    payload = {
        "bundle_id": bundle["id"],
        "body_id": second_body["id"],
        "lines": [{"bundle_item_id": bundle["items"][0]["id"], "accessory_id": accessory_id, "quantity": 1}],
        "set_quantity": 1,
    }
    quote = employee.post("/api/quotes", json=payload)
    assert quote.status_code == 200
    saved = employee.get(f"/api/quotes/{quote.json()['quote_no']}").json()
    assert saved["body"]["id"] == second_body["id"]
    assert saved["replacements"][0]["category"] == "主体"
    assert saved["replacements"][0]["original_accessory_id"] == body_id
    assert saved["replacements"][0]["replacement_accessory_id"] == second_body["id"]
    assert employee.get(f"/api/catalog/bundles/{bundle['id']}").json()["body"]["id"] == body_id
    duplicated = employee.post(f"/api/quotes/{quote.json()['quote_no']}/duplicate")
    assert duplicated.status_code == 200
    assert duplicated.json()["body"]["id"] == second_body["id"]


def test_admin_role_invariant_and_quantity_range_guard():
    admin = admin_client()
    current = next(row for row in admin.get("/api/admin/users").json() if row["username"] == "admin")
    demote_self = admin.patch(f"/api/admin/users/{current['id']}", json={"username": "admin", "password": None, "role": "employee", "active": True})
    assert demote_self.status_code == 400

    body_id, accessory_id = catalog_for_quote(admin)
    bundle = admin.post("/api/admin/bundles", json={"name":"数量范围保护","description":"","body_id":body_id,"active":True,"items":[{"accessory_id":accessory_id,"quantity":1,"position":1}]}).json()
    response = admin.patch(f"/api/admin/accessories/{accessory_id}", json={"name":"测试配件","model":"TEST-ACC","category":"花洒喷头","attributes":{},"cost":10,"default_qty":2,"min_qty":2,"max_qty":2,"active":True})
    assert response.status_code == 409
    assert bundle["id"] in [row["id"] for row in admin.get("/api/admin/bundles").json()]


def test_blank_catalog_names_and_models_are_rejected():
    admin = admin_client()
    for field in ("name", "model"):
        payload = {
            "name": "正常名称",
            "model": "NORMAL-MODEL",
            "category": "主体",
            "cost": 1,
            "default_qty": 1,
            "min_qty": 1,
            "max_qty": 1,
            "active": True,
        }
        payload[field] = "   "
        assert admin.post("/api/admin/accessories", json=payload).status_code == 422


def test_bundle_cover_image_survives_orphan_cleanup():
    from app import SessionLocal, cleanup_orphan_uploads

    admin = admin_client()
    body_id, accessory_id = catalog_for_quote(admin)
    image = TEST_UPLOAD_DIR / "bundle-cover.png"
    image.write_bytes(b"cover")
    image_url = "/uploads/bundle-cover.png"

    bundle = admin.post(
        "/api/admin/bundles",
        json={
            "name": "封面套装",
            "code": "COVER-1",
            "description": "",
            "image_url": image_url,
            "body_id": body_id,
            "active": True,
            "items": [{"accessory_id": accessory_id, "quantity": 1, "position": 1}],
        },
    ).json()
    assert bundle["image_url"] == image_url
    assert bundle["code"] == "COVER-1"

    with SessionLocal() as db:
        cleanup_orphan_uploads(db)
    assert image.exists(), "套装封面不应被当作孤儿文件清理"

    assert admin.delete(f"/api/admin/bundles/{bundle['id']}").status_code == 200
    assert not image.exists(), "删除套装后应清理其封面文件"


def test_shared_upload_is_removed_only_after_last_reference():
    admin = admin_client()
    image = TEST_UPLOAD_DIR / "shared.png"
    image.write_bytes(b"test-image")
    image_url = "/uploads/shared.png"
    payload = {"name": "图片主体", "model": "IMG", "category": "主体", "image_url": image_url, "description": "", "attributes": {}, "cost": 1, "default_qty": 1, "min_qty": 1, "max_qty": 1, "active": True}
    first = admin.post("/api/admin/accessories", json=payload).json()
    second = admin.post("/api/admin/accessories", json={**payload, "model": "IMG-2"}).json()

    assert admin.delete(f"/api/admin/accessories/{first['id']}").status_code == 200
    assert image.exists()
    assert admin.delete(f"/api/admin/accessories/{second['id']}").status_code == 200
    assert not image.exists()


def test_health_endpoint_is_public():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_quote_price_uses_accessory_and_set_quantity():
    admin = admin_client()
    body_id, accessory_id = catalog_for_quote(admin)
    employee = TestClient(app)
    assert employee.post("/api/auth/login", json={"username": "employee", "password": "employee123"}).status_code == 200
    bundle = admin.post("/api/admin/bundles", json={"name":"数量测试套装","description":"","body_id":body_id,"active":True,"items":[{"accessory_id":accessory_id,"quantity":1,"position":1}]}).json()
    quote = employee.post(
        "/api/quotes",
        json={"bundle_id": bundle["id"], "lines": [{"bundle_item_id": bundle["items"][0]["id"], "accessory_id": accessory_id, "quantity": 2}], "set_quantity": 2},
    ).json()
    # 配件总成本 = 单件 10 × 数量 2 = 20；单套 = (100 + 20 + 80) × 1.5 = 300；2 套总计 600
    assert quote["set_quantity"] == 2
    assert quote["unit_price"] == "300.00"
    assert quote["final_price"] == "600.00"
    detail = employee.get(f"/api/quotes/{quote['quote_no']}").json()
    assert detail["set_quantity"] == 2
    assert detail["unit_price"] == "300.00"
    assert "discount_type" not in detail
    assert "discount_value" not in detail
    summary = next(row for row in employee.get("/api/quotes").json() if row["quote_no"] == quote["quote_no"])
    assert summary["set_quantity"] == 2
    assert summary["unit_price"] == "300.00"
    assert summary["final_price"] == "600.00"

    settings = admin.get("/api/admin/pricing-settings").json()
    assert "tax_rate_percent" not in settings
    assert "max_discount_percent" not in settings
    assert "minimum_price" not in settings
    assert "freight" not in settings


def test_numeric_attribute_gets_unit_appended():
    admin = admin_client()
    payload = {
        "name": "单位测试杆",
        "model": "UNIT-TEST",
        "category": "杆子",
        "description": "",
        "attributes": {"长度": "500", "厚度/重量": "2.5", "形状": "方杆"},
        "cost": 1,
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
        "active": True,
    }
    created = admin.post("/api/admin/accessories", json=payload)
    assert created.status_code == 200
    row = created.json()
    assert row["attributes"]["长度"] == "500mm"
    assert row["attributes"]["厚度/重量"] == "2.5mm"
    assert row["attributes"]["形状"] == "方杆"

    updated = admin.patch(
        f"/api/admin/accessories/{row['id']}",
        json={**payload, "attributes": {"长度": "600mm", "厚度/重量": "3"}},
    ).json()
    assert updated["attributes"]["长度"] == "600mm"
    assert updated["attributes"]["厚度/重量"] == "3mm"

    assert admin.delete(f"/api/admin/accessories/{row['id']}").status_code == 200
