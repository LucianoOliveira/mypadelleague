"""Create event system tables

Revision ID: create_event_system
Revises: 
Create Date: 2026-02-23 17:46:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers
revision = 'create_event_system'
down_revision = 'b3aa7719303c'  # Previous head revision
branch_labels = None
depends_on = None

def upgrade():
    # Create EventType table
    op.create_table('event_type',
        sa.Column('et_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('et_name', sa.String(100), nullable=False),
        sa.Column('et_description', sa.Text, nullable=True),
        sa.Column('et_is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('et_order', sa.Integer, nullable=False, default=0),
        sa.Column('et_created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('et_updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create MexicanConfig table
    op.create_table('mexican_config',
        sa.Column('mc_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('mc_name', sa.String(100), nullable=False),
        sa.Column('mc_rounds', sa.Integer, nullable=False),
        sa.Column('mc_players_per_game', sa.Integer, nullable=False, default=4),
        sa.Column('mc_games_per_round', sa.Integer, nullable=False),
        sa.Column('mc_is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('mc_created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('mc_updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create Event table
    op.create_table('event',
        sa.Column('ev_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ev_title', sa.String(200), nullable=False),
        sa.Column('ev_description', sa.Text, nullable=True),
        sa.Column('ev_club_id', sa.Integer, nullable=True),
        sa.Column('ev_location', sa.String(200), nullable=True),
        sa.Column('ev_date', sa.Date, nullable=False),
        sa.Column('ev_start_time', sa.Time, nullable=True),
        sa.Column('ev_end_time', sa.Time, nullable=True),
        sa.Column('ev_type_id', sa.Integer, nullable=False),
        sa.Column('ev_max_players', sa.Integer, nullable=False),
        sa.Column('ev_registration_start', sa.DateTime, nullable=True),
        sa.Column('ev_registration_end', sa.DateTime, nullable=True),
        sa.Column('ev_status', sa.String(50), nullable=False, default='announced'),
        sa.Column('ev_pairing_type', sa.String(50), nullable=True),
        sa.Column('ev_mexican_config_id', sa.Integer, nullable=True),
        sa.Column('ev_created_by_id', sa.Integer, nullable=False),
        sa.Column('ev_created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('ev_updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['ev_club_id'], ['club.cl_id']),
        sa.ForeignKeyConstraint(['ev_type_id'], ['event_type.et_id']),
        sa.ForeignKeyConstraint(['ev_mexican_config_id'], ['mexican_config.mc_id']),
        sa.ForeignKeyConstraint(['ev_created_by_id'], ['users.us_id'])
    )

    # Create EventRegistration table
    op.create_table('event_registration',
        sa.Column('er_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('er_event_id', sa.Integer, nullable=False),
        sa.Column('er_player_id', sa.Integer, nullable=False),
        sa.Column('er_registered_by_id', sa.Integer, nullable=False),
        sa.Column('er_is_substitute', sa.Boolean, nullable=False, default=False),
        sa.Column('er_registered_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['er_event_id'], ['event.ev_id']),
        sa.ForeignKeyConstraint(['er_player_id'], ['users.us_id']),
        sa.ForeignKeyConstraint(['er_registered_by_id'], ['users.us_id']),
        sa.UniqueConstraint('er_event_id', 'er_player_id')
    )

    # Create EventClassification table
    op.create_table('event_classification',
        sa.Column('ec_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ec_event_id', sa.Integer, nullable=False),
        sa.Column('ec_player_id', sa.Integer, nullable=False),
        sa.Column('ec_position', sa.Integer, nullable=False),
        sa.Column('ec_points', sa.Integer, nullable=False, default=0),
        sa.Column('ec_games_played', sa.Integer, nullable=False, default=0),
        sa.Column('ec_games_won', sa.Integer, nullable=False, default=0),
        sa.Column('ec_sets_won', sa.Integer, nullable=False, default=0),
        sa.Column('ec_sets_lost', sa.Integer, nullable=False, default=0),
        sa.Column('ec_updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['ec_event_id'], ['event.ev_id']),
        sa.ForeignKeyConstraint(['ec_player_id'], ['users.us_id']),
        sa.UniqueConstraint('ec_event_id', 'ec_player_id')
    )

    # Create EventCourts table
    op.create_table('event_courts',
        sa.Column('evc_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('evc_event_id', sa.Integer, nullable=False),
        sa.Column('evc_court_id', sa.Integer, nullable=True),
        sa.Column('evc_court_name', sa.String(100), nullable=True),
        sa.Column('evc_created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['evc_event_id'], ['event.ev_id']),
        sa.ForeignKeyConstraint(['evc_court_id'], ['court.ct_id'])
    )

    # Create EventPlayerNames table
    op.create_table('event_player_names',
        sa.Column('epn_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('epn_event_id', sa.Integer, nullable=False),
        sa.Column('epn_player_name', sa.String(200), nullable=False),
        sa.Column('epn_position_type', sa.String(50), nullable=False),
        sa.Column('epn_position_index', sa.Integer, nullable=True),
        sa.Column('epn_team_identifier', sa.String(10), nullable=True),
        sa.Column('epn_team_position', sa.Integer, nullable=True),
        sa.Column('epn_created_by_id', sa.Integer, nullable=False),
        sa.Column('epn_created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['epn_event_id'], ['event.ev_id']),
        sa.ForeignKeyConstraint(['epn_created_by_id'], ['users.us_id'])
    )

    # Insert initial event types
    connection = op.get_bind()
    connection.execute(text("""
        INSERT INTO event_type (et_name, et_description, et_is_active, et_order) VALUES
        ('Mexican Tournament', 'Traditional Mexican format tournament with multiple rounds', 1, 1),
        ('Single Elimination', 'Knockout tournament format', 1, 2),
        ('Round Robin', 'Everyone plays everyone format', 1, 3),
        ('Swiss System', 'Swiss system pairing tournament', 1, 4),
        ('Friendly Match', 'Casual friendly games', 1, 5)
    """))

    # Insert initial Mexican configurations
    connection.execute(text("""
        INSERT INTO mexican_config (mc_name, mc_rounds, mc_players_per_game, mc_games_per_round, mc_is_active) VALUES
        ('Standard Mexican (3 rounds)', 3, 4, 1, 1),
        ('Extended Mexican (4 rounds)', 4, 4, 1, 1),
        ('Long Mexican (5 rounds)', 5, 4, 1, 1),
        ('Quick Mexican (2 rounds)', 2, 4, 1, 1)
    """))

def downgrade():
    op.drop_table('event_player_names')
    op.drop_table('event_courts')
    op.drop_table('event_classification')
    op.drop_table('event_registration')
    op.drop_table('event')
    op.drop_table('mexican_config')
    op.drop_table('event_type')