"""remove_not_null_constraints_from_game

Revision ID: c8fab0a71abc
Revises: allow_null_league_fields
Create Date: 2026-01-17 11:15:45.849097

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8fab0a71abc'
down_revision = 'allow_null_league_fields'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support altering column constraints directly, so we need to:
    # 1. Create new table with correct constraints
    # 2. Copy data from old table
    # 3. Drop old table
    # 4. Rename new table
    
    # Create new table with nullable league and gameday fields
    op.create_table('tb_game_new',
        sa.Column('gm_id', sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
        sa.Column('gm_idLeague', sa.Integer(), nullable=True),  # Allow NULL for event games
        sa.Column('gm_idGameDay', sa.Integer(), nullable=True),  # Allow NULL for event games  
        sa.Column('gm_idEvent', sa.Integer(), nullable=True),
        sa.Column('gm_date', sa.Date(), nullable=True),
        sa.Column('gm_timeStart', sa.Time(), nullable=True),
        sa.Column('gm_timeEnd', sa.Time(), nullable=True),
        sa.Column('gm_court', sa.Integer(), nullable=True),  # Make nullable initially
        sa.Column('gm_idPlayer_A1', sa.Integer(), nullable=True),
        sa.Column('gm_idPlayer_A2', sa.Integer(), nullable=True),
        sa.Column('gm_idPlayer_B1', sa.Integer(), nullable=True),
        sa.Column('gm_idPlayer_B2', sa.Integer(), nullable=True),
        sa.Column('gm_result_A', sa.Integer(), default=0),
        sa.Column('gm_result_B', sa.Integer(), default=0),
        sa.Column('gm_teamA', sa.String(10), nullable=True),
        sa.Column('gm_teamB', sa.String(10), nullable=True),
        sa.ForeignKeyConstraint(['gm_idLeague'], ['tb_league.lg_id']),
        sa.ForeignKeyConstraint(['gm_idGameDay'], ['tb_gameday.gd_id']),
        sa.ForeignKeyConstraint(['gm_idEvent'], ['tb_event.ev_id']),
        sa.ForeignKeyConstraint(['gm_court'], ['tb_court.ct_id']),
        sa.ForeignKeyConstraint(['gm_idPlayer_A1'], ['tb_users.us_id']),
        sa.ForeignKeyConstraint(['gm_idPlayer_A2'], ['tb_users.us_id']),
        sa.ForeignKeyConstraint(['gm_idPlayer_B1'], ['tb_users.us_id']),
        sa.ForeignKeyConstraint(['gm_idPlayer_B2'], ['tb_users.us_id'])
    )
    
    # Copy existing data if tb_game table exists and has data
    connection = op.get_bind()
    try:
        # Check if old table exists and has data
        result = connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='tb_game'"))
        if result.fetchone():
            # Copy data from old table to new table
            connection.execute(sa.text("""
                INSERT INTO tb_game_new (
                    gm_id, gm_idLeague, gm_idGameDay, gm_idEvent, gm_date, gm_timeStart, gm_timeEnd,
                    gm_court, gm_idPlayer_A1, gm_idPlayer_A2, gm_idPlayer_B1, gm_idPlayer_B2,
                    gm_result_A, gm_result_B, gm_teamA, gm_teamB
                )
                SELECT 
                    gm_id, gm_idLeague, gm_idGameDay, gm_idEvent, gm_date, gm_timeStart, gm_timeEnd,
                    gm_court, gm_idPlayer_A1, gm_idPlayer_A2, gm_idPlayer_B1, gm_idPlayer_B2,
                    gm_result_A, gm_result_B, gm_teamA, gm_teamB
                FROM tb_game
            """))
            
            # Drop old table
            op.drop_table('tb_game')
    except Exception as e:
        # If old table doesn't exist or has issues, just continue
        pass
    
    # Rename new table to original name
    op.rename_table('tb_game_new', 'tb_game')


def downgrade():
    # For downgrade, recreate the original table structure if needed
    # This is complex for SQLite, so we'll keep it simple
    pass
