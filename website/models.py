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