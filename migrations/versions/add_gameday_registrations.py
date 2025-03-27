"""add gameday registration fields and table

Revision ID: add_gameday_registrations
Revises: add_registration_dates
Create Date: 2024-03-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_gameday_registrations'
down_revision = 'add_registration_dates'
branch_labels = None
depends_on = None

def upgrade():
    # Add registration dates to gameday table
    with op.batch_alter_table('tb_gameday', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gd_registration_start', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('gd_registration_end', sa.DateTime(timezone=True), nullable=True))

    # Create gameday registration table
    op.create_table('tb_gameday_registration',
        sa.Column('gdr_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('gdr_gameday_id', sa.Integer(), nullable=False),
        sa.Column('gdr_player_id', sa.Integer(), nullable=False),
        sa.Column('gdr_registered_by_id', sa.Integer(), nullable=False),
        sa.Column('gdr_registered_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['gdr_gameday_id'], ['tb_gameday.gd_id'], name='fk_gameday_registration_gameday'),
        sa.ForeignKeyConstraint(['gdr_player_id'], ['tb_users.us_id'], name='fk_gameday_registration_player'),
        sa.ForeignKeyConstraint(['gdr_registered_by_id'], ['tb_users.us_id'], name='fk_gameday_registration_registeredby'),
        sa.PrimaryKeyConstraint('gdr_id'),
        sa.UniqueConstraint('gdr_gameday_id', 'gdr_player_id', name='uq_gameday_player_registration')
    )

def downgrade():
    # Drop gameday registration table
    op.drop_table('tb_gameday_registration')
    
    # Drop registration date columns from gameday table
    with op.batch_alter_table('tb_gameday', schema=None) as batch_op:
        batch_op.drop_column('gd_registration_end')
        batch_op.drop_column('gd_registration_start')