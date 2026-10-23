"""drop minimum price from pricing settings"""

from alembic import op
import sqlalchemy as sa

revision = "0011_remove_min_price"
down_revision = "0010_remove_tax_discount"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pricing_settings")}
    if "minimum_price" in columns:
        op.drop_column("pricing_settings", "minimum_price")


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pricing_settings")}
    if "minimum_price" not in columns:
        op.add_column(
            "pricing_settings",
            sa.Column("minimum_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        )
