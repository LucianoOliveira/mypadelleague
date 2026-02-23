"""Allow null values for league fields in game table

Revision ID: allow_null_league_fields
Revises: 7510713ab48a
Create Date: 2026-01-17 12:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'allow_null_league_fields'
down_revision = '7510713ab48a'
branch_labels = None
depends_on = None


def upgrade():
    # For SQLite, we need to recreate the table to change column constraints
    # Create new table with correct constraints
    op.execute('''
        CREATE TABLE tb_game_new (
            gm_id INTEGER NOT NULL PRIMARY KEY,
            gm_idLeague INTEGER NULL,
            gm_idGameDay INTEGER NULL,
            gm_idEvent INTEGER NULL,
            gm_date DATE,
            gm_timeStart TIME,
            gm_timeEnd TIME,
            gm_court INTEGER NULL,
            gm_idPlayer_A1 INTEGER,
            gm_idPlayer_A2 INTEGER,
            gm_idPlayer_B1 INTEGER,
            gm_idPlayer_B2 INTEGER,
            gm_result_A INTEGER DEFAULT 0,
            gm_result_B INTEGER DEFAULT 0,
            gm_teamA VARCHAR(10),
            gm_teamB VARCHAR(10),
            FOREIGN KEY(gm_idLeague) REFERENCES tb_league (lg_id),
            FOREIGN KEY(gm_idGameDay) REFERENCES tb_gameday (gd_id),
            FOREIGN KEY(gm_idEvent) REFERENCES tb_event (ev_id),
            FOREIGN KEY(gm_court) REFERENCES tb_court (ct_id),
            FOREIGN KEY(gm_idPlayer_A1) REFERENCES tb_users (us_id),
            FOREIGN KEY(gm_idPlayer_A2) REFERENCES tb_users (us_id),
            FOREIGN KEY(gm_idPlayer_B1) REFERENCES tb_users (us_id),
            FOREIGN KEY(gm_idPlayer_B2) REFERENCES tb_users (us_id)
        )
    ''')
    
    # Copy existing data only if games exist
    op.execute('''
        INSERT INTO tb_game_new 
        SELECT * FROM tb_game WHERE 1=0
    ''')
    
    # Drop old table and rename new one
    op.execute('DROP TABLE tb_game')
    op.execute('ALTER TABLE tb_game_new RENAME TO tb_game')


def downgrade():
    # Recreate with NOT NULL constraints (this will fail if there are NULL values)
    op.execute('''
        CREATE TABLE tb_game_new (
            gm_id INTEGER NOT NULL PRIMARY KEY,
            gm_idLeague INTEGER NOT NULL,
            gm_idGameDay INTEGER,
            gm_idEvent INTEGER,
            gm_date DATE,
            gm_timeStart TIME,
            gm_timeEnd TIME,
            gm_court INTEGER NOT NULL,
            gm_idPlayer_A1 INTEGER,
            gm_idPlayer_A2 INTEGER,
            gm_idPlayer_B1 INTEGER,
            gm_idPlayer_B2 INTEGER,
            gm_result_A INTEGER DEFAULT 0,
            gm_result_B INTEGER DEFAULT 0,
            gm_teamA VARCHAR(10),
            gm_teamB VARCHAR(10),
            FOREIGN KEY(gm_idLeague) REFERENCES tb_league (lg_id),
            FOREIGN KEY(gm_idGameDay) REFERENCES tb_gameday (gd_id),
            FOREIGN KEY(gm_idEvent) REFERENCES tb_event (ev_id),
            FOREIGN KEY(gm_court) REFERENCES tb_court (ct_id),
            FOREIGN KEY(gm_idPlayer_A1) REFERENCES tb_users (us_id),
            FOREIGN KEY(gm_idPlayer_A2) REFERENCES tb_users (us_id),
            FOREIGN KEY(gm_idPlayer_B1) REFERENCES tb_users (us_id),
            FOREIGN KEY(gm_idPlayer_B2) REFERENCES tb_users (us_id)
        )
    ''')
    
    op.execute('''
        INSERT INTO tb_game_new 
        SELECT * FROM tb_game
        WHERE gm_idLeague IS NOT NULL
    ''')
    
    op.execute('DROP TABLE tb_game')
    op.execute('ALTER TABLE tb_game_new RENAME TO tb_game')