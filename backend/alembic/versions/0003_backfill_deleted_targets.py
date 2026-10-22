"""mark historical audit targets that no longer exist"""

from alembic import op
from sqlalchemy import inspect


revision = "0003_backfill_deleted_targets"
down_revision = "0002_hard_delete_history"
branch_labels = None
depends_on = None


def upgrade():
    conditions = [
        "(target_type = 'quote' AND NOT EXISTS (SELECT 1 FROM quotes q WHERE q.quote_no = log.target_id))",
        "(target_type = 'user' AND target_id ~ '^[0-9]+$' AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = CAST(log.target_id AS INTEGER)))",
        "(target_type = 'body' AND target_id ~ '^[0-9]+$' AND NOT EXISTS (SELECT 1 FROM bodies b WHERE b.id = CAST(log.target_id AS INTEGER)))",
        "(target_type = 'accessory' AND target_id ~ '^[0-9]+$' AND NOT EXISTS (SELECT 1 FROM accessories a WHERE a.id = CAST(log.target_id AS INTEGER)))",
        "target_type = 'image'",
    ]
    if inspect(op.get_bind()).has_table("compatibility_rules"):
        conditions.insert(4, "(target_type = 'compatibility_rule' AND target_id ~ '^[0-9]+$' AND NOT EXISTS (SELECT 1 FROM compatibility_rules r WHERE r.id = CAST(log.target_id AS INTEGER)))")
    op.execute(f"""
        UPDATE audit_logs AS log
        SET target_deleted = TRUE,
            target_label = COALESCE(NULLIF(target_label, ''), target_id)
        WHERE action = 'delete'
          AND (
            {' OR '.join(conditions)}
          )
        """)


def downgrade():
    pass
