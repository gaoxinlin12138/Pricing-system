"""support hard deletes while preserving historical snapshots"""

from alembic import op
import sqlalchemy as sa


revision = "0002_hard_delete_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS created_by_name_snapshot VARCHAR(60)")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_name_snapshot VARCHAR(60)")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_deleted BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_label VARCHAR(160)")

    op.execute(
        "UPDATE quotes q SET created_by_name_snapshot = u.username "
        "FROM users u WHERE q.created_by = u.id"
    )
    op.execute(
        "UPDATE audit_logs a SET actor_name_snapshot = u.username "
        "FROM users u WHERE a.actor_id = u.id"
    )
    op.execute("UPDATE audit_logs SET target_label = COALESCE(target_id, '') WHERE target_label IS NULL")

    op.drop_constraint("quotes_created_by_fkey", "quotes", type_="foreignkey")
    op.drop_constraint("audit_logs_actor_id_fkey", "audit_logs", type_="foreignkey")
    has_rules = sa.inspect(op.get_bind()).has_table("compatibility_rules")
    if has_rules:
        op.drop_constraint("compatibility_rules_source_accessory_id_fkey", "compatibility_rules", type_="foreignkey")
        op.drop_constraint("compatibility_rules_target_accessory_id_fkey", "compatibility_rules", type_="foreignkey")

    op.alter_column("quotes", "created_by", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key("quotes_created_by_fkey", "quotes", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("audit_logs_actor_id_fkey", "audit_logs", "users", ["actor_id"], ["id"], ondelete="SET NULL")
    if has_rules:
        op.create_foreign_key("compatibility_rules_source_accessory_id_fkey", "compatibility_rules", "accessories", ["source_accessory_id"], ["id"], ondelete="CASCADE")
        op.create_foreign_key("compatibility_rules_target_accessory_id_fkey", "compatibility_rules", "accessories", ["target_accessory_id"], ["id"], ondelete="CASCADE")
    op.alter_column("audit_logs", "target_deleted", server_default=None)


def downgrade():
    op.drop_constraint("quotes_created_by_fkey", "quotes", type_="foreignkey")
    op.drop_constraint("audit_logs_actor_id_fkey", "audit_logs", type_="foreignkey")
    has_rules = sa.inspect(op.get_bind()).has_table("compatibility_rules")
    if has_rules:
        op.drop_constraint("compatibility_rules_source_accessory_id_fkey", "compatibility_rules", type_="foreignkey")
        op.drop_constraint("compatibility_rules_target_accessory_id_fkey", "compatibility_rules", type_="foreignkey")
    op.create_foreign_key("quotes_created_by_fkey", "quotes", "users", ["created_by"], ["id"])
    op.create_foreign_key("audit_logs_actor_id_fkey", "audit_logs", "users", ["actor_id"], ["id"])
    if has_rules:
        op.create_foreign_key("compatibility_rules_source_accessory_id_fkey", "compatibility_rules", "accessories", ["source_accessory_id"], ["id"])
        op.create_foreign_key("compatibility_rules_target_accessory_id_fkey", "compatibility_rules", "accessories", ["target_accessory_id"], ["id"])
    op.drop_column("audit_logs", "target_label")
    op.drop_column("audit_logs", "target_deleted")
    op.drop_column("audit_logs", "actor_name_snapshot")
    op.drop_column("quotes", "created_by_name_snapshot")
