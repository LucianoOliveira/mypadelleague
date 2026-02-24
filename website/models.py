from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from datetime import datetime, timezone, timedelta, time

class Users(db.Model, UserMixin):
    __tablename__ = 'tb_users'
    us_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    us_name = db.Column(db.String(50), nullable=False)
    us_email = db.Column(db.String(200))
    us_pwd = db.Column(db.String(150))
    us_telephone = db.Column(db.String(20), nullable=False, unique=True)  # Added telephone field
    us_birthday = db.Column(db.Date)
    us_is_player = db.Column(db.Boolean, default=True)
    us_is_manager = db.Column(db.Boolean, default=False)
    us_is_admin = db.Column(db.Boolean, default=False)
    us_is_superuser = db.Column(db.Boolean, default=False)
    us_is_active = db.Column(db.Boolean, default=True)

    def get_id(self):
        return str(self.us_id)

class UserRequests(db.Model):
    __tablename__ = 'tb_user_requests'
    ur_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ur_user_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    ur_request_type = db.Column(db.String(50), nullable=False)
    ur_request_time = db.Column(db.DateTime, default=func.now())
    ur_responded = db.Column(db.Boolean, default=False)
    ur_accepted = db.Column(db.Boolean, nullable=True)
    ur_response_time = db.Column(db.DateTime, nullable=True)
    ur_response_user_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=True)
    ur_response_reason = db.Column(db.String(500), nullable=True)

    user = db.relationship('Users', foreign_keys=[ur_user_id], backref=db.backref('requests', lazy=True))
    response_user = db.relationship('Users', foreign_keys=[ur_response_user_id], backref=db.backref('responses', lazy=True))

class Messages(db.Model):
    __tablename__ = 'tb_messages'
    msg_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    msg_sender_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    msg_receiver_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    msg_subject = db.Column(db.String(200), nullable=False)
    msg_body = db.Column(db.Text, nullable=False)
    msg_sent_at = db.Column(db.DateTime, default=func.now())
    msg_read_at = db.Column(db.DateTime, nullable=True)

    sender = db.relationship('Users', foreign_keys=[msg_sender_id], backref=db.backref('sent_messages', lazy=True))
    receiver = db.relationship('Users', foreign_keys=[msg_receiver_id], backref=db.backref('received_messages', lazy=True))

class Club(db.Model):
    __tablename__ = 'tb_club'
    cl_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cl_name = db.Column(db.String(100), nullable=False)
    cl_email = db.Column(db.String(200))
    cl_phone = db.Column(db.String(20))
    cl_address = db.Column(db.String(200))
    cl_active = db.Column(db.Boolean, default=True)
    
    courts = db.relationship('Court', backref='club', lazy=True)
    leagues = db.relationship('League', backref='club', lazy=True)

class ClubAuthorization(db.Model):
    __tablename__ = 'tb_club_authorization'
    ca_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ca_user_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    ca_club_id = db.Column(db.Integer, db.ForeignKey('tb_club.cl_id'), nullable=False)
    ca_created_at = db.Column(db.DateTime, default=func.now())

    user = db.relationship('Users', backref=db.backref('club_authorizations', lazy=True))
    club = db.relationship('Club', backref=db.backref('authorized_users', lazy=True))

    __table_args__ = (db.UniqueConstraint('ca_user_id', 'ca_club_id', name='uq_user_club'),)

class Court(db.Model):
    __tablename__ = 'tb_court'
    ct_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ct_name = db.Column(db.String(50), nullable=False)
    ct_sport = db.Column(db.String(50), nullable=False)
    ct_club_id = db.Column(db.Integer, db.ForeignKey('tb_club.cl_id'), nullable=False)

class League(db.Model):
    __tablename__ = 'tb_league'
    lg_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lg_club_id = db.Column(db.Integer, db.ForeignKey('tb_club.cl_id'), nullable=False)
    lg_name = db.Column(db.String(50))
    lg_level = db.Column(db.String(20))
    lg_status = db.Column(db.String(20))
    lg_nbrDays = db.Column(db.Integer)
    lg_nbrTeams = db.Column(db.Integer)
    lg_nbr_substitutes = db.Column(db.Integer, default=0)  # Number of allowed substitutes
    lg_nbr_auto_substitutes = db.Column(db.Integer, default=0)  # Number of auto-registered substitutes
    lg_presence_points = db.Column(db.Integer, default=0)  # Points awarded for presence in gameday
    lg_startDate = db.Column(db.Date)
    lg_endDate = db.Column(db.Date)
    lg_registration_start = db.Column(db.DateTime(timezone=True))
    lg_registration_end = db.Column(db.DateTime(timezone=True))
    lg_startTime = db.Column(db.Time)
    lg_minWarmUp = db.Column(db.Integer)
    lg_minPerGame = db.Column(db.Integer)
    lg_minBetweenGames = db.Column(db.Integer)
    lg_typeOfLeague = db.Column(db.String(50))
    tb_maxLevel = db.Column(db.Integer)
    lg_eloK = db.Column(db.Integer)
    lg_max_players = db.Column(db.Integer)  # Maximum number of players that can register

    @property
    def current_player_count(self):
        return LeaguePlayers.query.filter_by(lp_league_id=self.lg_id).count()

    @property
    def registration_start_utc(self):
        if (self.lg_registration_start and self.lg_registration_start.tzinfo is None):
            return self.lg_registration_start.replace(tzinfo=timezone.utc)
        return self.lg_registration_start

    @property
    def registration_end_utc(self):
        if (self.lg_registration_end and self.lg_registration_end.tzinfo is None):
            return self.lg_registration_end.replace(tzinfo=timezone.utc)
        return self.lg_registration_end

    def should_update_status(self):
        now = datetime.now(timezone.utc)
        
        # Check registration period status using timezone-aware comparisons
        if self.lg_status == "announced":
            if self.registration_start_utc and now >= self.registration_start_utc:
                return True
        elif self.lg_status == "accepting registrations":
            if (self.registration_end_utc and now > self.registration_end_utc) or self.current_player_count >= self.lg_max_players:
                return True
        elif self.lg_status == "registration complete":
            if now.date() >= self.lg_startDate:
                return True
                
        return False

    def update_status(self):
        if not self.should_update_status():
            return

        now = datetime.now(timezone.utc)
        
        if self.lg_status == "announced" and self.registration_start_utc and now >= self.registration_start_utc:
            self.lg_status = "accepting registrations"
        
        elif self.lg_status == "accepting registrations":
            if self.current_player_count >= self.lg_max_players:
                self.lg_status = "registration complete"
            elif self.registration_end_utc and now > self.registration_end_utc:
                if self.current_player_count < self.lg_max_players:
                    self.lg_status = "canceled"
                else:
                    self.lg_status = "registration complete"
        
        elif self.lg_status == "registration complete" and now.date() >= self.lg_startDate:
            self.lg_status = "being played"

    def can_modify_league_settings(self):
        """Check if league settings can still be modified (before first gameday)"""
        now = datetime.now(timezone.utc)
        return now.date() < self.lg_startDate if self.lg_startDate else True
    
    @property
    def max_substitutes(self):
        """Maximum number of substitutes allowed based on number of teams"""
        return self.lg_nbrTeams * 2 if self.lg_nbrTeams else 0

    def validate_substitutes(self):
        """Validate substitute numbers are within allowed range"""
        max_subs = self.max_substitutes
        if self.lg_nbr_substitutes < 0 or self.lg_nbr_substitutes > max_subs:
            raise ValueError(f"Number of substitutes must be between 0 and {max_subs}")
        if self.lg_nbr_auto_substitutes < 0 or self.lg_nbr_auto_substitutes > max_subs:
            raise ValueError(f"Number of auto-substitutes must be between 0 and {max_subs}")
        if self.lg_presence_points < 0 or self.lg_presence_points > 3:
            raise ValueError("Presence points must be between 0 and 3")

    def __init__(self, *args, **kwargs):
        # Set default values for substitute-related fields if they're None
        if 'lg_nbr_substitutes' not in kwargs or kwargs['lg_nbr_substitutes'] is None:
            kwargs['lg_nbr_substitutes'] = 0
        if 'lg_nbr_auto_substitutes' not in kwargs or kwargs['lg_nbr_auto_substitutes'] is None:
            kwargs['lg_nbr_auto_substitutes'] = 0
        if 'lg_presence_points' not in kwargs or kwargs['lg_presence_points'] is None:
            kwargs['lg_presence_points'] = 0
            
        super().__init__(*args, **kwargs)
        if self.lg_nbrTeams:
            self.validate_substitutes()

class GameDay(db.Model):
    __tablename__ = 'tb_gameday'
    gd_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gd_idLeague = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id', name='fk_gameday_league'), nullable=False)
    gd_date = db.Column(db.Date)
    gd_status = db.Column(db.String(20), nullable=False)
    gd_idWinner1 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_gameday_winner1'), nullable=True)
    gd_idWinner2 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_gameday_winner2'), nullable=True)
    gd_gameDayName = db.Column(db.String(50))
    gd_registration_start = db.Column(db.DateTime(timezone=True))
    gd_registration_end = db.Column(db.DateTime(timezone=True))

    # Relationships
    league = db.relationship('League', backref=db.backref('gamedays', lazy=True))
    winner1 = db.relationship('Users', foreign_keys=[gd_idWinner1], backref=db.backref('winner1_gamedays', lazy=True))
    winner2 = db.relationship('Users', foreign_keys=[gd_idWinner2], backref=db.backref('winner2_gamedays', lazy=True))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.gd_date:
            # Set registration start to one week before at 12:30:00 UTC
            self.gd_registration_start = datetime.combine(
                self.gd_date - timedelta(days=7),
                time(12, 30, 0)
            ).replace(tzinfo=timezone.utc)
            # Set registration end to the day before at 12:30:00 UTC
            self.gd_registration_end = datetime.combine(
                self.gd_date - timedelta(days=1),
                time(12, 30, 0)
            ).replace(tzinfo=timezone.utc)

    @property
    def current_player_count(self):
        return GameDayRegistration.query.filter_by(gdr_gameday_id=self.gd_id).count()

    @property
    def max_players(self):
        if self.league:
            return (self.league.lg_nbrTeams * 2) + self.league.lg_nbr_substitutes
        return 0

    @property
    def registration_start_utc(self):
        if self.gd_registration_start and self.gd_registration_start.tzinfo is None:
            return self.gd_registration_start.replace(tzinfo=timezone.utc)
        return self.gd_registration_start

    @property
    def registration_end_utc(self):
        if self.gd_registration_end and self.gd_registration_end.tzinfo is None:
            return self.gd_registration_end.replace(tzinfo=timezone.utc)
        return self.gd_registration_end

class GameDayRegistration(db.Model):
    __tablename__ = 'tb_gameday_registration'
    gdr_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gdr_gameday_id = db.Column(db.Integer, db.ForeignKey('tb_gameday.gd_id'), nullable=False)
    gdr_player_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    gdr_registered_by_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    gdr_registered_at = db.Column(db.DateTime(timezone=True), default=func.now())

    # Relationships
    gameday = db.relationship('GameDay', backref=db.backref('registrations', lazy=True))
    player = db.relationship('Users', foreign_keys=[gdr_player_id], backref=db.backref('gameday_registrations', lazy=True))
    registered_by = db.relationship('Users', foreign_keys=[gdr_registered_by_id], backref=db.backref('gameday_registrations_made', lazy=True))

    __table_args__ = (db.UniqueConstraint('gdr_gameday_id', 'gdr_player_id', name='uq_gameday_player_registration'),)

class Game(db.Model):
    __tablename__ = 'tb_game'
    gm_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gm_idLeague = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id'), nullable=False)
    gm_idGameDay = db.Column(db.Integer, db.ForeignKey('tb_gameday.gd_id'), nullable=False)
    gm_idEvent = db.Column(db.Integer, db.ForeignKey('tb_event.ev_id'), nullable=True)
    gm_date = db.Column(db.Date)
    gm_timeStart = db.Column(db.Time)
    gm_timeEnd = db.Column(db.Time)
    gm_court = db.Column(db.Integer, db.ForeignKey('tb_court.ct_id'), nullable=False)
    gm_idPlayer_A1 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'))
    gm_idPlayer_A2 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'))
    gm_idPlayer_B1 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'))
    gm_idPlayer_B2 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'))
    gm_result_A = db.Column(db.Integer)
    gm_result_B = db.Column(db.Integer)
    gm_teamA = db.Column(db.String(1))
    gm_teamB = db.Column(db.String(1))

    # Relationships
    league = db.relationship('League', backref=db.backref('games', lazy=True))
    gameday = db.relationship('GameDay', backref=db.backref('games', lazy=True))
    court = db.relationship('Court', backref=db.backref('games', lazy=True))
    player_A1 = db.relationship('Users', foreign_keys=[gm_idPlayer_A1])
    player_A2 = db.relationship('Users', foreign_keys=[gm_idPlayer_A2])
    player_B1 = db.relationship('Users', foreign_keys=[gm_idPlayer_B1])
    player_B2 = db.relationship('Users', foreign_keys=[gm_idPlayer_B2])

class LeagueCourts(db.Model):
    __tablename__ = 'tb_league_courts'
    lc_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lc_league_id = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id'), nullable=False)
    lc_court_id = db.Column(db.Integer, db.ForeignKey('tb_court.ct_id'), nullable=False)

    # Relationships
    league = db.relationship('League', backref=db.backref('league_courts', lazy=True))
    court = db.relationship('Court', backref=db.backref('league_courts', lazy=True))

class GameDayPlayer(db.Model):
    __tablename__ = 'tb_gameDayPlayer'
    gp_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gp_idLeague = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id'), nullable=False)
    gp_idGameDay = db.Column(db.Integer, db.ForeignKey('tb_gameday.gd_id'), nullable=False)
    gp_idPlayer = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    gp_registerTS = db.Column(db.DateTime(timezone=True), default=func.now())
    gp_team = db.Column(db.String(1), nullable=True)

    # Relationships
    league = db.relationship('League', backref=db.backref('gameday_players', lazy=True))
    gameday = db.relationship('GameDay', backref=db.backref('players', lazy=True))
    player = db.relationship('Users', backref=db.backref('gameday_participations', lazy=True))

class GameDayClassification(db.Model):
    __tablename__ = 'tb_gameDayClassification'
    gc_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gc_idLeague = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id'), nullable=False)
    gc_idGameDay = db.Column(db.Integer, db.ForeignKey('tb_gameday.gd_id'), nullable=False)
    gc_idPlayer = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    gc_points = db.Column(db.Integer, nullable=False)
    gc_wins = db.Column(db.Integer, nullable=False)
    gc_losses = db.Column(db.Integer, nullable=False)
    gc_gamesFavor = db.Column(db.Integer, nullable=False)
    gc_gamesAgainst = db.Column(db.Integer, nullable=False)
    gc_gamesDiff = db.Column(db.Integer, nullable=False)
    gc_ranking = db.Column(db.Float, nullable=False)

    # Relationships
    league = db.relationship('League', backref=db.backref('gameday_classifications', lazy=True))
    gameday = db.relationship('GameDay', backref=db.backref('classifications', lazy=True))
    player = db.relationship('Users', backref=db.backref('gameday_classifications', lazy=True))

class LeagueClassification(db.Model):
    __tablename__ = 'tb_leagueClassification'
    lc_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lc_idLeague = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id'), nullable=False)
    lc_idPlayer = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    lc_points = db.Column(db.Integer, nullable=False)
    lc_wins = db.Column(db.Integer, nullable=False)
    lc_losses = db.Column(db.Integer, nullable=False)
    lc_gamesFavor = db.Column(db.Integer, nullable=False)
    lc_gamesAgainst = db.Column(db.Integer, nullable=False)
    lc_gamesDiff = db.Column(db.Integer, nullable=False)
    lc_ranking = db.Column(db.Float, nullable=False)

    # Relationships
    league = db.relationship('League', backref=db.backref('league_classifications', lazy=True))
    player = db.relationship('Users', backref=db.backref('league_classifications', lazy=True))


# EVENT SYSTEM MODELS
class EventType(db.Model):
    __tablename__ = 'tb_event_types'
    et_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    et_name = db.Column(db.String(50), nullable=False, unique=True)
    et_description = db.Column(db.Text)
    et_order = db.Column(db.Integer, default=1)
    et_has_config = db.Column(db.Boolean, default=False)
    et_is_active = db.Column(db.Boolean, default=True)
    et_created_at = db.Column(db.DateTime(timezone=True), default=func.now())

    def __repr__(self):
        return f'<EventType {self.et_name}>'

class MexicanConfig(db.Model):
    __tablename__ = 'tb_mexican_config'
    mc_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mc_event_type_id = db.Column(db.Integer, db.ForeignKey('tb_event_types.et_id'), nullable=True)
    mc_event_id = db.Column(db.Integer, db.ForeignKey('tb_event.ev_id'), nullable=True)
    mc_name = db.Column(db.String(100), nullable=False)
    mc_description = db.Column(db.Text)
    mc_max_points = db.Column(db.Integer, nullable=False, default=16)
    mc_allow_draws = db.Column(db.Boolean, nullable=False, default=True)
    mc_overtime_enabled = db.Column(db.Boolean, nullable=False, default=False)
    mc_point_win = db.Column(db.Integer, nullable=False, default=3)
    mc_point_draw = db.Column(db.Integer, nullable=False, default=1)
    mc_point_loss = db.Column(db.Integer, nullable=False, default=0)
    mc_is_default = db.Column(db.Boolean, default=False)
    mc_is_active = db.Column(db.Boolean, default=True)
    mc_created_at = db.Column(db.DateTime(timezone=True), default=func.now())

    # Relationships
    event_type = db.relationship('EventType', backref=db.backref('mexican_configs', lazy=True))
    event = db.relationship('Event', backref=db.backref('mexican_config', uselist=False, lazy=True))

    def validate_game_result(self, result_a, result_b):
        """
        Validate if game result is allowed according to Mexican configuration
        Returns: (is_valid, error_message)
        """
        # Allow 0-0 (indicates unplayed game)
        if result_a == 0 and result_b == 0:
            return True, None
            
        total_points = result_a + result_b
        max_points = self.mc_max_points
        
        # Check if draws are allowed
        if result_a == result_b and not self.mc_allow_draws:
            # Exception: tied games at max points can go +1 to break tie if overtime enabled
            if self.mc_overtime_enabled and total_points == max_points + 1 and abs(result_a - result_b) == 1:
                return True, None
            return False, "Draws are not allowed for this event"
        
        # Check valid point totals
        valid_totals = [max_points]
        if self.mc_overtime_enabled:
            # Allow overtime point for tie-breaking
            valid_totals.append(max_points + 1)
            
        if total_points not in valid_totals:
            return False, f"Invalid point total. Must sum to {max_points}" + (
                f" or {max_points + 1} (overtime)" if self.mc_overtime_enabled else ""
            )
            
        return True, None

    def calculate_player_points(self, result_a, result_b, player_is_team_a):
        """
        Calculate points awarded to a player based on game result
        """
        if result_a == 0 and result_b == 0:
            return 0  # Unplayed game
        
        if player_is_team_a:
            player_result, opponent_result = result_a, result_b
        else:
            player_result, opponent_result = result_b, result_a
            
        if player_result > opponent_result:
            return self.mc_point_win
        elif player_result == opponent_result:
            return self.mc_point_draw
        else:
            return self.mc_point_loss

    def __repr__(self):
        return f'<MexicanConfig {self.mc_name}>'

class Event(db.Model):
    __tablename__ = 'tb_event'
    ev_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ev_club_id = db.Column(db.Integer, db.ForeignKey('tb_club.cl_id'), nullable=True)
    ev_title = db.Column(db.String(100), nullable=False)
    ev_location = db.Column(db.String(200))
    ev_date = db.Column(db.Date, nullable=False)
    ev_start_time = db.Column(db.Time, nullable=False)
    ev_type_id = db.Column(db.Integer, db.ForeignKey('tb_event_types.et_id'), nullable=False)
    ev_max_players = db.Column(db.Integer, nullable=False)
    ev_registration_start = db.Column(db.DateTime(timezone=True))
    ev_registration_end = db.Column(db.DateTime(timezone=True))
    ev_nbr_substitutes = db.Column(db.Integer, default=0)
    ev_pairing_type = db.Column(db.String(20), default='Random')  # Random, Manual, L&R Random
    ev_status = db.Column(db.String(20), default='announced')  # announced, registration_started, registration_ended, event_started, event_ended
    ev_winner1_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_event_winner1'), nullable=True)
    ev_winner2_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_event_winner2'), nullable=True)
    ev_created_by_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_event_created_by'), nullable=False)
    ev_created_at = db.Column(db.DateTime(timezone=True), default=func.now())

    # Relationships
    club = db.relationship('Club', backref=db.backref('events', lazy=True))
    event_type = db.relationship('EventType', backref=db.backref('events', lazy=True))
    winner1 = db.relationship('Users', foreign_keys=[ev_winner1_id], backref=db.backref('event_wins_first', lazy=True))
    winner2 = db.relationship('Users', foreign_keys=[ev_winner2_id], backref=db.backref('event_wins_second', lazy=True))
    created_by = db.relationship('Users', foreign_keys=[ev_created_by_id], backref=db.backref('events_created', lazy=True))
    games = db.relationship('Game', foreign_keys='Game.gm_idEvent', backref=db.backref('event', lazy=True))

    @property
    def current_player_count(self):
        return EventRegistration.query.filter_by(er_event_id=self.ev_id, er_is_substitute=False).count()

    @property
    def current_substitute_count(self):
        return EventRegistration.query.filter_by(er_event_id=self.ev_id, er_is_substitute=True).count()

    @property
    def event_datetime(self):
        """Combine date and time into a single datetime object"""
        from datetime import datetime, timezone
        return datetime.combine(self.ev_date, self.ev_start_time).replace(tzinfo=timezone.utc)

    @property
    def registration_start_utc(self):
        if self.ev_registration_start and self.ev_registration_start.tzinfo is None:
            return self.ev_registration_start.replace(tzinfo=timezone.utc)
        return self.ev_registration_start

    @property
    def registration_end_utc(self):
        if self.ev_registration_end and self.ev_registration_end.tzinfo is None:
            return self.ev_registration_end.replace(tzinfo=timezone.utc)
        return self.ev_registration_end

    def should_update_status(self):
        now = datetime.now(timezone.utc)
        event_datetime = datetime.combine(self.ev_date, self.ev_start_time).replace(tzinfo=timezone.utc)
        
        if self.ev_status == "announced":
            if self.registration_start_utc and now >= self.registration_start_utc:
                return True
        elif self.ev_status == "registration_started":
            if (self.registration_end_utc and now > self.registration_end_utc) or self.current_player_count >= self.ev_max_players:
                return True
        elif self.ev_status == "registration_ended":
            if now >= event_datetime:
                return True
        elif self.ev_status == "event_started":
            # Event ends after 4 hours by default (can be customized later)
            if now >= event_datetime + timedelta(hours=4):
                return True
                
        return False

    def update_status(self):
        if not self.should_update_status():
            return

        now = datetime.now(timezone.utc)
        event_datetime = datetime.combine(self.ev_date, self.ev_start_time).replace(tzinfo=timezone.utc)
        
        if self.ev_status == "announced" and self.registration_start_utc and now >= self.registration_start_utc:
            self.ev_status = "registration_started"
        
        elif self.ev_status == "registration_started":
            if self.current_player_count >= self.ev_max_players:
                self.ev_status = "registration_ended"
            elif self.registration_end_utc and now > self.registration_end_utc:
                self.ev_status = "registration_ended"
        
        elif self.ev_status == "registration_ended" and now >= event_datetime:
            self.ev_status = "event_started"
        
        elif self.ev_status == "event_started" and now >= event_datetime + timedelta(hours=4):
            self.ev_status = "event_ended"

    def can_register(self):
        """Check if users can still register for the event"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        # Update status first
        self.update_status()
        
        return (self.ev_status == "registration_started" and 
                self.current_player_count < self.ev_max_players and 
                (not self.registration_end_utc or now <= self.registration_end_utc))

    def validate_player_limits(self):
        """Validate current registrations don't exceed limits"""
        current_players = self.current_player_count
        current_substitutes = self.current_substitute_count
        
        if current_players > self.ev_max_players:
            raise ValueError(f"Too many players registered: {current_players} > {self.ev_max_players}")
        
        if current_substitutes > self.ev_nbr_substitutes:
            raise ValueError(f"Too many substitutes registered: {current_substitutes} > {self.ev_nbr_substitutes}")

    def __repr__(self):
        return f'<Event {self.ev_title}>'

class EventRegistration(db.Model):
    __tablename__ = 'tb_event_registration'
    er_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    er_event_id = db.Column(db.Integer, db.ForeignKey('tb_event.ev_id'), nullable=False)
    er_player_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    er_registered_by_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    er_registered_at = db.Column(db.DateTime(timezone=True), default=func.now())
    er_is_substitute = db.Column(db.Boolean, default=False)

    # Relationships
    event = db.relationship('Event', backref=db.backref('registrations', lazy=True))
    player = db.relationship('Users', foreign_keys=[er_player_id], backref=db.backref('event_registrations', lazy=True))
    registered_by = db.relationship('Users', foreign_keys=[er_registered_by_id], backref=db.backref('event_registrations_made', lazy=True))

    __table_args__ = (db.UniqueConstraint('er_event_id', 'er_player_id', name='uq_event_player_registration'),)

class EventClassification(db.Model):
    __tablename__ = 'tb_event_classification'
    ec_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ec_event_id = db.Column(db.Integer, db.ForeignKey('tb_event.ev_id'), nullable=False)
    ec_player_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    ec_points = db.Column(db.Integer, default=0)
    ec_wins = db.Column(db.Integer, default=0)
    ec_losses = db.Column(db.Integer, default=0)
    ec_games_favor = db.Column(db.Integer, default=0)
    ec_games_against = db.Column(db.Integer, default=0)
    ec_games_diff = db.Column(db.Integer, default=0)
    ec_ranking = db.Column(db.Float, default=0.0)

    # Relationships
    event = db.relationship('Event', backref=db.backref('classifications', lazy=True))
    player = db.relationship('Users', backref=db.backref('event_classifications', lazy=True))

    __table_args__ = (db.UniqueConstraint('ec_event_id', 'ec_player_id', name='uq_event_player_classification'),)

class EventCourts(db.Model):
    __tablename__ = 'tb_event_courts'
    evc_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evc_event_id = db.Column(db.Integer, db.ForeignKey('tb_event.ev_id'), nullable=False)
    evc_court_id = db.Column(db.Integer, db.ForeignKey('tb_court.ct_id'), nullable=False)

    # Relationships
    event = db.relationship('Event', backref=db.backref('event_courts', lazy=True))
    court = db.relationship('Court', backref=db.backref('event_courts', lazy=True))

    __table_args__ = (db.UniqueConstraint('evc_event_id', 'evc_court_id', name='uq_event_court'),)

class EventPlayerNames(db.Model):
    __tablename__ = 'tb_event_player_names'
    epn_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    epn_event_id = db.Column(db.Integer, db.ForeignKey('tb_event.ev_id'), nullable=False)
    epn_player_name = db.Column(db.String(100), nullable=False)
    epn_position_type = db.Column(db.String(20), nullable=False)  # 'random', 'team', 'left', 'right'
    epn_position_index = db.Column(db.Integer, nullable=False)  # Order/index within the position type
    epn_team_identifier = db.Column(db.String(10), nullable=True)  # For manual pairing: 'A', 'B', 'C', etc.
    epn_team_position = db.Column(db.Integer, nullable=True)  # For manual pairing: 1 or 2 (first or second player in team)
    epn_created_by_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    epn_created_at = db.Column(db.DateTime(timezone=True), default=func.now())

    # Relationships
    event = db.relationship('Event', backref=db.backref('player_names', lazy=True))
    created_by = db.relationship('Users', backref=db.backref('event_player_names_created', lazy=True))

    def __repr__(self):
        return f'<EventPlayerNames {self.epn_player_name} for event {self.epn_event_id}>'

class ELOranking(db.Model):
    __tablename__ = 'tb_ELO_ranking'
    pl_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), primary_key=True)
    pl_rankingNow = db.Column(db.Float)
    pl_totalRankingOpo = db.Column(db.Float)
    pl_wins = db.Column(db.Integer, nullable=False)
    pl_losses = db.Column(db.Integer, nullable=False)
    pl_totalGames = db.Column(db.Integer, nullable=False)

    # Relationship
    player = db.relationship('Users', backref=db.backref('elo_ranking', uselist=False, lazy=True))

class ELOrankingHist(db.Model):
    __tablename__ = 'tb_ELO_ranking_hist'
    el_gm_id = db.Column(db.Integer, db.ForeignKey('tb_game.gm_id'), nullable=False, primary_key=True)
    el_pl_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False, primary_key=True)
    el_date = db.Column(db.Date)
    el_startTime = db.Column(db.Time)
    el_pl_id_teammate = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    el_pl_id_op1 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    el_pl_id_op2 = db.Column(db.Integer, db.ForeignKey('tb_users.us_id'), nullable=False)
    el_result_team = db.Column(db.Integer, nullable=False)
    el_result_op = db.Column(db.Integer, nullable=False)
    el_beforeRank = db.Column(db.Float)
    el_afterRank = db.Column(db.Float)

    # Relationships
    game = db.relationship('Game', backref=db.backref('elo_history', lazy=True))
    player = db.relationship('Users', foreign_keys=[el_pl_id], backref=db.backref('elo_history', lazy=True))
    teammate = db.relationship('Users', foreign_keys=[el_pl_id_teammate], backref=db.backref('elo_history_as_teammate', lazy=True))
    opponent1 = db.relationship('Users', foreign_keys=[el_pl_id_op1], backref=db.backref('elo_history_as_opponent1', lazy=True))
    opponent2 = db.relationship('Users', foreign_keys=[el_pl_id_op2], backref=db.backref('elo_history_as_opponent2', lazy=True))

class LeaguePlayers(db.Model):
    __tablename__ = 'tb_league_players'
    lp_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lp_league_id = db.Column(db.Integer, db.ForeignKey('tb_league.lg_id', name='fk_leagueplayers_league'), nullable=False)
    lp_player_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_leagueplayers_player'), nullable=False)
    lp_registered_by_id = db.Column(db.Integer, db.ForeignKey('tb_users.us_id', name='fk_leagueplayers_registeredby'), nullable=False)
    lp_registered_at = db.Column(db.DateTime(timezone=True), default=func.now())
    
    # Relationships
    league = db.relationship('League', backref=db.backref('registered_players', lazy=True))
    player = db.relationship('Users', foreign_keys=[lp_player_id], backref=db.backref('league_registrations', lazy=True))
    registered_by = db.relationship('Users', foreign_keys=[lp_registered_by_id], backref=db.backref('player_registrations_made', lazy=True))

    __table_args__ = (db.UniqueConstraint('lp_league_id', 'lp_player_id', name='uq_league_player'),)