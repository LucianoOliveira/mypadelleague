"""make event club_id nullable for public events

Revision ID: make_club_nullable
Revises: 
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'make_club_nullable'
down_revision = None  # Update this if you know the previous migration
branch_labels = None
depends_on = None


def upgrade():
    # Make ev_club_id nullable to support public events without clubs
    with op.batch_alter_table('tb_event', schema=None) as batch_op:
        batch_op.alter_column('ev_club_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)


def downgrade():
    # Revert ev_club_id to NOT NULL
    with op.batch_alter_table('tb_event', schema=None) as batch_op:
        batch_op.alter_column('ev_club_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
