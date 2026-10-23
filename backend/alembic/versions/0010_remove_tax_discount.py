"""drop tax rate and max discount from pricing settings"""

from alembic import op
import sqlalchemy as sa

revision = "0010_remove_tax_discount"
down_revision = "0009_attribute_units"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pricing_settings")}
    if "tax_rate" in columns:
        op.drop_column("pricing_settings", "tax_rate")
    if "max_discount_percent" in columns:
        op.drop_column("pricing_settings", "max_discount_percent")


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("pricing_settings")}
    if "tax_rate" not in columns:
        op.add_column(
            "pricing_settings",
            sa.Column("tax_rate", sa.Numeric(8, 4), nullable=False, server_default="0.13"),
        )
    if "max_discount_percent" not in columns:
        op.add_column(
            "pricing_settings",
            sa.Column("max_discount_percent", sa.Numeric(8, 4), nullable=False, server_default="0.20"),
        )
