from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


ROOT = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; configure a PostgreSQL connection in .env")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
if APP_ENV in {"production", "prod"} and not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET is required in production")
if APP_ENV in {"production", "prod"} and os.getenv("COOKIE_SECURE", "").strip().lower() != "true":
    raise RuntimeError("COOKIE_SECURE=true is required in production")
# 开发环境也不再使用源码中固定的默认密钥；每次进程重启都会让旧会话失效。
SESSION_SECRET = SESSION_SECRET or secrets.token_urlsafe(32)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", ROOT / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
login_failures: dict[str, list[datetime]] = {}
SESSION_TTL = timedelta(hours=12)

# 配件类别字段来自公司当前的产品资料表。字段定义本身不含价格，
# 仅用于让管理员按类别录入结构化属性；实际属性值仍保存在 accessories.attributes JSON 中。
BODY_CATEGORY = "主体"

ACCESSORY_CATEGORY_SCHEMAS: list[dict[str, Any]] = [
    {
        "category": BODY_CATEGORY,
        "note": "套装的基础件，每套固定选一个；只维护名称、型号、成本、图片和描述。",
        "fields": [],
    },
    {
        "category": "杆子",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "厚度/重量", "label": "厚度/重量", "type": "text", "unit": "mm"},
            {"key": "长度", "label": "长度", "type": "text", "unit": "mm"},
            {"key": "形状", "label": "形状（方杆/圆杆）", "type": "select", "options": ["方杆", "圆杆"]},
            {"key": "结构", "label": "结构", "type": "select", "options": ["上下两根杆子", "一体式杆子"]},
        ],
    },
    {
        "category": "中叉+墙座",
        "note": "一般与杆子配套发放，可以和杆子放在一起。",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "安装方式", "label": "安装方式", "type": "text"},
            {"key": "表面处理", "label": "表面处理", "type": "text"},
            {"key": "适配杆径", "label": "适配杆径", "type": "text", "unit": "mm"},
        ],
    },
    {
        "category": "花洒喷头",
        "note": "手喷与顶喷合并为同一类，属性一致，统一按花洒喷头维护。",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "形状", "label": "形状", "type": "text"},
            {"key": "是否防爆", "label": "是否防爆", "type": "text"},
            {"key": "尺寸大小", "label": "尺寸大小", "type": "text", "unit": "mm"},
            {"key": "档位", "label": "档位", "type": "select", "options": ["无档", "一档", "二档", "三档", "四档"]},
        ],
    },
    {
        "category": "电话线",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "长度", "label": "长度", "type": "text", "unit": "m"},
            {"key": "内芯", "label": "内芯", "type": "select", "options": ["铜芯", "不锈钢芯"]},
            {"key": "流量大小", "label": "流量大小", "type": "select", "options": ["大流量", "小流量"]},
            {"key": "材质款式", "label": "材质款式", "type": "select", "options": ["PVC管", "波纹管"]},
        ],
    },
    {
        "category": "手喷软管",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "长度", "label": "长度", "type": "text", "unit": "m"},
            {"key": "内芯", "label": "内芯", "type": "select", "options": ["铜芯", "不锈钢芯"]},
            {"key": "材质款式", "label": "材质款式", "type": "select", "options": ["PVC管", "波纹管"]},
        ],
    },
    {
        "category": "喷枪",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "材质", "label": "材质", "type": "text"},
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "档位", "label": "档位", "type": "select", "options": ["无档", "一档", "二档", "三档", "四档"]},
        ],
    },
    {
        "category": "弯角角盘",
        "fields": [
            {"key": "供应商", "label": "供应商", "type": "text"},
            {"key": "角阀颜色", "label": "角阀颜色", "type": "text"},
            {"key": "角阀形状", "label": "角阀形状", "type": "text"},
            {"key": "弯角型号", "label": "弯角型号（普通弯角/大置物弯角/加长弯角等）", "type": "text"},
            {"key": "弯角材质", "label": "弯角材质（铜弯角/304弯角等）", "type": "text"},
        ],
    },
]

_NUMBER_ONLY = re.compile(r"\d+(?:\.\d+)?")


def normalize_attribute_units(category: str, attributes: dict[str, Any] | None) -> dict[str, str]:
    """属性里带单位的字段，如果只填了数字就自动补上单位（如 500 -> 500mm）。"""
    schema = next((item for item in ACCESSORY_CATEGORY_SCHEMAS if item["category"] == category), None)
    units = {field["key"]: field["unit"] for field in (schema or {}).get("fields", []) if field.get("unit")}
    result: dict[str, str] = {}
    for key, value in (attributes or {}).items():
        text = str(value).strip() if value is not None else ""
        unit = units.get(key)
        if unit and _NUMBER_ONLY.fullmatch(text):
            text = f"{text}{unit}"
        result[key] = text
    return result


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="employee")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Body(Base):
    """历史遗留表：0001 迁移用当前模型建库，需要保留它才能让旧迁移链在全新数据库上跑通。
    运行期数据已全部迁到 Accessory（category = "主体"），业务代码不再读写这张表。"""

    __tablename__ = "bodies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(80))
    image_url: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Accessory(Base):
    __tablename__ = "accessories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(80))
    image_url: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    default_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    min_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    max_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=99)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Bundle(Base):
    __tablename__ = "bundles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    # 主体已并入配件表（category = "主体"），字段名保留 body_id 以减少调用方改动。
    body_id: Mapped[int] = mapped_column(ForeignKey("accessories.id", ondelete="RESTRICT"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BundleItem(Base):
    __tablename__ = "bundle_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    accessory_id: Mapped[int] = mapped_column(ForeignKey("accessories.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    position: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("bundle_id", "accessory_id", name="uq_bundle_accessory"),)


class PricingSettings(Base):
    __tablename__ = "pricing_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("1.5"))
    labor_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("80"))
    quote_valid_days: Mapped[int] = mapped_column(Integer, default=15)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name_snapshot: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="saved")
    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(60), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    target_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=256)


class LineIn(BaseModel):
    accessory_id: int
    quantity: Decimal = Field(default=Decimal("1"), ge=0, max_digits=12, decimal_places=3)


class QuoteIn(BaseModel):
    body_id: int
    lines: list[LineIn] = Field(default_factory=list)
    set_quantity: int = Field(default=1, ge=1, le=99)
    # 员工报价时按当前套装输入；缺省时沿用后台保存的默认值，兼容管理员旧版试算接口。
    multiplier: Decimal | None = Field(default=None, ge=1, max_digits=8, decimal_places=4)
    labor_fee: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class SettingsIn(BaseModel):
    multiplier: Decimal = Field(ge=1, max_digits=8, decimal_places=4)
    labor_fee: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    quote_valid_days: int = Field(ge=1, le=365)


class QuoteSettingsIn(BaseModel):
    quote_valid_days: int = Field(ge=1, le=365)


class BulkQuoteDeleteIn(BaseModel):
    quote_nos: list[str] = Field(min_length=1, max_length=200)


class AccessoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    image_url: str = Field(default="", max_length=500)
    description: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    default_qty: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    min_qty: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    max_qty: Decimal = Field(default=Decimal("99"), ge=0, max_digits=12, decimal_places=3)
    active: bool = True


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    # 密码在创建时必填、修改时可留空（留空表示保留原密码）。
    # 不在 Pydantic 字段上做 min_length 校验，否则管理员编辑账号不改密码时会被 422 拒绝。
    password: str | None = None
    role: Literal["admin", "employee"] = "employee"
    active: bool = True


class BundleItemIn(BaseModel):
    accessory_id: int
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=12, decimal_places=3)
    position: int = Field(default=1, ge=1)


class BundleIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(default="", max_length=80)
    description: str = ""
    image_url: str = Field(default="", max_length=500)
    body_id: int
    active: bool = True
    items: list[BundleItemIn] = Field(min_length=1)


class BundleLineIn(BaseModel):
    bundle_item_id: int
    accessory_id: int
    quantity: Decimal = Field(ge=0, max_digits=12, decimal_places=3)


class BundleQuoteIn(BaseModel):
    bundle_id: int
    # Optional for backward compatibility; omitted means use the bundle's original body.
    body_id: int | None = Field(default=None, ge=1)
    lines: list[BundleLineIn] = Field(min_length=1)
    set_quantity: int = Field(default=1, ge=1, le=99)
    # 员工报价时按当前套装输入；缺省时沿用后台保存的默认值，兼容历史报价单。
    multiplier: Decimal | None = Field(default=None, ge=1, max_digits=8, decimal_places=4)
    labor_fee: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


IS_PRODUCTION = APP_ENV in {"production", "prod"}
app = FastAPI(
    title="星瀑计价平台",
    version="0.2.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "请求参数无效"
    code = "AUTH_ERROR" if exc.status_code in (401, 403) else "VALIDATION_ERROR" if exc.status_code < 500 else "SERVER_ERROR"
    return JSONResponse(status_code=exc.status_code, content={"code": code, "message": message, "details": {}})


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, __: IntegrityError):
    return JSONResponse(status_code=409, content={"code": "CONFLICT", "message": "数据关联冲突，操作未完成", "details": {}})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now() -> datetime:
    return datetime.now(timezone.utc)


def rounded(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 150_000)
    return f"pbkdf2_sha256$150000${salt.hex()}${digest.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt_hex, digest_hex = encoded.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def public_accessory(row: Accessory) -> dict[str, Any]:
    attributes = normalize_attribute_units(row.category, row.attributes)
    # 供应商是所有非主体配件的通用属性；历史数据没有填写时也返回空值，便于前端统一编辑。
    if row.category != BODY_CATEGORY:
        attributes.setdefault("供应商", "")
    return {"id": row.id, "name": row.name, "model": row.model, "category": row.category, "image_url": row.image_url, "description": row.description or "", "attributes": attributes, "default_qty": str(row.default_qty), "min_qty": str(row.min_qty), "max_qty": str(row.max_qty)}


def private_accessory(row: Accessory) -> dict[str, Any]:
    return {**public_accessory(row), "cost": str(rounded(row.cost)), "active": row.active, "version": row.version, "updated_at": row.updated_at.isoformat()}


def _bundle_items(db: Session, bundle_id: int) -> list[BundleItem]:
    return db.scalars(select(BundleItem).where(BundleItem.bundle_id == bundle_id).order_by(BundleItem.position, BundleItem.id)).all()


def private_bundle(db: Session, bundle: Bundle) -> dict[str, Any]:
    body = db.get(Accessory, bundle.body_id)
    items = _bundle_items(db, bundle.id)
    accessories = {x.id: x for x in db.scalars(select(Accessory).where(Accessory.id.in_([i.accessory_id for i in items]))).all()} if items else {}
    return {
        "id": bundle.id,
        "name": bundle.name,
        "code": bundle.code or "",
        "description": bundle.description or "",
        "image_url": bundle.image_url or "",
        "active": bundle.active,
        "version": bundle.version,
        "updated_at": bundle.updated_at.isoformat(),
        "body": private_accessory(body) if body else None,
        "items": [{"id": i.id, "accessory": private_accessory(accessories[i.accessory_id]), "quantity": str(i.quantity), "position": i.position} for i in items if i.accessory_id in accessories],
    }


def public_bundle(db: Session, bundle: Bundle, *, include_replacements: bool = False) -> dict[str, Any]:
    body = db.get(Accessory, bundle.body_id)
    items = _bundle_items(db, bundle.id)
    accessories = {x.id: x for x in db.scalars(select(Accessory).where(Accessory.id.in_([i.accessory_id for i in items]))).all()} if items else {}
    result: dict[str, Any] = {
        "id": bundle.id,
        "name": bundle.name,
        "code": bundle.code or "",
        "description": bundle.description or "",
        "image_url": bundle.image_url or "",
        "version": bundle.version,
        "body": public_accessory(body) if body else None,
        "items": [{"id": i.id, "accessory": public_accessory(accessories[i.accessory_id]), "quantity": str(i.quantity), "position": i.position} for i in items if i.accessory_id in accessories],
    }
    if include_replacements:
        categories = sorted({accessories[i.accessory_id].category for i in items if i.accessory_id in accessories} | {BODY_CATEGORY})
        candidates = db.scalars(select(Accessory).where(Accessory.active, Accessory.category.in_(categories)).order_by(Accessory.category, Accessory.id)).all() if categories else []
        result["replacement_candidates"] = {category: [public_accessory(x) for x in candidates if x.category == category] for category in categories}
    return result


def bundle_references_for_body(db: Session, body_id: int) -> list[str]:
    return [x.name for x in db.scalars(select(Bundle).where(Bundle.body_id == body_id).order_by(Bundle.name)).all()]


def bundle_references_for_accessory(db: Session, accessory_id: int) -> list[str]:
    return [x.name for x in db.scalars(select(Bundle).join(BundleItem, BundleItem.bundle_id == Bundle.id).where(BundleItem.accessory_id == accessory_id).order_by(Bundle.name)).all()]


def bundle_quantity_conflicts(
    db: Session,
    accessory_id: int,
    min_qty: Decimal,
    max_qty: Decimal,
) -> list[str]:
    """Return bundles whose saved quantity would become invalid after a range change."""
    rows = db.execute(
        select(Bundle.name, BundleItem.quantity)
        .join(BundleItem, BundleItem.bundle_id == Bundle.id)
        .where(BundleItem.accessory_id == accessory_id)
    ).all()
    return [name for name, quantity in rows if quantity < min_qty or quantity > max_qty]


def validate_bundle_payload(payload: BundleIn, db: Session, existing_id: int | None = None) -> tuple[Accessory, list[Accessory]]:
    body = db.get(Accessory, payload.body_id)
    if not body or body.category != BODY_CATEGORY:
        raise HTTPException(400, "主体不存在")
    if payload.active and not body.active:
        raise HTTPException(400, "套装启用时主体必须处于启用状态")
    ids = [item.accessory_id for item in payload.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "套装内同一配件只能出现一次，请使用数量表示用量")
    accessories = {x.id: x for x in db.scalars(select(Accessory).where(Accessory.id.in_(ids))).all()}
    if len(accessories) != len(ids):
        raise HTTPException(400, "套装包含不存在的配件")
    for item in payload.items:
        accessory = accessories[item.accessory_id]
        if accessory.category == BODY_CATEGORY:
            raise HTTPException(400, f"{accessory.name} 是主体，不能作为套装配件重复添加")
        if payload.active and not accessory.active:
            raise HTTPException(400, f"配件 {accessory.name} 已停用，不能启用套装")
        if item.quantity < accessory.min_qty or item.quantity > accessory.max_qty:
            raise HTTPException(400, f"{accessory.name} 数量需在 {accessory.min_qty} 到 {accessory.max_qty} 之间")
    return body, [accessories[x] for x in ids]


def session_token_hash(token: str) -> str:
    # HMAC 让轮换 SESSION_SECRET 同时撤销旧数据库会话。
    return hmac.new(SESSION_SECRET.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def current_user(session: str | None = Cookie(default=None, alias="shower_session"), db: Session = Depends(get_db)) -> User:
    if not session:
        raise HTTPException(401, "请先登录")
    user_session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == session_token_hash(session),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now(),
        )
    )
    if not user_session:
        raise HTTPException(401, "登录已过期")
    user = db.get(User, user_session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "账号已停用")
    return user


def revoke_user_sessions(db: Session, user_id: int, *, except_token: str | None = None) -> None:
    query = db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_token:
        query = query.filter(UserSession.token_hash != session_token_hash(except_token))
    query.update({UserSession.revoked_at: now()}, synchronize_session=False)


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


def audit(
    db: Session,
    user: User | None,
    action: str,
    target: str,
    target_id: str,
    detail: dict[str, Any] | None = None,
    *,
    target_label: str | None = None,
    target_deleted: bool = False,
) -> None:
    # PostgreSQL JSON 字段不能直接序列化 Decimal；审计日志只保存摘要，统一转换为字符串。
    safe_detail = json.loads(json.dumps(detail or {}, default=str))
    db.add(
        AuditLog(
            actor_id=user.id if user else None,
            actor_name_snapshot=user.username if user else None,
            action=action,
            target_type=target,
            target_id=target_id,
            target_deleted=target_deleted,
            target_label=target_label or target_id,
            detail=safe_detail,
        )
    )


def mark_target_deleted(db: Session, target_type: str, target_id: str, target_label: str) -> None:
    """Keep historical audit rows, but explicitly mark their target as deleted."""
    db.query(AuditLog).filter(
        AuditLog.target_type == target_type,
        AuditLog.target_id == target_id,
    ).update(
        {AuditLog.target_deleted: True, AuditLog.target_label: target_label},
        synchronize_session=False,
    )


def lock_admin_mutations(db: Session) -> None:
    """Serialize changes that can remove an active administrator.

    The settings singleton exists in every initialized database and gives these
    checks a stable row to lock. The fallback keeps older/partially initialized
    databases safe by locking all currently active admin rows instead.
    """
    locked = db.execute(
        select(PricingSettings.id).where(PricingSettings.id == 1).with_for_update()
    ).first()
    if locked is None:
        db.execute(
            select(User.id)
            .where(User.role == "admin", User.active)
            .order_by(User.id)
            .with_for_update()
        ).all()


def upload_filename(image_url: str | None) -> str | None:
    """Return a safe local upload filename, or None for external/invalid URLs."""
    if not image_url:
        return None
    path = unquote(urlparse(str(image_url)).path)
    marker = "/uploads/"
    if marker not in path:
        return None
    name = path.split(marker, 1)[1].strip("/")
    if not name or Path(name).name != name:
        return None
    return name


def remove_uploaded_file(image_url: str | None, db: Session | None = None) -> bool:
    """Delete one local upload only when it is no longer referenced by a record."""
    name = upload_filename(image_url)
    if not name:
        return False
    if db is not None:
        accessory_urls = db.scalars(select(Accessory.image_url).where(Accessory.image_url != "")).all()
        bundle_urls = db.scalars(select(Bundle.image_url).where(Bundle.image_url != "")).all()
        if any(upload_filename(url) == name for url in [*accessory_urls, *bundle_urls]):
            return False
    root = UPLOAD_DIR.resolve()
    target = (root / name).resolve()
    if target.parent != root or not target.is_file():
        return False
    try:
        target.unlink()
        return True
    except OSError:
        return False


def cleanup_orphan_uploads(db: Session) -> int:
    """Remove files in the upload directory that no catalog record references."""
    referenced={upload_filename(url) for url in [*db.scalars(select(Accessory.image_url).where(Accessory.image_url != "")).all(),*db.scalars(select(Bundle.image_url).where(Bundle.image_url != "")).all()]}
    removed=0
    for path in UPLOAD_DIR.iterdir():
        if path.is_file() and path.name not in referenced:
            try:
                path.unlink()
                removed+=1
            except OSError:
                pass
    return removed


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        return
    # 部署时用环境变量指定首次登录密码；未设置时的内置密码只用于本地开发。
    configured_admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()
    configured_employee_password = os.getenv("INITIAL_EMPLOYEE_PASSWORD", "").strip()
    if APP_ENV in {"production", "prod"} and (not configured_admin_password or not configured_employee_password):
        raise RuntimeError("INITIAL_ADMIN_PASSWORD and INITIAL_EMPLOYEE_PASSWORD are required in production")
    if APP_ENV in {"production", "prod"} and (
        len(configured_admin_password) < 8 or len(configured_employee_password) < 8
    ):
        raise RuntimeError("Initial passwords must be at least 8 characters in production")
    admin_password = configured_admin_password or "admin123"
    employee_password = configured_employee_password or "employee123"
    if not configured_admin_password:
        print("警告：未设置 INITIAL_ADMIN_PASSWORD，正在使用内置默认密码，仅限本地开发，请登录后立即修改。", flush=True)
    db.add_all([User(username="admin", password_hash=hash_password(admin_password), role="admin"), User(username="employee", password_hash=hash_password(employee_password), role="employee")])
    db.add(PricingSettings(id=1, multiplier=Decimal("1.5"), labor_fee=Decimal("80"), quote_valid_days=15))
    bodies = [
        Accessory(name="星瀑花洒主体", model="SH-001", category=BODY_CATEGORY, description="304不锈钢主体，适配多种出水组合", cost=Decimal("680"), default_qty=1, min_qty=1, max_qty=1),
        Accessory(name="雾幕花洒主体", model="SH-002", category=BODY_CATEGORY, description="圆润极简主体，适合现代卫浴空间", cost=Decimal("520"), default_qty=1, min_qty=1, max_qty=1),
    ]
    db.add_all(bodies)
    # 真实产品由管理员录入。类别字段由 ACCESSORY_CATEGORY_SCHEMAS 提供，
    # 首次初始化不再写入旧版示例配件，避免员工误用演示成本。
    db.commit()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db)
        cleanup_orphan_uploads(db)


@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    key = payload.username.casefold(); current = now()
    recent = [t for t in login_failures.get(key, []) if (current - t).total_seconds() < 600]
    if len(recent) >= 10: raise HTTPException(429, "登录尝试过于频繁，请稍后再试")
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.active or not check_password(payload.password, user.password_hash):
        recent.append(current)
        login_failures[key] = recent
        if len(login_failures) > 10000:
            oldest_key = min(login_failures, key=lambda item: login_failures[item][-1])
            login_failures.pop(oldest_key, None)
        raise HTTPException(401, "账号或密码错误")
    login_failures.pop(key, None)
    token = secrets.token_urlsafe(32)
    db.query(UserSession).filter(UserSession.expires_at <= current).delete(synchronize_session=False)
    db.add(UserSession(user_id=user.id, token_hash=session_token_hash(token), created_at=current, expires_at=current + SESSION_TTL))
    user.last_login = current
    audit(db,user,"login","session",str(user.id),{"role":user.role})
    db.commit()
    response.set_cookie("shower_session", token, max_age=int(SESSION_TTL.total_seconds()), httponly=True, samesite="lax", secure=COOKIE_SECURE)
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(response: Response, session: str | None = Cookie(default=None, alias="shower_session"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if session:
        db.query(UserSession).filter(UserSession.token_hash == session_token_hash(session), UserSession.user_id == user.id).update(
            {UserSession.revoked_at: now()}, synchronize_session=False
        )
    audit(db,user,"logout","session",str(user.id),{"role":user.role}); db.commit(); response.delete_cookie("shower_session"); return {"ok": True}


@app.get("/api/health")
def health(): return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)): return {"username": user.username, "role": user.role}


@app.get("/api/catalog/bodies")
def catalog_bodies(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """主体已并入配件表，保留此接口便于旧客户端按主体列表读取。"""
    return [public_accessory(x) for x in db.scalars(select(Accessory).where(Accessory.active, Accessory.category == BODY_CATEGORY).order_by(Accessory.id)).all()]


@app.get("/api/catalog/accessories")
def catalog_accessories(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [public_accessory(x) for x in db.scalars(select(Accessory).where(Accessory.active, Accessory.category != BODY_CATEGORY).order_by(Accessory.category, Accessory.id)).all()]


@app.get("/api/catalog/accessory-schema")
def accessory_schema(_: User = Depends(current_user)):
    """返回配件类别字段定义；不包含成本等管理员字段。"""
    return ACCESSORY_CATEGORY_SCHEMAS


@app.get("/api/catalog/accessory-categories")
def accessory_categories(_: User = Depends(current_user)):
    """返回正式的配件类别目录，便于前端在没有产品记录时仍展示类别。"""
    return [
        {"category": item["category"], "note": item.get("note", ""), "field_count": len(item.get("fields", []))}
        for item in ACCESSORY_CATEGORY_SCHEMAS
    ]


@app.get("/api/catalog/bundles")
def catalog_bundles(q: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    bundles = db.scalars(select(Bundle).where(Bundle.active).order_by(Bundle.id.desc())).all()
    needle = q.strip().lower()
    result = []
    for bundle in bundles:
        item_rows = _bundle_items(db, bundle.id)
        body = db.get(Accessory, bundle.body_id)
        accessories = [db.get(Accessory, item.accessory_id) for item in item_rows]
        haystack = " ".join([bundle.name, bundle.code or "", bundle.description or "", body.name if body else "", body.model if body else "", *[f"{x.name} {x.model}" for x in accessories if x]])
        if needle and needle not in haystack.lower():
            continue
        result.append({"id": bundle.id, "name": bundle.name, "code": bundle.code or "", "description": bundle.description or "", "image_url": bundle.image_url or "", "version": bundle.version, "body": public_accessory(body) if body else None, "item_count": len(item_rows)})
    return result


@app.get("/api/catalog/bundles/{bundle_id}")
def catalog_bundle_detail(bundle_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    bundle = db.scalar(select(Bundle).where(Bundle.id == bundle_id, Bundle.active))
    if not bundle:
        raise HTTPException(404, "套装不存在或已停用")
    return public_bundle(db, bundle, include_replacements=True)


@app.get("/api/pricing-defaults")
def pricing_defaults(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """员工报价页的初始值；员工仍可在每次报价中覆盖，不会写回这里。"""
    settings = db.get(PricingSettings, 1)
    return {"multiplier": str(settings.multiplier), "labor_fee": str(settings.labor_fee)}


def calculate(payload: QuoteIn, db: Session, private: bool = False) -> dict[str, Any]:
    body = db.scalar(select(Accessory).where(Accessory.id == payload.body_id, Accessory.active, Accessory.category == BODY_CATEGORY))
    if not body: raise HTTPException(400, "主体不存在或已停用")
    settings = db.get(PricingSettings, 1)
    ids = [x.accessory_id for x in payload.lines]; rows = {x.id:x for x in db.scalars(select(Accessory).where(Accessory.id.in_(ids), Accessory.active)).all()}
    if len(rows) != len(set(ids)): raise HTTPException(400, "存在不存在或已停用的配件")
    # 报价参数可以由员工针对当前套装覆盖；旧请求未携带时沿用后台默认值。
    multiplier = payload.multiplier if payload.multiplier is not None else settings.multiplier
    labor_fee = payload.labor_fee if payload.labor_fee is not None else settings.labor_fee
    accessory_total = Decimal("0"); lines = []
    for line in payload.lines:
        row = rows[line.accessory_id]; qty = Decimal(line.quantity)
        if row.category == BODY_CATEGORY: raise HTTPException(400, f"{row.name} 是主体，不能作为配件计价")
        if qty < row.min_qty or qty > row.max_qty: raise HTTPException(400, f"{row.name} 数量需在 {row.min_qty} 到 {row.max_qty} 之间")
        line_cost = row.cost * qty; accessory_total += line_cost
        item = {"accessory_id":row.id,"name":row.name,"model":row.model,"quantity":str(qty)}
        if private: item["line_cost"] = str(rounded(line_cost))
        lines.append(item)
    subtotal = body.cost + accessory_total + labor_fee
    unit_price = rounded(subtotal * multiplier)
    final = rounded(unit_price * payload.set_quantity)
    result = {"body":{"id":body.id,"name":body.name,"model":body.model},"lines":lines,"set_quantity":payload.set_quantity,"unit_price":str(unit_price),"final_price":str(final),"quote_valid_days":settings.quote_valid_days,"pricing":{"multiplier":str(multiplier),"labor_fee":str(labor_fee)}}
    if private: result["private"] = {"body_cost":str(rounded(body.cost)),"accessory_total":str(rounded(accessory_total)),"labor_fee":str(rounded(labor_fee)),"subtotal":str(rounded(subtotal)),"multiplier":str(multiplier),"unit_price":str(unit_price),"set_quantity":payload.set_quantity,"final_price":str(final)}
    return result


def calculate_bundle(payload: BundleQuoteIn, db: Session, private: bool = False) -> dict[str, Any]:
    bundle = db.get(Bundle, payload.bundle_id)
    if not bundle or not bundle.active:
        raise HTTPException(400, "套装不存在或已停用")
    original_body = db.scalar(select(Accessory).where(Accessory.id == bundle.body_id, Accessory.category == BODY_CATEGORY))
    if not original_body:
        raise HTTPException(400, "套装主体不存在或已停用")
    selected_body_id = payload.body_id or bundle.body_id
    body = db.scalar(select(Accessory).where(Accessory.id == selected_body_id, Accessory.active, Accessory.category == BODY_CATEGORY))
    if not body:
        raise HTTPException(400, "替换主体不存在或已停用")
    items = _bundle_items(db, bundle.id)
    by_id = {item.id: item for item in items}
    if set(by_id) != {line.bundle_item_id for line in payload.lines} or len(payload.lines) != len(items):
        raise HTTPException(400, "报价明细必须完整对应套装配件")
    accessory_ids = [line.accessory_id for line in payload.lines]
    rows = {x.id: x for x in db.scalars(select(Accessory).where(Accessory.id.in_(accessory_ids), Accessory.active)).all()}
    if len(rows) != len(set(accessory_ids)):
        raise HTTPException(400, "存在不存在或已停用的报价配件")
    replacements: list[dict[str, Any]] = []
    if body.id != original_body.id:
        replacements.append({
            "bundle_item_id": None,
            "original_accessory_id": original_body.id,
            "original_name": original_body.name,
            "replacement_accessory_id": body.id,
            "replacement_name": body.name,
            "category": BODY_CATEGORY,
        })
    legacy_lines: list[LineIn] = []
    original_items: list[dict[str, Any]] = []
    for line in payload.lines:
        original = by_id[line.bundle_item_id]
        target = rows[line.accessory_id]
        original_accessory = db.get(Accessory, original.accessory_id)
        if not original_accessory or target.category != original_accessory.category:
            raise HTTPException(400, "替换物料必须与原物料属于同一类别")
        qty = Decimal(line.quantity)
        if qty < target.min_qty or qty > target.max_qty:
            raise HTTPException(400, f"{target.name} 数量需在 {target.min_qty} 到 {target.max_qty} 之间")
        legacy_lines.append(LineIn(accessory_id=target.id, quantity=qty))
        original_items.append({"bundle_item_id": original.id, "accessory_id": original_accessory.id, "name": original_accessory.name, "model": original_accessory.model, "category": original_accessory.category, "quantity": str(original.quantity), "position": original.position})
        if target.id != original_accessory.id:
            replacements.append({"bundle_item_id": original.id, "original_accessory_id": original_accessory.id, "original_name": original_accessory.name, "replacement_accessory_id": target.id, "replacement_name": target.name, "category": target.category})
    result = calculate(QuoteIn(body_id=body.id, lines=legacy_lines, set_quantity=payload.set_quantity, multiplier=payload.multiplier, labor_fee=payload.labor_fee), db, private=private)
    for result_line, source_line in zip(result.get("lines", []), payload.lines):
        result_line["bundle_item_id"] = source_line.bundle_item_id
    result["bundle"] = {"id": bundle.id, "name": bundle.name, "code": bundle.code or "", "version": bundle.version, "description": bundle.description or "", "image_url": bundle.image_url or ""}
    result["original_bundle_items"] = original_items
    result["replacements"] = replacements
    if private:
        result["private"]["bundle_id"] = str(bundle.id)
        result["private"]["bundle_version"] = str(bundle.version)
    return result


def quote_status(quote: Quote) -> str:
    valid_until = quote.valid_until
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    return "expired" if quote.status in ("saved", "active") and valid_until < now() else quote.status


def parse_quote_payload(data: dict[str, Any]) -> QuoteIn | BundleQuoteIn:
    if "bundle_id" in data:
        return BundleQuoteIn.model_validate(data)
    return QuoteIn.model_validate(data)


@app.post("/api/quotes/preview")
def quote_preview(payload: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    parsed = parse_quote_payload(payload)
    if isinstance(parsed, QuoteIn) and user.role != "admin":
        raise HTTPException(403, "员工只能从启用的预设套装报价")
    return calculate_bundle(parsed, db) if isinstance(parsed, BundleQuoteIn) else calculate(parsed, db)


@app.post("/api/quotes")
def create_quote(payload: dict[str, Any] | QuoteIn | BundleQuoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    parsed = parse_quote_payload(payload) if isinstance(payload, dict) else payload
    return _create_quote(parsed, user, db)


def _create_quote(parsed: QuoteIn | BundleQuoteIn, user: User, db: Session, *, allow_legacy: bool = False):
    if isinstance(parsed, QuoteIn) and user.role != "admin" and not allow_legacy:
        raise HTTPException(403, "员工只能从启用的预设套装报价")
    result = calculate_bundle(parsed, db) if isinstance(parsed, BundleQuoteIn) else calculate(parsed, db)
    private = calculate_bundle(parsed, db, private=True) if isinstance(parsed, BundleQuoteIn) else calculate(parsed, db, private=True)
    created = now(); valid = created + timedelta(days=db.get(PricingSettings,1).quote_valid_days); no = f"Q{created.strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000):03d}"
    snapshot = {**result, "private": private["private"], "private_lines": private["lines"]}; quote = Quote(quote_no=no, created_by=user.id, created_by_name_snapshot=user.username, created_at=created, valid_until=valid, status="saved", final_price=Decimal(result["final_price"]), snapshot=snapshot); db.add(quote); audit(db,user,"create","quote",no,{"final_price":result["final_price"],"bundle_id":result.get("bundle",{}).get("id"),"replacements":result.get("replacements",[])}); 
    if result.get("replacements"):
        audit(db,user,"replace","bundle",str(result["bundle"]["id"]),{"bundle_id":result["bundle"]["id"],"replacements":result["replacements"],"quote_no":no},target_label=result["bundle"]["name"])
    db.commit()
    return {"quote_no":no,"created_at":created.isoformat(),"valid_until":valid.isoformat(),"status":"saved","set_quantity":result["set_quantity"],"unit_price":result["unit_price"],"final_price":result["final_price"],"body":result["body"],"lines":result["lines"]}


def public_quote(quote: Quote) -> dict[str, Any]:
    snapshot = dict(quote.snapshot or {}); snapshot.pop("private",None); snapshot.pop("private_lines",None)
    for line in snapshot.get("lines",[]): line.pop("line_cost",None)
    return {"quote_no":quote.quote_no,"created_at":quote.created_at.isoformat(),"valid_until":quote.valid_until.isoformat(),"status":quote_status(quote),**snapshot}


@app.get("/api/quotes")
def list_quotes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Quote).where(Quote.created_by==user.id).order_by(Quote.id.desc())).all()
    return [{**_quote_summary(x)} for x in rows]


def _quote_summary(quote: Quote) -> dict[str, Any]:
    """报价列表只回传摘要；套装名与替换次数来自保存时的快照，原套装被改动也不受影响。"""
    snapshot = quote.snapshot or {}
    bundle = snapshot.get("bundle") or {}
    body = snapshot.get("body") or {}
    set_quantity = int(snapshot.get("set_quantity") or 1)
    return {
        "quote_no": quote.quote_no,
        "created_at": quote.created_at.isoformat(),
        "valid_until": quote.valid_until.isoformat(),
        "status": quote_status(quote),
        "set_quantity": set_quantity,
        "unit_price": snapshot.get("unit_price") or str(quote.final_price),
        "final_price": str(quote.final_price),
        "bundle_name": bundle.get("name") or "",
        "body_name": body.get("name") or "",
        "replacement_count": len(snapshot.get("replacements") or []),
    }


@app.get("/api/quotes/{quote_no}")
def get_quote(quote_no: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quote = db.scalar(select(Quote).where(Quote.quote_no==quote_no, Quote.created_by==user.id));
    if not quote: raise HTTPException(404,"报价单不存在")
    return public_quote(quote)


@app.post("/api/quotes/{quote_no}/duplicate")
def duplicate_quote(quote_no: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quote = db.scalar(select(Quote).where(Quote.quote_no==quote_no, Quote.created_by==user.id));
    if not quote: raise HTTPException(404,"报价单不存在")
    snap = quote.snapshot
    set_quantity = int(snap.get("set_quantity") or 1)
    private = snap.get("private") or {}
    multiplier = Decimal(private["multiplier"]) if private.get("multiplier") is not None else None
    labor_fee = Decimal(private["labor_fee"]) if private.get("labor_fee") is not None else None
    if snap.get("bundle", {}).get("id"):
        payload = BundleQuoteIn(bundle_id=int(snap["bundle"]["id"]), body_id=int(snap.get("body", {}).get("id")) if snap.get("body", {}).get("id") else None, lines=[BundleLineIn(bundle_item_id=int(x["bundle_item_id"]), accessory_id=int(x["accessory_id"]), quantity=Decimal(x["quantity"])) for x in snap.get("lines", [])], set_quantity=set_quantity, multiplier=multiplier, labor_fee=labor_fee)
    else:
        payload = QuoteIn(body_id=snap["body"]["id"], lines=[LineIn(accessory_id=x["accessory_id"],quantity=Decimal(x["quantity"])) for x in snap.get("lines",[])], set_quantity=set_quantity, multiplier=multiplier, labor_fee=labor_fee)
    return _create_quote(payload, user, db, allow_legacy=True)


def settings_json(s: PricingSettings):
    return {"multiplier":str(s.multiplier),"labor_fee":str(s.labor_fee),"quote_valid_days":s.quote_valid_days}


def quote_settings_json(s: PricingSettings):
    return {"quote_valid_days": s.quote_valid_days}


@app.get("/api/admin/pricing-settings")
def get_settings(_: User=Depends(admin_user), db: Session=Depends(get_db)): return settings_json(db.get(PricingSettings,1))


@app.patch("/api/admin/pricing-settings")
def update_settings(payload: SettingsIn, user: User=Depends(admin_user), db: Session=Depends(get_db)):
    s=db.get(PricingSettings,1); s.multiplier=payload.multiplier; s.labor_fee=payload.labor_fee; s.quote_valid_days=payload.quote_valid_days; s.updated_at=now(); audit(db,user,"update","settings","1",settings_json(s)); db.commit(); return settings_json(s)


@app.get("/api/admin/quote-settings")
def get_quote_settings(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return quote_settings_json(db.get(PricingSettings, 1))


@app.patch("/api/admin/quote-settings")
def update_quote_settings(payload: QuoteSettingsIn, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    settings = db.get(PricingSettings, 1)
    settings.quote_valid_days = payload.quote_valid_days
    settings.updated_at = now()
    audit(db, user, "update", "settings", "1", quote_settings_json(settings))
    db.commit()
    return quote_settings_json(settings)


@app.get("/api/admin/bundles")
def admin_bundles(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [private_bundle(db, bundle) for bundle in db.scalars(select(Bundle).order_by(Bundle.id.desc())).all()]


def save_bundle(bundle: Bundle, payload: BundleIn, user: User, db: Session, action: str) -> dict[str, Any]:
    if not payload.name.strip():
        raise HTTPException(422, "套装名称不能只有空白字符")
    body, accessories = validate_bundle_payload(payload, db, bundle.id if bundle.id else None)
    old_image_url = bundle.image_url
    bundle.name = payload.name.strip()
    bundle.code = payload.code.strip()
    bundle.description = payload.description.strip()
    bundle.image_url = payload.image_url.strip()
    bundle.body_id = body.id
    bundle.active = payload.active
    bundle.version = (bundle.version or 0) + (1 if action == "update" else 0)
    bundle.updated_at = now()
    if action == "create":
        db.add(bundle); db.flush()
    db.query(BundleItem).filter(BundleItem.bundle_id == bundle.id).delete(synchronize_session=False)
    for item in payload.items:
        db.add(BundleItem(bundle_id=bundle.id, accessory_id=item.accessory_id, quantity=item.quantity, position=item.position))
    audit(db, user, action, "bundle", str(bundle.id), {"name": bundle.name, "code": bundle.code, "body_id": bundle.body_id, "image_url": bundle.image_url, "items": [item.model_dump() for item in payload.items], "active": bundle.active})
    db.commit(); db.refresh(bundle)
    if old_image_url and old_image_url != bundle.image_url:
        remove_uploaded_file(old_image_url, db)
    return private_bundle(db, bundle)


@app.post("/api/admin/bundles")
def create_bundle(payload: BundleIn, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    return save_bundle(Bundle(version=1), payload, user, db, "create")


@app.patch("/api/admin/bundles/{bundle_id}")
def update_bundle(bundle_id: int, payload: BundleIn, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    bundle = db.get(Bundle, bundle_id)
    if not bundle: raise HTTPException(404, "套装不存在")
    return save_bundle(bundle, payload, user, db, "update")


@app.delete("/api/admin/bundles/{bundle_id}")
def delete_bundle(bundle_id: int, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    bundle = db.get(Bundle, bundle_id)
    if not bundle: raise HTTPException(404, "套装不存在")
    label = bundle.name
    old_image_url = bundle.image_url
    mark_target_deleted(db, "bundle", str(bundle.id), label)
    audit(db, user, "delete", "bundle", str(bundle.id), {"name": bundle.name}, target_label=label, target_deleted=True)
    db.query(BundleItem).filter(BundleItem.bundle_id == bundle.id).delete(synchronize_session=False)
    db.delete(bundle); db.commit()
    remove_uploaded_file(old_image_url, db)
    return {"ok": True, "deleted": True, "id": bundle_id}


def accessory_audit_target(row: Accessory | AccessoryIn) -> str:
    return "body" if row.category == BODY_CATEGORY else "accessory"


@app.get("/api/admin/bodies")
def admin_bodies(_: User=Depends(admin_user), db: Session=Depends(get_db)):
    """兼容旧客户端：主体已并入 accessories，这里只返回主体类别的记录。"""
    return [private_accessory(x) for x in db.scalars(select(Accessory).where(Accessory.category == BODY_CATEGORY).order_by(Accessory.id)).all()]


@app.get("/api/admin/accessories")
def admin_accessories(_: User=Depends(admin_user), db: Session=Depends(get_db)): return [private_accessory(x) for x in db.scalars(select(Accessory).order_by(Accessory.category,Accessory.id)).all()]


def accessory_values(payload: AccessoryIn) -> dict[str, Any]:
    if not payload.name.strip():
        raise HTTPException(422, "名称不能只有空白字符")
    if not payload.model.strip():
        raise HTTPException(422, "型号不能只有空白字符")
    values = payload.model_dump()
    values["name"] = payload.name.strip()
    values["model"] = payload.model.strip()
    values["category"] = payload.category.strip()
    if not values["category"]:
        raise HTTPException(400, "请选择配件类型")
    if values["category"] == BODY_CATEGORY:
        # 主体每套固定一个，不需要数量范围，也不保存属性字段。
        values.update(default_qty=Decimal("1"), min_qty=Decimal("1"), max_qty=Decimal("1"), attributes={})
    elif values["max_qty"] < values["min_qty"]:
        raise HTTPException(400, "最大数量不能小于最小数量")
    elif values["default_qty"] < values["min_qty"] or values["default_qty"] > values["max_qty"]:
        raise HTTPException(400, "默认数量必须在最小数量和最大数量之间")
    values["attributes"] = normalize_attribute_units(values["category"], values["attributes"])
    return values


@app.post("/api/admin/accessories")
def create_accessory(payload:AccessoryIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    values = accessory_values(payload)
    x=Accessory(**values,updated_at=now()); db.add(x); db.flush(); target=accessory_audit_target(x); audit(db,user,"create",target,str(x.id),values); db.commit(); return private_accessory(x)


@app.patch("/api/admin/accessories/{accessory_id}")
def update_accessory(accessory_id:int,payload:AccessoryIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    values = accessory_values(payload)
    x=db.get(Accessory,accessory_id)
    if not x: raise HTTPException(404,"配件不存在")
    item_refs = bundle_references_for_accessory(db, accessory_id)
    body_refs = bundle_references_for_body(db, accessory_id) if x.category == BODY_CATEGORY else []
    if x.category != values["category"] and (item_refs or body_refs):
        raise HTTPException(409, "配件仍被套装引用，无法修改类型：" + "、".join([*item_refs, *body_refs]))
    if x.active and not values["active"]:
        refs = [*item_refs, *body_refs]
        if refs: raise HTTPException(409, "主体/配件仍被套装引用，无法停用：" + "、".join(refs))
    if x.category != BODY_CATEGORY and values["category"] == x.category:
        conflicts = bundle_quantity_conflicts(db, accessory_id, values["min_qty"], values["max_qty"])
        if conflicts:
            raise HTTPException(409, "新的数量范围会使以下套装失效，请先调整套装数量：" + "、".join(conflicts))
    old_image_url=x.image_url
    for key,value in values.items(): setattr(x,key,value)
    x.version+=1; x.updated_at=now(); audit(db,user,"update",accessory_audit_target(x),str(accessory_id),values); db.commit()
    remove_uploaded_file(old_image_url, db)
    return private_accessory(x)


@app.delete("/api/admin/accessories/{accessory_id}")
def delete_accessory(accessory_id:int,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.get(Accessory,accessory_id)
    if not x: raise HTTPException(404,"配件不存在")
    refs = [*bundle_references_for_accessory(db, accessory_id)]
    if x.category == BODY_CATEGORY:
        refs += bundle_references_for_body(db, accessory_id)
    if refs: raise HTTPException(409, "主体/配件仍被套装引用，无法删除：" + "、".join(refs))
    old_image_url=x.image_url
    target=accessory_audit_target(x)
    mark_target_deleted(db,target,str(accessory_id),x.name)
    audit(db,user,"delete",target,str(accessory_id),{"name":x.name},target_label=x.name,target_deleted=True)
    db.delete(x); db.commit()
    remove_uploaded_file(old_image_url, db)
    return {"ok":True,"deleted":True,"id":accessory_id}


@app.get("/api/admin/users")
def admin_users(_:User=Depends(admin_user),db:Session=Depends(get_db)): return [{"id":x.id,"username":x.username,"role":x.role,"active":x.active,"last_login":x.last_login.isoformat() if x.last_login else None,"created_at":x.created_at.isoformat()} for x in db.scalars(select(User).order_by(User.id)).all()]


@app.post("/api/admin/users")
def create_user(payload:UserIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if not payload.password: raise HTTPException(400,"新账号必须设置密码")
    if len(payload.password) < 8: raise HTTPException(400,"密码至少需要 8 位")
    username = payload.username.strip()
    if len(username) < 3: raise HTTPException(400,"账号至少需要 3 个字符")
    if db.scalar(select(User).where(User.username==username)): raise HTTPException(409,"账号已存在")
    x=User(username=username,password_hash=hash_password(payload.password),role=payload.role,active=payload.active); db.add(x); db.flush(); audit(db,user,"create","user",str(x.id),{"username":x.username,"role":x.role}); db.commit(); return {"id":x.id,"username":x.username,"role":x.role,"active":x.active}


@app.patch("/api/admin/users/{user_id}")
def update_user(user_id:int,payload:UserIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if user_id==user.id and not payload.active: raise HTTPException(400,"不能停用当前登录账号")
    x=db.get(User,user_id)
    if not x: raise HTTPException(404,"账号不存在")
    if user_id == user.id and payload.role != "admin":
        raise HTTPException(400, "不能把当前登录账号降为员工")
    if x.role == "admin" and x.active and (not payload.active or payload.role != "admin"):
        lock_admin_mutations(db)
        active_admin_count = db.scalar(select(func.count(User.id)).where(User.role == "admin", User.active)) or 0
        if active_admin_count <= 1:
            raise HTTPException(409, "系统至少需要保留一个启用中的管理员")
    username = payload.username.strip()
    if len(username) < 3: raise HTTPException(400,"账号至少需要 3 个字符")
    duplicate = db.scalar(select(User).where(User.username == username, User.id != user_id))
    if duplicate: raise HTTPException(409,"账号已存在")
    role_changed = x.role != payload.role
    active_changed = x.active != payload.active
    x.username=username;x.role=payload.role;x.active=payload.active
    if payload.password:
        if len(payload.password) < 8: raise HTTPException(400,"密码至少需要 8 位")
        x.password_hash=hash_password(payload.password)
    if payload.password or role_changed or active_changed:
        revoke_user_sessions(db, x.id)
    audit(db,user,"update","user",str(user_id),{"username":x.username,"role":x.role,"active":x.active});db.commit();return {"ok":True}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id:int,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if user_id == user.id: raise HTTPException(400,"不能删除当前登录账号")
    x=db.get(User,user_id)
    if not x: raise HTTPException(404,"账号不存在")
    if x.role == "admin" and x.active:
        lock_admin_mutations(db)
        active_admin_count = db.scalar(select(func.count(User.id)).where(User.role == "admin", User.active)) or 0
        if active_admin_count <= 1:
            raise HTTPException(409,"不能删除最后一个启用中的管理员")
    username=x.username
    db.query(Quote).filter(Quote.created_by == user_id).update(
        {Quote.created_by: None, Quote.created_by_name_snapshot: username},
        synchronize_session=False,
    )
    db.query(AuditLog).filter(AuditLog.actor_id == user_id).update(
        {AuditLog.actor_id: None, AuditLog.actor_name_snapshot: username},
        synchronize_session=False,
    )
    mark_target_deleted(db,"user",str(user_id),username)
    audit(db,user,"delete","user",str(user_id),{"username":username},target_label=username,target_deleted=True)
    db.delete(x)
    db.commit()
    return {"ok":True,"deleted":True,"id":user_id}


@app.get("/api/admin/quotes")
def admin_quotes(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    users={x.id:x.username for x in db.scalars(select(User)).all()}
    return [{**_quote_summary(x),"username":x.created_by_name_snapshot or users.get(x.created_by) or "已删除账号"} for x in db.scalars(select(Quote).order_by(Quote.id.desc())).all()]


@app.get("/api/admin/quotes/{quote_no}")
def admin_quote_detail(quote_no:str,_:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.scalar(select(Quote).where(Quote.quote_no==quote_no));
    if not x: raise HTTPException(404,"报价单不存在")
    return {"quote_no":x.quote_no,"created_at":x.created_at.isoformat(),"valid_until":x.valid_until.isoformat(),"status":quote_status(x),**(x.snapshot or {})}


@app.post("/api/admin/quotes/{quote_no}/void")
def void_quote(quote_no:str,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.scalar(select(Quote).where(Quote.quote_no==quote_no));
    if not x: raise HTTPException(404,"报价单不存在")
    x.status="void";audit(db,user,"void","quote",quote_no);db.commit();return {"ok":True,"status":"void"}


@app.delete("/api/admin/quotes/{quote_no}")
def delete_quote(quote_no:str,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.scalar(select(Quote).where(Quote.quote_no==quote_no))
    if not x: raise HTTPException(404,"报价单不存在")
    mark_target_deleted(db,"quote",quote_no,quote_no)
    audit(db,user,"delete","quote",quote_no,{"final_price":str(x.final_price)},target_label=quote_no,target_deleted=True)
    db.delete(x); db.commit(); return {"ok":True,"deleted":True,"id":quote_no}


@app.post("/api/admin/quotes/bulk-delete")
def bulk_delete_quotes(payload: BulkQuoteDeleteIn, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    quote_nos = list(dict.fromkeys(item.strip() for item in payload.quote_nos if item.strip()))
    if not quote_nos:
        raise HTTPException(422, "请选择至少一张报价单")
    quotes = db.scalars(select(Quote).where(Quote.quote_no.in_(quote_nos))).all()
    if not quotes:
        raise HTTPException(404, "报价单不存在")
    for quote in quotes:
        mark_target_deleted(db, "quote", quote.quote_no, quote.quote_no)
        audit(db, user, "delete", "quote", quote.quote_no, {"final_price": str(quote.final_price)}, target_label=quote.quote_no, target_deleted=True)
        db.delete(quote)
    db.commit()
    return {"ok": True, "deleted": len(quotes), "ids": [quote.quote_no for quote in quotes]}


@app.get("/api/admin/audit-logs")
def audit_logs(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    users={x.id:x.username for x in db.scalars(select(User)).all()}
    actions={"create":"新增","update":"修改","delete":"删除","void":"作废","replace":"替换配件","upload":"上传","test":"试算","login":"登录","logout":"退出"}
    targets={"user":"账号","settings":"计价参数","body":"主体","accessory":"配件","bundle":"套装","quote":"报价单","image":"图片","pricing":"计价试算","session":"会话"}
    return [{"id":x.id,"username":x.actor_name_snapshot or users.get(x.actor_id) or "已删除账号","action":x.action,"action_label":actions.get(x.action,x.action),"target_type":x.target_type,"target_type_label":targets.get(x.target_type,x.target_type),"target_id":x.target_id,"target_label":x.target_label,"target_deleted":x.target_deleted,"detail":x.detail,"created_at":x.created_at.isoformat()} for x in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()]


@app.delete("/api/admin/audit-logs")
def clear_audit_logs(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    deleted=db.query(AuditLog).delete(synchronize_session=False)
    db.commit()
    return {"ok":True,"deleted":deleted}


@app.post("/api/admin/uploads")
def upload(request: Request, file:UploadFile=File(...),user:User=Depends(admin_user),db:Session=Depends(get_db)):
    allowed={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}
    data=file.file.read()
    if len(data)>5*1024*1024: raise HTTPException(400,"图片不能超过 5MB")
    # 先按文件头识别真实格式，再要求客户端声明与真实格式完全一致。
    detected = None
    if data.startswith(b"\xff\xd8\xff"): detected = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"): detected = "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP": detected = "image/webp"
    if detected is None:
        raise HTTPException(400,"无法识别图片格式")
    if file.content_type != detected:
        raise HTTPException(400,"文件内容与图片类型不一致")
    content_type = detected
    if content_type not in allowed: raise HTTPException(400,"只允许 JPG、PNG 或 WebP 图片")
    name=f"{secrets.token_urlsafe(16)}{allowed[content_type]}"; (UPLOAD_DIR/name).write_bytes(data)
    # 前端运行在 5173，图片由 8001 后端的 /uploads 提供，返回完整地址以确保能预览。
    audit(db,user,"upload","image",name,{"filename":file.filename or name,"content_type":content_type,"size":len(data)}); db.commit()
    return {"url":f"{str(request.base_url).rstrip('/')}/uploads/{name}"}


@app.delete("/api/admin/uploads/{filename}")
def delete_upload(filename:str,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    """清理尚未绑定到主体/配件的上传文件；已引用的图片禁止直接删除。"""
    name=upload_filename(f"/uploads/{filename}")
    if not name or name != filename:
        raise HTTPException(400,"无效的图片文件名")
    image_urls=[*db.scalars(select(Accessory.image_url).where(Accessory.image_url!="")).all(),*db.scalars(select(Bundle.image_url).where(Bundle.image_url!="")).all()]
    if any(upload_filename(url)==name for url in image_urls):
        raise HTTPException(409,"图片仍被配件或套装使用，不能删除")
    deleted=remove_uploaded_file(f"/uploads/{name}")
    if deleted:
        mark_target_deleted(db,"image",name,name)
        audit(db,user,"delete","image",name,{"reason":"unbound_upload_cleanup"},target_label=name,target_deleted=True)
        db.commit()
    return {"ok":True,"deleted":deleted,"id":name}


@app.post("/api/admin/pricing-test")
def pricing_test(payload:QuoteIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    result=calculate(payload,db,private=True)
    audit(db,user,"test","pricing",str(payload.body_id),{"final_price":result["final_price"],"line_count":len(payload.lines)})
    db.commit()
    return result

