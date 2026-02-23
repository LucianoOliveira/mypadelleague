"""Merge event and pairing migrations

Revision ID: 7510713ab48a
Revises: add_event_id_to_games, add_pairing_type_to_events
Create Date: 2026-01-17 11:11:30.858875

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7510713ab48a'
down_revision = ('add_event_id_to_games', 'add_pairing_type_to_events')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
