"""add preset bundles and retire compatibility rules"""

from alembic import op
import sqlalchemy as sa

revision = "0004_bundle_presets"
down_revision = "0003_backfill_deleted_targets"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("bundles"):
        op.create_table(
            "bundles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("body_id", sa.Integer(), sa.ForeignKey("bodies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    inspector = sa.inspect(bind)
    if not inspector.has_table("bundle_items"):
        op.create_table(
            "bundle_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("bundle_id", sa.Integer(), sa.ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("accessory_id", sa.Integer(), sa.ForeignKey("accessories.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False, server_default="1"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("bundle_id", "accessory_id", name="uq_bundle_accessory"),
        )
    if sa.inspect(bind).has_table("compatibility_rules"):
        op.drop_table("compatibility_rules")


def downgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("bundle_items"):
        op.drop_table("bundle_items")
    if sa.inspect(bind).has_table("bundles"):
        op.drop_table("bundles")
    if not sa.inspect(bind).has_table("compatibility_rules"):
        op.create_table(
            "compatibility_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rule_type", sa.String(length=20), nullable=False),
            sa.Column("source_accessory_id", sa.Integer(), sa.ForeignKey("accessories.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_accessory_id", sa.Integer(), sa.ForeignKey("accessories.id", ondelete="CASCADE"), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
