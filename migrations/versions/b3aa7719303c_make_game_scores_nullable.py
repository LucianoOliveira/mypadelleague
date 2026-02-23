"""make_game_scores_nullable

Revision ID: b3aa7719303c
Revises: c8fab0a71abc
Create Date: 2026-01-17 11:27:29.383346

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3aa7719303c'
down_revision = 'c8fab0a71abc'
branch_labels = None
depends_on = None


def upgrade():
    # Update existing games to have null scores instead of 0
    # This indicates that games with 0 scores haven't been played yet
    connection = op.get_bind()
    
    # Set scores to NULL for games that likely haven't been played
    # (games with both scores as 0)
    connection.execute(sa.text("""
        UPDATE tb_game 
        SET gm_result_A = NULL, gm_result_B = NULL 
        WHERE gm_result_A = 0 AND gm_result_B = 0
    """))


def downgrade():
    # Set NULL scores back to 0 for downgrade
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE tb_game 
        SET gm_result_A = 0, gm_result_B = 0 
        WHERE gm_result_A IS NULL OR gm_result_B IS NULL
    """))
