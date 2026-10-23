"""merge handheld and top shower categories into 花洒喷头"""

from alembic import op
import sqlalchemy as sa

revision = "0006_merge_shower_categories"
down_revision = "0005_bundle_image_code"
branch_labels = None
depends_on = None


def upgrade():
    # 手喷与顶喷的字段定义完全相同，合并成一个类别不会丢失属性；
    # 套装明细按配件 ID 引用，类别改名不影响已有套装和报价快照。
    op.execute(sa.text("UPDATE accessories SET category = '花洒喷头' WHERE category IN ('手喷', '顶喷')"))


def downgrade():
    # 合并后无法可靠判断某条记录原来属于手喷还是顶喷，因此不做拆分。
    pass
