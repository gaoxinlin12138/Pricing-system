"""drop freight from pricing settings"""

from alembic import op
import sqlalchemy as sa

revision = "0012_remove_freight"
down_revision = "0011_remove_min_price"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pricing_settings")}
    if "freight" in columns:
        op.drop_column("pricing_settings", "freight")


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pricing_settings")}
    if "freight" not in columns:
        op.add_column(
            "pricing_settings",
            sa.Column("freight", sa.Numeric(12, 2), nullable=False, server_default="30"),
        )
