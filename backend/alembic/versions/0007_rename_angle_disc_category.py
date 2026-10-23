"""rename 弯角角阀 category to 弯角角盘"""

from alembic import op
import sqlalchemy as sa

revision = "0007_rename_angle_disc_category"
down_revision = "0006_merge_shower_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("UPDATE accessories SET category = '弯角角盘' WHERE category = '弯角角阀'"))


def downgrade():
    op.execute(sa.text("UPDATE accessories SET category = '弯角角阀' WHERE category = '弯角角盘'"))
