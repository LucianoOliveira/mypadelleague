"""Add UpDown event type

Revision ID: add_updown_event_type
Revises: create_event_system, make_club_nullable
Create Date: 2026-03-05

Merges the two existing heads and adds the 'UpDown' (Sobe e Desce) event type.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'add_updown_event_type'
down_revision = ('create_event_system', 'make_club_nullable')
branch_labels = None
depends_on = None


def upgrade():
    # Insert the UpDown event type if it doesn't already exist
    conn = op.get_bind()
    existing = conn.execute(
        text("SELECT et_id FROM tb_event_types WHERE et_name = 'UpDown'")
    ).fetchone()

    if not existing:
        conn.execute(
            text(
                "INSERT INTO tb_event_types "
                "(et_name, et_description, et_order, et_has_config, et_is_active) "
                "VALUES ('UpDown', 'Sobe e Desce – winners move up, losers move down each round', 4, 0, 1)"
            )
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM tb_event_types WHERE et_name = 'UpDown'")
    )
