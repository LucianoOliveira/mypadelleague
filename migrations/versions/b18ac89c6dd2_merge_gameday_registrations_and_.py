"""merge gameday registrations and telephone column

Revision ID: b18ac89c6dd2
Revises: add_gameday_registrations, c407fd31e4c0
Create Date: 2025-03-19 21:19:19.002146

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b18ac89c6dd2'
down_revision = ('add_gameday_registrations', 'c407fd31e4c0')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
