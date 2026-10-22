from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
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
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


ROOT = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; configure a PostgreSQL connection in .env")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-only-change-me")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", ROOT / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="shower-pricing-session")
login_failures: dict[str, list[datetime]] = {}

# 配件类别字段来自公司当前的产品资料表。字段定义本身不含价格，
# 仅用于让管理员按类别录入结构化属性；实际属性值仍保存在 accessories.attributes JSON 中。
ACCESSORY_CATEGORY_SCHEMAS: list[dict[str, Any]] = [
    {
        "category": "杆子",
        "fields": [
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
            {"key": "安装方式", "label": "安装方式", "type": "text"},
            {"key": "表面处理", "label": "表面处理", "type": "text"},
            {"key": "适配杆径", "label": "适配杆径", "type": "text", "unit": "mm"},
        ],
    },
    {
        "category": "手喷",
        "fields": [
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "形状", "label": "形状", "type": "text"},
            {"key": "是否防爆", "label": "是否防爆", "type": "text"},
            {"key": "尺寸大小", "label": "尺寸大小", "type": "text", "unit": "mm"},
            {"key": "档位", "label": "档位", "type": "select", "options": ["无档", "一档", "二档", "三档", "四档"]},
        ],
    },
    {
        "category": "顶喷",
        "fields": [
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
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "长度", "label": "长度", "type": "text", "unit": "m"},
            {"key": "内芯", "label": "内芯", "type": "select", "options": ["铜芯", "不锈钢芯"]},
            {"key": "材质款式", "label": "材质款式", "type": "select", "options": ["PVC管", "波纹管"]},
        ],
    },
    {
        "category": "喷枪",
        "fields": [
            {"key": "材质", "label": "材质", "type": "text"},
            {"key": "颜色", "label": "颜色", "type": "text"},
            {"key": "档位", "label": "档位", "type": "select", "options": ["无档", "一档", "二档", "三档", "四档"]},
        ],
    },
    {
        "category": "弯角角阀",
        "fields": [
            {"key": "角阀颜色", "label": "角阀颜色", "type": "text"},
            {"key": "角阀形状", "label": "角阀形状", "type": "text"},
            {"key": "弯角型号", "label": "弯角型号（普通弯角/大置物弯角/加长弯角等）", "type": "text"},
            {"key": "弯角材质", "label": "弯角材质（铜弯角/304弯角等）", "type": "text"},
        ],
    },
]


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


class Body(Base):
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
    body_id: Mapped[int] = mapped_column(ForeignKey("bodies.id", ondelete="RESTRICT"), index=True)
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
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.13"))
    freight: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("30"))
    quote_valid_days: Mapped[int] = mapped_column(Integer, default=15)
    max_discount_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.20"))
    minimum_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
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
    username: str
    password: str


class LineIn(BaseModel):
    accessory_id: int
    quantity: Decimal = Field(default=Decimal("1"), ge=0)


class QuoteIn(BaseModel):
    body_id: int
    lines: list[LineIn] = Field(default_factory=list)
    discount_type: Literal["percent", "amount"] = "percent"
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)


class SettingsIn(BaseModel):
    multiplier: Decimal = Field(ge=1)
    labor_fee: Decimal = Field(ge=0)
    tax_rate_percent: Decimal = Field(ge=0, le=100)
    freight: Decimal = Field(ge=0)
    quote_valid_days: int = Field(ge=1, le=365)
    max_discount_percent: Decimal = Field(ge=0, le=100)
    minimum_price: Decimal = Field(ge=0)


class BodyIn(BaseModel):
    name: str
    model: str
    image_url: str = ""
    description: str = ""
    cost: Decimal = Field(ge=0)
    active: bool = True


class AccessoryIn(BaseModel):
    name: str
    model: str
    category: str
    image_url: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    cost: Decimal = Field(ge=0)
    default_qty: Decimal = Field(default=Decimal("0"), ge=0)
    min_qty: Decimal = Field(default=Decimal("0"), ge=0)
    max_qty: Decimal = Field(default=Decimal("99"), ge=0)
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
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    position: int = Field(default=1, ge=1)


class BundleIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(default="", max_length=80)
    description: str = ""
    image_url: str = ""
    body_id: int
    active: bool = True
    items: list[BundleItemIn] = Field(min_length=1)


class BundleLineIn(BaseModel):
    bundle_item_id: int
    accessory_id: int
    quantity: Decimal = Field(ge=0)


class BundleQuoteIn(BaseModel):
    bundle_id: int
    lines: list[BundleLineIn] = Field(min_length=1)
    discount_type: Literal["percent", "amount"] = "percent"
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)


app = FastAPI(title="星瀑计价平台", version="0.2.0")
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


def public_body(row: Body) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "model": row.model, "image_url": row.image_url, "description": row.description}


def public_accessory(row: Accessory) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "model": row.model, "category": row.category, "image_url": row.image_url, "attributes": row.attributes or {}, "default_qty": str(row.default_qty), "min_qty": str(row.min_qty), "max_qty": str(row.max_qty)}


def private_body(row: Body) -> dict[str, Any]:
    return {**public_body(row), "cost": str(rounded(row.cost)), "active": row.active, "version": row.version, "updated_at": row.updated_at.isoformat()}


def private_accessory(row: Accessory) -> dict[str, Any]:
    return {**public_accessory(row), "cost": str(rounded(row.cost)), "active": row.active, "version": row.version, "updated_at": row.updated_at.isoformat()}


def _bundle_items(db: Session, bundle_id: int) -> list[BundleItem]:
    return db.scalars(select(BundleItem).where(BundleItem.bundle_id == bundle_id).order_by(BundleItem.position, BundleItem.id)).all()


def private_bundle(db: Session, bundle: Bundle) -> dict[str, Any]:
    body = db.get(Body, bundle.body_id)
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
        "body": private_body(body) if body else None,
        "items": [{"id": i.id, "accessory": private_accessory(accessories[i.accessory_id]), "quantity": str(i.quantity), "position": i.position} for i in items if i.accessory_id in accessories],
    }


def public_bundle(db: Session, bundle: Bundle, *, include_replacements: bool = False) -> dict[str, Any]:
    body = db.get(Body, bundle.body_id)
    items = _bundle_items(db, bundle.id)
    accessories = {x.id: x for x in db.scalars(select(Accessory).where(Accessory.id.in_([i.accessory_id for i in items]))).all()} if items else {}
    result: dict[str, Any] = {
        "id": bundle.id,
        "name": bundle.name,
        "code": bundle.code or "",
        "description": bundle.description or "",
        "image_url": bundle.image_url or "",
        "version": bundle.version,
        "body": public_body(body) if body else None,
        "items": [{"id": i.id, "accessory": public_accessory(accessories[i.accessory_id]), "quantity": str(i.quantity), "position": i.position} for i in items if i.accessory_id in accessories],
    }
    if include_replacements:
        categories = sorted({accessories[i.accessory_id].category for i in items if i.accessory_id in accessories})
        candidates = db.scalars(select(Accessory).where(Accessory.active, Accessory.category.in_(categories)).order_by(Accessory.category, Accessory.id)).all() if categories else []
        result["replacement_candidates"] = {category: [public_accessory(x) for x in candidates if x.category == category] for category in categories}
    return result


def bundle_references_for_body(db: Session, body_id: int) -> list[str]:
    return [x.name for x in db.scalars(select(Bundle).where(Bundle.body_id == body_id).order_by(Bundle.name)).all()]


def bundle_references_for_accessory(db: Session, accessory_id: int) -> list[str]:
    return [x.name for x in db.scalars(select(Bundle).join(BundleItem, BundleItem.bundle_id == Bundle.id).where(BundleItem.accessory_id == accessory_id).order_by(Bundle.name)).all()]


def validate_bundle_payload(payload: BundleIn, db: Session, existing_id: int | None = None) -> tuple[Body, list[Accessory]]:
    body = db.get(Body, payload.body_id)
    if not body:
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
        if payload.active and not accessory.active:
            raise HTTPException(400, f"配件 {accessory.name} 已停用，不能启用套装")
        if item.quantity < accessory.min_qty or item.quantity > accessory.max_qty:
            raise HTTPException(400, f"{accessory.name} 数量需在 {accessory.min_qty} 到 {accessory.max_qty} 之间")
    return body, [accessories[x] for x in ids]


def current_user(session: str | None = Cookie(default=None, alias="shower_session"), db: Session = Depends(get_db)) -> User:
    if not session:
        raise HTTPException(401, "请先登录")
    try:
        payload = serializer.loads(session, max_age=60 * 60 * 12)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "登录已过期")
    user = db.get(User, int(payload.get("user_id", 0)))
    if not user or not user.active:
        raise HTTPException(401, "账号已停用")
    return user


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
        body_urls = db.scalars(select(Body.image_url).where(Body.image_url != "")).all()
        accessory_urls = db.scalars(select(Accessory.image_url).where(Accessory.image_url != "")).all()
        bundle_urls = db.scalars(select(Bundle.image_url).where(Bundle.image_url != "")).all()
        if any(upload_filename(url) == name for url in [*body_urls, *accessory_urls, *bundle_urls]):
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
    referenced={upload_filename(url) for url in [*db.scalars(select(Body.image_url).where(Body.image_url != "")).all(),*db.scalars(select(Accessory.image_url).where(Accessory.image_url != "")).all(),*db.scalars(select(Bundle.image_url).where(Bundle.image_url != "")).all()]}
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
    # 部署时可用环境变量指定首次登录密码，避免上线后还留着演示账号密码。
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD") or "admin123"
    employee_password = os.getenv("INITIAL_EMPLOYEE_PASSWORD") or "employee123"
    db.add_all([User(username="admin", password_hash=hash_password(admin_password), role="admin"), User(username="employee", password_hash=hash_password(employee_password), role="employee")])
    db.add(PricingSettings(id=1, multiplier=Decimal("1.5"), labor_fee=Decimal("80"), tax_rate=Decimal("0.13"), freight=Decimal("30"), quote_valid_days=15, max_discount_percent=Decimal("0.20"), minimum_price=Decimal("0")))
    bodies = [Body(name="星瀑花洒主体", model="SH-001", description="304不锈钢主体，适配多种出水组合", cost=Decimal("680")), Body(name="雾幕花洒主体", model="SH-002", description="圆润极简主体，适合现代卫浴空间", cost=Decimal("520"))]
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
    key = payload.username.lower(); recent = [t for t in login_failures.get(key, []) if (now() - t).seconds < 600]
    if len(recent) >= 10: raise HTTPException(429, "登录尝试过于频繁，请稍后再试")
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.active or not check_password(payload.password, user.password_hash):
        recent.append(now()); login_failures[key] = recent; raise HTTPException(401, "账号或密码错误")
    login_failures.pop(key, None); user.last_login = now(); audit(db,user,"login","session",str(user.id),{"role":user.role}); db.commit()
    response.set_cookie("shower_session", serializer.dumps({"user_id": user.id}), max_age=60*60*12, httponly=True, samesite="lax", secure=COOKIE_SECURE)
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(response: Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    audit(db,user,"logout","session",str(user.id),{"role":user.role}); db.commit(); response.delete_cookie("shower_session"); return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)): return {"username": user.username, "role": user.role}


@app.get("/api/catalog/bodies")
def catalog_bodies(_: User = Depends(current_user), db: Session = Depends(get_db)): return [public_body(x) for x in db.scalars(select(Body).where(Body.active).order_by(Body.id)).all()]


@app.get("/api/catalog/accessories")
def catalog_accessories(_: User = Depends(current_user), db: Session = Depends(get_db)): return [public_accessory(x) for x in db.scalars(select(Accessory).where(Accessory.active).order_by(Accessory.category, Accessory.id)).all()]


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
        body = db.get(Body, bundle.body_id)
        accessories = [db.get(Accessory, item.accessory_id) for item in item_rows]
        haystack = " ".join([bundle.name, bundle.description or "", body.name if body else "", body.model if body else "", *[f"{x.name} {x.model}" for x in accessories if x]])
        if needle and needle not in haystack.lower():
            continue
        result.append({"id": bundle.id, "name": bundle.name, "code": bundle.code or "", "description": bundle.description or "", "image_url": bundle.image_url or "", "version": bundle.version, "body": public_body(body) if body else None, "item_count": len(item_rows)})
    return result


@app.get("/api/catalog/bundles/{bundle_id}")
def catalog_bundle_detail(bundle_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    bundle = db.scalar(select(Bundle).where(Bundle.id == bundle_id, Bundle.active))
    if not bundle:
        raise HTTPException(404, "套装不存在或已停用")
    return public_bundle(db, bundle, include_replacements=True)


def calculate(payload: QuoteIn, db: Session, private: bool = False) -> dict[str, Any]:
    body = db.scalar(select(Body).where(Body.id == payload.body_id, Body.active))
    if not body: raise HTTPException(400, "主体不存在或已停用")
    settings = db.get(PricingSettings, 1)
    ids = [x.accessory_id for x in payload.lines]; rows = {x.id:x for x in db.scalars(select(Accessory).where(Accessory.id.in_(ids), Accessory.active)).all()}
    if len(rows) != len(set(ids)): raise HTTPException(400, "存在不存在或已停用的配件")
    accessory_total = Decimal("0"); lines = []
    for line in payload.lines:
        row = rows[line.accessory_id]; qty = Decimal(line.quantity)
        if qty < row.min_qty or qty > row.max_qty: raise HTTPException(400, f"{row.name} 数量需在 {row.min_qty} 到 {row.max_qty} 之间")
        line_cost = row.cost * qty; accessory_total += line_cost
        item = {"accessory_id":row.id,"name":row.name,"model":row.model,"quantity":str(qty)}
        if private: item["line_cost"] = str(rounded(line_cost))
        lines.append(item)
    subtotal = body.cost + accessory_total + settings.labor_fee; ex_tax = subtotal * settings.multiplier
    max_discount_amount = ex_tax * settings.max_discount_percent
    if payload.discount_type == "percent":
        if payload.discount_value > settings.max_discount_percent: raise HTTPException(400, "折扣超过管理员允许范围")
        discount = ex_tax * payload.discount_value
    else:
        discount = payload.discount_value
        if discount > max_discount_amount:
            raise HTTPException(400, f"固定金额折扣超过管理员允许上限，当前最多可减免 {rounded(max_discount_amount)} 元")
    discounted = max(Decimal("0"), ex_tax - discount)
    tax = discounted * settings.tax_rate; final = rounded(discounted + tax + settings.freight)
    if final < settings.minimum_price: raise HTTPException(400, "最终售价低于管理员设置的最低售价")
    result = {"body":{"id":body.id,"name":body.name,"model":body.model},"lines":lines,"discount_type":payload.discount_type,"discount_value":str(payload.discount_value),"final_price":str(final),"quote_valid_days":settings.quote_valid_days}
    if private: result["private"] = {"body_cost":str(rounded(body.cost)),"accessory_total":str(rounded(accessory_total)),"labor_fee":str(rounded(settings.labor_fee)),"subtotal":str(rounded(subtotal)),"multiplier":str(settings.multiplier),"ex_tax_price":str(rounded(ex_tax)),"max_discount_amount":str(rounded(max_discount_amount)),"discount_amount":str(rounded(discount)),"tax_rate":str(settings.tax_rate),"tax":str(rounded(tax)),"freight":str(rounded(settings.freight)),"final_price":str(final)}
    return result


def calculate_bundle(payload: BundleQuoteIn, db: Session, private: bool = False) -> dict[str, Any]:
    bundle = db.get(Bundle, payload.bundle_id)
    if not bundle or not bundle.active:
        raise HTTPException(400, "套装不存在或已停用")
    body = db.scalar(select(Body).where(Body.id == bundle.body_id, Body.active))
    if not body:
        raise HTTPException(400, "套装主体不存在或已停用")
    items = _bundle_items(db, bundle.id)
    by_id = {item.id: item for item in items}
    if set(by_id) != {line.bundle_item_id for line in payload.lines} or len(payload.lines) != len(items):
        raise HTTPException(400, "报价明细必须完整对应套装配件")
    accessory_ids = [line.accessory_id for line in payload.lines]
    rows = {x.id: x for x in db.scalars(select(Accessory).where(Accessory.id.in_(accessory_ids), Accessory.active)).all()}
    if len(rows) != len(set(accessory_ids)):
        raise HTTPException(400, "存在不存在或已停用的报价配件")
    replacements: list[dict[str, Any]] = []
    legacy_lines: list[LineIn] = []
    original_items: list[dict[str, Any]] = []
    for line in payload.lines:
        original = by_id[line.bundle_item_id]
        target = rows[line.accessory_id]
        original_accessory = db.get(Accessory, original.accessory_id)
        if not original_accessory or target.category != original_accessory.category:
            raise HTTPException(400, "替换配件必须与原配件属于同一类别")
        qty = Decimal(line.quantity)
        if qty < target.min_qty or qty > target.max_qty:
            raise HTTPException(400, f"{target.name} 数量需在 {target.min_qty} 到 {target.max_qty} 之间")
        legacy_lines.append(LineIn(accessory_id=target.id, quantity=qty))
        original_items.append({"bundle_item_id": original.id, "accessory_id": original_accessory.id, "name": original_accessory.name, "model": original_accessory.model, "category": original_accessory.category, "quantity": str(original.quantity), "position": original.position})
        if target.id != original_accessory.id:
            replacements.append({"bundle_item_id": original.id, "original_accessory_id": original_accessory.id, "original_name": original_accessory.name, "replacement_accessory_id": target.id, "replacement_name": target.name, "category": target.category})
    result = calculate(QuoteIn(body_id=body.id, lines=legacy_lines, discount_type=payload.discount_type, discount_value=payload.discount_value), db, private=private)
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
def quote_preview(payload: dict[str, Any], _: User = Depends(current_user), db: Session = Depends(get_db)):
    parsed = parse_quote_payload(payload)
    return calculate_bundle(parsed, db) if isinstance(parsed, BundleQuoteIn) else calculate(parsed, db)


@app.post("/api/quotes")
def create_quote(payload: dict[str, Any] | QuoteIn | BundleQuoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    parsed = parse_quote_payload(payload) if isinstance(payload, dict) else payload
    result = calculate_bundle(parsed, db) if isinstance(parsed, BundleQuoteIn) else calculate(parsed, db)
    private = calculate_bundle(parsed, db, private=True) if isinstance(parsed, BundleQuoteIn) else calculate(parsed, db, private=True)
    created = now(); valid = created + timedelta(days=db.get(PricingSettings,1).quote_valid_days); no = f"Q{created.strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000):03d}"
    snapshot = {**result, "private": private["private"], "private_lines": private["lines"]}; quote = Quote(quote_no=no, created_by=user.id, created_by_name_snapshot=user.username, created_at=created, valid_until=valid, status="saved", final_price=Decimal(result["final_price"]), snapshot=snapshot); db.add(quote); audit(db,user,"create","quote",no,{"final_price":result["final_price"],"bundle_id":result.get("bundle",{}).get("id"),"replacements":result.get("replacements",[])}); 
    if result.get("replacements"):
        audit(db,user,"replace","bundle",str(result["bundle"]["id"]),{"bundle_id":result["bundle"]["id"],"replacements":result["replacements"],"quote_no":no},target_label=result["bundle"]["name"])
    db.commit()
    return {"quote_no":no,"created_at":created.isoformat(),"valid_until":valid.isoformat(),"status":"saved","final_price":result["final_price"],"body":result["body"],"lines":result["lines"]}


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
    return {
        "quote_no": quote.quote_no,
        "created_at": quote.created_at.isoformat(),
        "valid_until": quote.valid_until.isoformat(),
        "status": quote_status(quote),
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
    if snap.get("bundle", {}).get("id"):
        payload = BundleQuoteIn(bundle_id=int(snap["bundle"]["id"]), lines=[BundleLineIn(bundle_item_id=int(x["bundle_item_id"]), accessory_id=int(x["accessory_id"]), quantity=Decimal(x["quantity"])) for x in snap.get("lines", [])], discount_type=snap.get("discount_type","percent"), discount_value=Decimal(snap.get("discount_value","0")))
    else:
        payload = QuoteIn(body_id=snap["body"]["id"], lines=[LineIn(accessory_id=x["accessory_id"],quantity=Decimal(x["quantity"])) for x in snap.get("lines",[])], discount_type=snap.get("discount_type","percent"), discount_value=Decimal(snap.get("discount_value","0")))
    return create_quote(payload,user,db)


def settings_json(s: PricingSettings):
    return {"multiplier":str(s.multiplier),"labor_fee":str(s.labor_fee),"tax_rate_percent":str(s.tax_rate*100),"freight":str(s.freight),"quote_valid_days":s.quote_valid_days,"max_discount_percent":str(s.max_discount_percent*100),"minimum_price":str(s.minimum_price)}


@app.get("/api/admin/pricing-settings")
def get_settings(_: User=Depends(admin_user), db: Session=Depends(get_db)): return settings_json(db.get(PricingSettings,1))


@app.patch("/api/admin/pricing-settings")
def update_settings(payload: SettingsIn, user: User=Depends(admin_user), db: Session=Depends(get_db)):
    s=db.get(PricingSettings,1); s.multiplier=payload.multiplier; s.labor_fee=payload.labor_fee; s.tax_rate=payload.tax_rate_percent/100; s.freight=payload.freight; s.quote_valid_days=payload.quote_valid_days; s.max_discount_percent=payload.max_discount_percent/100; s.minimum_price=payload.minimum_price; s.updated_at=now(); audit(db,user,"update","settings","1",settings_json(s)); db.commit(); return settings_json(s)


@app.get("/api/admin/bundles")
def admin_bundles(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [private_bundle(db, bundle) for bundle in db.scalars(select(Bundle).order_by(Bundle.id.desc())).all()]


def save_bundle(bundle: Bundle, payload: BundleIn, user: User, db: Session, action: str) -> dict[str, Any]:
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


@app.get("/api/admin/bodies")
def admin_bodies(_: User=Depends(admin_user), db: Session=Depends(get_db)): return [private_body(x) for x in db.scalars(select(Body).order_by(Body.id)).all()]


@app.post("/api/admin/bodies")
def create_body(payload: BodyIn, user: User=Depends(admin_user), db: Session=Depends(get_db)):
    x=Body(**payload.model_dump(),updated_at=now()); db.add(x); db.flush(); audit(db,user,"create","body",str(x.id),payload.model_dump()); db.commit(); return private_body(x)


@app.patch("/api/admin/bodies/{body_id}")
def update_body(body_id:int,payload:BodyIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.get(Body,body_id)
    if not x: raise HTTPException(404,"主体不存在")
    if x.active and not payload.active:
        refs = bundle_references_for_body(db, body_id)
        if refs: raise HTTPException(409, "主体仍被套装引用，无法停用：" + "、".join(refs))
    old_image_url=x.image_url
    for key,value in payload.model_dump().items(): setattr(x,key,value)
    x.version+=1; x.updated_at=now(); audit(db,user,"update","body",str(body_id),payload.model_dump()); db.commit()
    remove_uploaded_file(old_image_url, db)
    return private_body(x)


@app.delete("/api/admin/bodies/{body_id}")
def delete_body(body_id:int,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.get(Body,body_id)
    if not x: raise HTTPException(404,"主体不存在")
    refs = bundle_references_for_body(db, body_id)
    if refs: raise HTTPException(409, "主体仍被套装引用，无法删除：" + "、".join(refs))
    old_image_url=x.image_url
    mark_target_deleted(db,"body",str(body_id),x.name)
    audit(db,user,"delete","body",str(body_id),{"name":x.name},target_label=x.name,target_deleted=True)
    db.delete(x); db.commit()
    remove_uploaded_file(old_image_url, db)
    return {"ok":True,"deleted":True,"id":body_id}


@app.get("/api/admin/accessories")
def admin_accessories(_: User=Depends(admin_user), db: Session=Depends(get_db)): return [private_accessory(x) for x in db.scalars(select(Accessory).order_by(Accessory.category,Accessory.id)).all()]


@app.post("/api/admin/accessories")
def create_accessory(payload:AccessoryIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if payload.max_qty < payload.min_qty: raise HTTPException(400,"最大数量不能小于最小数量")
    x=Accessory(**payload.model_dump(),updated_at=now()); db.add(x); db.flush(); audit(db,user,"create","accessory",str(x.id),payload.model_dump()); db.commit(); return private_accessory(x)


@app.patch("/api/admin/accessories/{accessory_id}")
def update_accessory(accessory_id:int,payload:AccessoryIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if payload.max_qty < payload.min_qty: raise HTTPException(400,"最大数量不能小于最小数量")
    x=db.get(Accessory,accessory_id)
    if not x: raise HTTPException(404,"配件不存在")
    if x.active and not payload.active:
        refs = bundle_references_for_accessory(db, accessory_id)
        if refs: raise HTTPException(409, "配件仍被套装引用，无法停用：" + "、".join(refs))
    old_image_url=x.image_url
    for key,value in payload.model_dump().items(): setattr(x,key,value)
    x.version+=1; x.updated_at=now(); audit(db,user,"update","accessory",str(accessory_id),payload.model_dump()); db.commit()
    remove_uploaded_file(old_image_url, db)
    return private_accessory(x)


@app.delete("/api/admin/accessories/{accessory_id}")
def delete_accessory(accessory_id:int,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    x=db.get(Accessory,accessory_id)
    if not x: raise HTTPException(404,"配件不存在")
    refs = bundle_references_for_accessory(db, accessory_id)
    if refs: raise HTTPException(409, "配件仍被套装引用，无法删除：" + "、".join(refs))
    old_image_url=x.image_url
    mark_target_deleted(db,"accessory",str(accessory_id),x.name)
    audit(db,user,"delete","accessory",str(accessory_id),{"name":x.name},target_label=x.name,target_deleted=True)
    db.delete(x); db.commit()
    remove_uploaded_file(old_image_url, db)
    return {"ok":True,"deleted":True,"id":accessory_id}


@app.get("/api/admin/users")
def admin_users(_:User=Depends(admin_user),db:Session=Depends(get_db)): return [{"id":x.id,"username":x.username,"role":x.role,"active":x.active,"last_login":x.last_login.isoformat() if x.last_login else None,"created_at":x.created_at.isoformat()} for x in db.scalars(select(User).order_by(User.id)).all()]


@app.post("/api/admin/users")
def create_user(payload:UserIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if not payload.password: raise HTTPException(400,"新账号必须设置密码")
    if len(payload.password) < 8: raise HTTPException(400,"密码至少需要 8 位")
    if db.scalar(select(User).where(User.username==payload.username)): raise HTTPException(409,"账号已存在")
    x=User(username=payload.username,password_hash=hash_password(payload.password),role=payload.role,active=payload.active); db.add(x); db.flush(); audit(db,user,"create","user",str(x.id),{"username":x.username,"role":x.role}); db.commit(); return {"id":x.id,"username":x.username,"role":x.role,"active":x.active}


@app.patch("/api/admin/users/{user_id}")
def update_user(user_id:int,payload:UserIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if user_id==user.id and not payload.active: raise HTTPException(400,"不能停用当前登录账号")
    x=db.get(User,user_id)
    if not x: raise HTTPException(404,"账号不存在")
    x.username=payload.username;x.role=payload.role;x.active=payload.active
    if payload.password:
        if len(payload.password) < 8: raise HTTPException(400,"密码至少需要 8 位")
        x.password_hash=hash_password(payload.password)
    audit(db,user,"update","user",str(user_id),{"username":x.username,"role":x.role,"active":x.active});db.commit();return {"ok":True}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id:int,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    if user_id == user.id: raise HTTPException(400,"不能删除当前登录账号")
    x=db.get(User,user_id)
    if not x: raise HTTPException(404,"账号不存在")
    if x.role == "admin":
        admin_count = db.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0
        if admin_count <= 1:
            raise HTTPException(409,"不能删除最后一个管理员")
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
    # 浏览器通常会发送正确 MIME；部分 Windows 浏览器/开发工具会发 octet-stream，
    # 此时根据文件头和扩展名二次识别，仍只接受三种图片格式。
    detected = None
    if data.startswith(b"\xff\xd8\xff"): detected = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"): detected = "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP": detected = "image/webp"
    content_type = file.content_type if file.content_type in allowed else detected
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
    image_urls=[*db.scalars(select(Body.image_url).where(Body.image_url!="")).all(),*db.scalars(select(Accessory.image_url).where(Accessory.image_url!="")).all(),*db.scalars(select(Bundle.image_url).where(Bundle.image_url!="")).all()]
    if any(upload_filename(url)==name for url in image_urls):
        raise HTTPException(409,"图片仍被主体、配件或套装使用，不能删除")
    deleted=remove_uploaded_file(f"/uploads/{name}")
    if deleted:
        mark_target_deleted(db,"image",name,name)
        audit(db,user,"delete","image",name,{"reason":"unbound_upload_cleanup"},target_label=name,target_deleted=True)
        db.commit()
    return {"ok":True,"deleted":deleted,"id":name}


@app.post("/api/admin/pricing-test")
def pricing_test(payload:QuoteIn,user:User=Depends(admin_user),db:Session=Depends(get_db)):
    result=calculate(payload,db,private=True)
    audit(db,user,"test","pricing",str(payload.body_id),{"final_price":result["final_price"],"line_count":len(payload.lines),"discount_type":payload.discount_type})
    db.commit()
    return result

