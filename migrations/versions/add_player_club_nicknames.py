"""Add player_club_nickname table

Revision ID: add_player_club_nicknames
Revises: create_event_system
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_player_club_nicknames'
down_revision = 'create_event_system'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tb_player_nickname',
        sa.Column('pcn_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('pcn_user_id', sa.Integer, sa.ForeignKey('tb_users.us_id'), nullable=False),
        sa.Column('pcn_club_id', sa.Integer, sa.ForeignKey('tb_club.cl_id'), nullable=False),
        sa.Column('pcn_nickname', sa.String(50), nullable=False),
        sa.UniqueConstraint('pcn_user_id', 'pcn_club_id', name='uq_player_club_nickname'),
    )


def downgrade():
    op.drop_table('tb_player_nickname')
