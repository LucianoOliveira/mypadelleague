"""add address column to club table

Revision ID: 5055aa442094
Revises: 
Create Date: 2025-03-12 10:22:07.265557

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5055aa442094'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('tb_club', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cl_address', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('cl_active', sa.Boolean(), nullable=True))
        batch_op.drop_column('cl_location')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('tb_club', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cl_location', sa.VARCHAR(length=200), nullable=True))
        batch_op.drop_column('cl_active')
        batch_op.drop_column('cl_address')

    # ### end Alembic commands ###
