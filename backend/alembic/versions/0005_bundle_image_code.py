"""add bundle cover image and code"""

from alembic import op
import sqlalchemy as sa

revision = "0005_bundle_image_code"
down_revision = "0004_bundle_presets"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("bundles")}
    if "image_url" not in columns:
        op.add_column(
            "bundles",
            sa.Column("image_url", sa.String(length=500), nullable=False, server_default=""),
        )
    if "code" not in columns:
        op.add_column(
            "bundles",
            sa.Column("code", sa.String(length=80), nullable=False, server_default=""),
        )


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("bundles")}
    if "code" in columns:
        op.drop_column("bundles", "code")
    if "image_url" in columns:
        op.drop_column("bundles", "image_url")
