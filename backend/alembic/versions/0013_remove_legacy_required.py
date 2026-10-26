"""remove the obsolete accessories.required column left by older deployments"""

from alembic import op
import sqlalchemy as sa


revision = "0013_remove_legacy_required"
down_revision = "0012_remove_freight"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("accessories")}
    if "required" in columns:
        op.drop_column("accessories", "required")


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("accessories")}
    if "required" not in columns:
        op.add_column(
            "accessories",
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
