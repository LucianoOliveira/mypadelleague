"""Add pairing type to events

Revision ID: add_pairing_type_to_events
Revises: 5ec9ac2964d2
Create Date: 2025-11-27 18:32:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_pairing_type_to_events'
down_revision = '5ec9ac2964d2'
branch_labels = None
depends_on = None


def upgrade():
    # Add the ev_pairing_type column to the tb_event table
    with op.batch_alter_table('tb_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ev_pairing_type', sa.String(length=20), nullable=True, default='Random'))
    
    # Update existing events to have default pairing type
    op.execute("UPDATE tb_event SET ev_pairing_type = 'Random' WHERE ev_pairing_type IS NULL")


def downgrade():
    # Remove the ev_pairing_type column from the tb_event table
    with op.batch_alter_table('tb_event', schema=None) as batch_op:
        batch_op.drop_column('ev_pairing_type')