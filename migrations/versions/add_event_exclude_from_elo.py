"""Add ev_exclude_from_elo to tb_event

Revision ID: add_event_exclude_from_elo
Revises: add_player_club_nicknames, make_club_nullable
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_event_exclude_from_elo'
down_revision = ('add_player_club_nicknames', 'make_club_nullable')
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tb_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ev_exclude_from_elo', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('tb_event', schema=None) as batch_op:
        batch_op.drop_column('ev_exclude_from_elo')
