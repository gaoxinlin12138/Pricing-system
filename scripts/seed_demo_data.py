"""一次性演示数据：通过 API 创建配件与预设套装（可在后台删除）。"""

import httpx

BASE = "http://127.0.0.1:8002"

ACCESSORIES = [
    {
        "name": "方形不锈钢杆",
        "model": "GZ-220",
        "category": "杆子",
        "cost": 45,
        "attributes": {"颜色": "黑", "形状": "方杆", "结构": "上下两根杆子", "长度": "600mm"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "圆形升降杆",
        "model": "GZ-110",
        "category": "杆子",
        "cost": 38,
        "attributes": {"颜色": "银", "形状": "圆杆", "结构": "一体式杆子", "长度": "500mm"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "中叉 + 墙座组件",
        "model": "ZC-01",
        "category": "中叉+墙座",
        "cost": 26,
        "attributes": {"安装方式": "螺丝固定", "表面处理": "镀铬"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 2,
    },
    {
        "name": "三档手喷",
        "model": "SP-330",
        "category": "手喷",
        "cost": 32,
        "attributes": {"颜色": "黑", "档位": "三档", "尺寸大小": "110mm", "是否防爆": "是"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 2,
    },
    {
        "name": "二档手喷",
        "model": "SP-210",
        "category": "手喷",
        "cost": 24,
        "attributes": {"颜色": "银", "档位": "二档", "尺寸大小": "95mm"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 2,
    },
    {
        "name": "圆形顶喷",
        "model": "DP-250",
        "category": "顶喷",
        "cost": 58,
        "attributes": {"颜色": "黑", "形状": "圆形", "尺寸大小": "250mm", "档位": "无档"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "方形顶喷",
        "model": "DP-300",
        "category": "顶喷",
        "cost": 76,
        "attributes": {"颜色": "银", "形状": "方形", "尺寸大小": "300mm"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "铜芯电话线",
        "model": "TL-150",
        "category": "电话线",
        "cost": 12,
        "attributes": {"长度": "1.5m", "内芯": "铜芯", "材质款式": "PVC管"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "不锈钢手喷软管",
        "model": "SH-150",
        "category": "手喷软管",
        "cost": 15,
        "attributes": {"长度": "1.5m", "内芯": "不锈钢芯", "材质款式": "波纹管"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "增压喷枪",
        "model": "PQ-01",
        "category": "喷枪",
        "cost": 22,
        "attributes": {"颜色": "黑", "材质": "ABS", "档位": "无档"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "name": "大置物弯角角阀",
        "model": "JV-08",
        "category": "弯角角阀",
        "cost": 35,
        "attributes": {"角阀颜色": "银", "弯角型号": "大置物弯角", "弯角材质": "铜弯角"},
        "default_qty": 1,
        "min_qty": 1,
        "max_qty": 2,
    },
]

BUNDLES = [
    {
        "name": "星瀑 · 基础三件套",
        "code": "XPB-B03",
        "description": "基础淋浴组合，方杆 + 三档手喷，适合预算型客户。",
        "body_model": "SH-001",
        "models": ["GZ-220", "SP-330", "SH-150", "JV-08"],
    },
    {
        "name": "星瀑 · 舒适顶喷套",
        "code": "LY0653NBT",
        "description": "带圆形顶喷与增压喷枪的完整组合，适合家用主卫。",
        "body_model": "SH-001",
        "models": ["GZ-220", "ZC-01", "SP-330", "DP-250", "TL-150", "SH-150", "PQ-01"],
    },
    {
        "name": "雾幕 · 极简套装",
        "code": "WM-M02",
        "description": "雾幕主体配圆杆与二档手喷，线条简洁。",
        "body_model": "SH-002",
        "models": ["GZ-110", "SP-210", "SH-150"],
    },
]


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=20)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    login.raise_for_status()

    existing_accessories = {row["model"]: row for row in client.get("/api/admin/accessories").json()}
    for item in ACCESSORIES:
        if item["model"] in existing_accessories:
            continue
        response = client.post("/api/admin/accessories", json={**item, "image_url": "", "active": True})
        response.raise_for_status()
        existing_accessories[item["model"]] = response.json()

    bodies = {row["model"]: row for row in client.get("/api/admin/bodies").json()}
    existing_bundles = {row["name"] for row in client.get("/api/admin/bundles").json()}

    for bundle in BUNDLES:
        if bundle["name"] in existing_bundles:
            continue
        body = bodies[bundle["body_model"]]
        items = [
            {"accessory_id": existing_accessories[model]["id"], "quantity": 1, "position": index + 1}
            for index, model in enumerate(bundle["models"])
        ]
        response = client.post(
            "/api/admin/bundles",
            json={
                "name": bundle["name"],
                "code": bundle.get("code", ""),
                "description": bundle["description"],
                "body_id": body["id"],
                "active": True,
                "items": items,
            },
        )
        response.raise_for_status()
        print("created bundle:", response.json()["name"])

    print("accessories:", len(client.get("/api/admin/accessories").json()))
    print("bundles:", [row["name"] for row in client.get("/api/admin/bundles").json()])


if __name__ == "__main__":
    main()
