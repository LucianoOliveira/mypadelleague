"""Add gm_idEvent column to tb_game table

Revision ID: add_event_id_to_games
Revises: 5ec9ac2964d2
Create Date: 2026-01-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_event_id_to_games'
down_revision = '5ec9ac2964d2'
branch_labels = None
depends_on = None


def upgrade():
    # Add gm_idEvent column to tb_game table
    with op.batch_alter_table('tb_game', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gm_idEvent', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_game_event', 'tb_event', ['gm_idEvent'], ['ev_id'])


def downgrade():
    # Remove gm_idEvent column from tb_game table
    with op.batch_alter_table('tb_game', schema=None) as batch_op:
        batch_op.drop_constraint('fk_game_event', type_='foreignkey')
        batch_op.drop_column('gm_idEvent')