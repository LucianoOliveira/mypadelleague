"""Add us_hide_from_elo to tb_users

Revision ID: add_user_hide_from_elo
Revises: add_event_exclude_from_elo
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_user_hide_from_elo'
down_revision = 'add_event_exclude_from_elo'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tb_users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('us_hide_from_elo', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('tb_users', schema=None) as batch_op:
        batch_op.drop_column('us_hide_from_elo')
