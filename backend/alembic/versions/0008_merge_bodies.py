"""merge bodies into accessories as the 主体 category"""

from alembic import op
import sqlalchemy as sa

revision = "0008_merge_bodies"
down_revision = "0007_rename_angle_disc_category"
branch_labels = None
depends_on = None

BODY_CATEGORY = "主体"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("accessories")}
    if "description" not in columns:
        op.add_column(
            "accessories",
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
        )

    meta = sa.MetaData()
    bodies = sa.Table("bodies", meta, autoload_with=bind)
    accessories = sa.Table("accessories", meta, autoload_with=bind)
    bundles = sa.Table("bundles", meta, autoload_with=bind)
    quotes = sa.Table("quotes", meta, autoload_with=bind)
    # 某些旧库曾经给 accessories 增加过 required 非空字段，
    # 但当前模型已经移除它。迁移插入主体时先兼容旧列，完成合并后再清理。
    has_legacy_required = "required" in columns

    # 旧库的 accessories 自增序列可能落后于 MAX(id)（历史上用显式 id 导入过数据）。
    # 不先校准的话，下面插入主体会从 1 开始，直接撞 accessories_pkey。
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "SELECT setval("
                "pg_get_serial_sequence('accessories', 'id'), "
                "COALESCE((SELECT MAX(id) FROM accessories), 0) + 1, false)"
            )
        )

    # 旧主体按名称+型号映射到新配件；已存在同名主体时直接复用，保证迁移可重复执行。
    mapping: dict[int, int] = {}
    for row in bind.execute(sa.select(bodies)).mappings().all():
        existing_id = bind.execute(
            sa.select(accessories.c.id).where(
                accessories.c.category == BODY_CATEGORY,
                accessories.c.name == row["name"],
                accessories.c.model == row["model"],
            )
        ).scalar()
        if existing_id:
            mapping[row["id"]] = existing_id
            continue
        values = dict(
                name=row["name"],
                model=row["model"],
                category=BODY_CATEGORY,
                image_url=row["image_url"] or "",
                description=row["description"] or "",
                attributes={},
                cost=row["cost"],
                default_qty=1,
                min_qty=1,
                max_qty=1,
                active=row["active"],
                version=row["version"],
                updated_at=row["updated_at"],
            )
        if has_legacy_required:
            values["required"] = True
        mapping[row["id"]] = bind.execute(
            accessories.insert().values(**values).returning(accessories.c.id)
        ).scalar_one()

    # 旧外键指向 bodies，必须先解除，才能把 body_id 改写成新配件 id。
    if bind.dialect.name == "postgresql":
        for foreign_key in sa.inspect(bind).get_foreign_keys("bundles"):
            if foreign_key["constrained_columns"] == ["body_id"]:
                op.drop_constraint(foreign_key["name"], "bundles", type_="foreignkey")

    for old_id, new_id in mapping.items():
        bind.execute(bundles.update().where(bundles.c.body_id == old_id).values(body_id=new_id))

    # 历史报价把主体 id 存进了快照；不转换的话「复制报价」会指向错误的主体。
    for quote in bind.execute(sa.select(quotes.c.id, quotes.c.snapshot)).mappings().all():
        snapshot = dict(quote["snapshot"] or {})
        body = dict(snapshot.get("body") or {})
        if body.get("id") in mapping:
            body["id"] = mapping[body["id"]]
            snapshot["body"] = body
            bind.execute(quotes.update().where(quotes.c.id == quote["id"]).values(snapshot=snapshot))

    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "bundles_body_id_fkey",
            "bundles",
            "accessories",
            ["body_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    if has_legacy_required:
        op.drop_column("accessories", "required")


def downgrade():
    # 主体已与配件共用一张表，无法可靠区分哪些主体是迁移来的，因此不做拆分。
    pass
