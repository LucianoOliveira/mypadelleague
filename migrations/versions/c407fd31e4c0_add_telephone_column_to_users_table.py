"""add_telephone_column_to_users_table

Revision ID: c407fd31e4c0
Revises: add_league_substitutes
Create Date: 2025-03-19 17:40:22.599371

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.schema import CreateTable, DropTable

# revision identifiers, used by Alembic.
revision = 'c407fd31e4c0'
down_revision = 'add_league_substitutes'
branch_labels = None
depends_on = None


def upgrade():
    # Create a new table with the desired schema
    op.execute('''
        CREATE TABLE tb_users_new (
            us_id INTEGER NOT NULL PRIMARY KEY,
            us_name VARCHAR(50) NOT NULL,
            us_email VARCHAR(200),
            us_pwd VARCHAR(150),
            us_birthday DATE,
            us_is_player BOOLEAN,
            us_is_manager BOOLEAN,
            us_is_admin BOOLEAN,
            us_is_superuser BOOLEAN,
            us_is_active BOOLEAN,
            us_telephone VARCHAR(20) UNIQUE
        )
    ''')
    
    # Copy data from the old table to the new table
    op.execute('''
        INSERT INTO tb_users_new (
            us_id, us_name, us_email, us_pwd, us_birthday,
            us_is_player, us_is_manager, us_is_admin,
            us_is_superuser, us_is_active
        )
        SELECT us_id, us_name, us_email, us_pwd, us_birthday,
               us_is_player, us_is_manager, us_is_admin,
               us_is_superuser, us_is_active
        FROM tb_users
    ''')
    
    # Drop the old table
    op.execute('DROP TABLE tb_users')
    
    # Rename the new table to the original name
    op.execute('ALTER TABLE tb_users_new RENAME TO tb_users')


def downgrade():
    # Create a new table without the telephone column
    op.execute('''
        CREATE TABLE tb_users_new (
            us_id INTEGER NOT NULL PRIMARY KEY,
            us_name VARCHAR(50) NOT NULL,
            us_email VARCHAR(200),
            us_pwd VARCHAR(150),
            us_birthday DATE,
            us_is_player BOOLEAN,
            us_is_manager BOOLEAN,
            us_is_admin BOOLEAN,
            us_is_superuser BOOLEAN,
            us_is_active BOOLEAN
        )
    ''')
    
    # Copy data from the current table to the new table
    op.execute('''
        INSERT INTO tb_users_new (
            us_id, us_name, us_email, us_pwd, us_birthday,
            us_is_player, us_is_manager, us_is_admin,
            us_is_superuser, us_is_active
        )
        SELECT us_id, us_name, us_email, us_pwd, us_birthday,
               us_is_player, us_is_manager, us_is_admin,
               us_is_superuser, us_is_active
        FROM tb_users
    ''')
    
    # Drop the old table
    op.execute('DROP TABLE tb_users')
    
    # Rename the new table to the original name
    op.execute('ALTER TABLE tb_users_new RENAME TO tb_users')
