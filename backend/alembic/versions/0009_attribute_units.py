"""append missing units to numeric accessory attributes"""

import re

from alembic import op
import sqlalchemy as sa

revision = "0009_attribute_units"
down_revision = "0008_merge_bodies"
branch_labels = None
depends_on = None

NUMBER_ONLY = re.compile(r"\d+(?:\.\d+)?")
UNIT_FIELDS = {
    "杆子": {"厚度/重量": "mm", "长度": "mm"},
    "中叉+墙座": {"适配杆径": "mm"},
    "花洒喷头": {"尺寸大小": "mm"},
    "电话线": {"长度": "m"},
    "手喷软管": {"长度": "m"},
}


def upgrade():
    bind = op.get_bind()
    meta = sa.MetaData()
    accessories = sa.Table("accessories", meta, autoload_with=bind)
    for row in bind.execute(
        sa.select(accessories.c.id, accessories.c.category, accessories.c.attributes)
    ).mappings():
        attributes = dict(row["attributes"] or {})
        units = UNIT_FIELDS.get(row["category"], {})
        changed = False
        for key, unit in units.items():
            value = attributes.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if NUMBER_ONLY.fullmatch(text):
                attributes[key] = f"{text}{unit}"
                changed = True
            elif text != value:
                attributes[key] = text
                changed = True
        if changed:
            bind.execute(
                accessories.update().where(accessories.c.id == row["id"]).values(attributes=attributes)
            )


def downgrade():
    # 无法可靠区分“自动补的单位”和“用户自己填的单位”，因此不回退数据。
    pass
