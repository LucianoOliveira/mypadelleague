from flask_login import login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, func, cast, String, text, desc, case, literal_column
from flask import render_template, Blueprint
from website import db
from website.models import League, Club, Users, GameDay, GameDayPlayer, Game, LeagueClassification, GameDayClassification, ELOranking, ELOrankingHist, LeagueCourts, Event, EventClassification, EventRegistration
from PIL import Image
from datetime import datetime, date, timedelta

#tools
def func_crop_image_in_memory(filePath):
    img = Image.open(filePath)
    width, height = img.size
    min_dim = min(width, height)
    left = (width - min_dim) / 2
    top = (height - min_dim) / 2
    right = (width + min_dim) / 2
    bottom = (height + min_dim) / 2
    img = img.crop((left, top, right, bottom))
    return img

def func_calculate_player_age(birthdate):
        today = date.today()
        age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
        return age

def func_delete_gameday_players_upd_class(gameDayID):
    gameDay_data = GameDay.query.filter_by(gd_id=gameDayID).first()
    leagueID = gameDay_data.gd_idLeague
    # DONE - Add logic for deleting game day players
    try:
        # Delete games associated with the game day
        Game.query.filter_by(gm_idGameDay=gameDayID).delete()
        # Delete game day players associated with the game day
        GameDayPlayer.query.filter_by(gp_idGameDay=gameDayID).delete()

        # Commit the changes to the database
        db.session.commit()

    except Exception as e:
        print(f"Error: {e}")
        # Handle the error, maybe log it or display a message to the user

    #Calculate the league classification after
    func_calculateLeagueClassification(leagueID)

def func_calculateLeagueClassification(leagueID):
    #print("Enter LeagueClassification")
    # clear the league classification
    try:
        LeagueClassification.query.filter_by(lc_idLeague=leagueID).delete()
        db.session.commit()

        players_query = Users.query.filter(Users.us_id.in_(db.session.query(GameDayPlayer.gp_idPlayer).filter(GameDayPlayer.gp_idLeague == leagueID).group_by(GameDayPlayer.gp_idPlayer)))
        players_data = players_query.all()


        for player in players_data:
            id_player = player.us_id
            player_name = player.us_name
            player_birthday = player.us_birthday
            player_age = func_calculate_player_age(player_birthday)

            games_info_query = Game.query.filter(Game.gm_idLeague == leagueID, ((Game.gm_idPlayer_A1 == id_player) | (Game.gm_idPlayer_A2 == id_player) | (Game.gm_idPlayer_B1 == id_player) | (Game.gm_idPlayer_B2 == id_player)), ((Game.gm_result_A > 0) | (Game.gm_result_B > 0)))
            games_info = games_info_query.first()

            league = League.query.filter_by(lg_id=leagueID).first()
            presence_points = league.lg_presence_points if league else 0

            if games_info:
                subquery = (
                    db.session.query(
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("3")),
                            else_=None
                        ).label("POINTS"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_A2 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_B1 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_B2 == id_player), Game.gm_result_B),
                            else_=None
                        ).label("GAMESFAVOR"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_A2 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_B1 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_B2 == id_player), Game.gm_result_A),
                            else_=None
                        ).label("GAMESAGAINST"),
                        literal_column("1").label("GAMES"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            else_=literal_column("0")
                        ).label("WINS"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            else_=literal_column("0")
                        ).label("LOSSES")
                    )
                    .filter(Game.gm_idLeague == leagueID, (Game.gm_idPlayer_A1 == id_player) | (Game.gm_idPlayer_A2 == id_player) | (Game.gm_idPlayer_B1 == id_player) | (Game.gm_idPlayer_B2 == id_player))
                    .subquery("TOTALS")
                )

                query = (
                    db.session.query(
                        literal_column(str(leagueID)).label("LEAGUEID"),
                        literal_column(str(id_player)).label("PLAYERID"),
                        literal_column(f"'{player_name}'").label("PLAYERNAME"), 
                        (func.sum(subquery.c.POINTS)+(presence_points)).label("POINTS"),
                        func.sum(subquery.c.WINS).label("WINS"),
                        func.sum(subquery.c.LOSSES).label("LOSSES"),
                        func.sum(subquery.c.GAMESFAVOR).label("GAMESFAVOR"),
                        func.sum(subquery.c.GAMESAGAINST).label("GAMESAGAINST"),
                        (func.sum(subquery.c.GAMESFAVOR) - func.sum(subquery.c.GAMESAGAINST)).label("GAMESDIFFERENCE"),
                        (
                            ((func.sum(subquery.c.POINTS) + presence_points) * 100000) +
                            (func.sum(subquery.c.WINS) *10000) +
                            (func.sum(subquery.c.GAMES) *1000) +
                            ((func.sum(subquery.c.GAMESFAVOR)- func.sum(subquery.c.GAMESAGAINST))*100) +
                            # ((func.sum(subquery.c.WINS) / func.sum(subquery.c.GAMES)) * 10000) +
                            # ((func.sum(subquery.c.GAMESFAVOR) / (func.sum(subquery.c.GAMESFAVOR) + func.sum(subquery.c.GAMESAGAINST))) * 100) +
                            (player_age / 100)
                        ).label("RANKING")
                    )
                    .select_from(subquery)
                    .group_by("LEAGUEID", "PLAYERID", "PLAYERNAME")
                )

                result = query.all()

                for r2 in result:
                    # Write Classification
                    classification = LeagueClassification(
                        lc_idLeague=leagueID,
                        lc_idPlayer=r2.PLAYERID,
                        # lc_namePlayer=r2.PLAYERNAME,
                        lc_points=r2.POINTS or 0,
                        lc_wins=r2.WINS or 0,
                        lc_losses=r2.LOSSES or 0,
                        lc_gamesFavor=r2.GAMESFAVOR or 0,
                        lc_gamesAgainst=r2.GAMESAGAINST or 0,
                        lc_gamesDiff=r2.GAMESDIFFERENCE or 0,
                        lc_ranking=r2.RANKING or 0,
                    )
                    db.session.add(classification)

                # Commit the changes to the database
                db.session.commit()

            else:
                # Calculation for players without games
                # Write Classification
                classification = LeagueClassification(
                    lc_idLeague=leagueID,
                    lc_idPlayer=id_player,
                    # lc_namePlayer=player_name,
                    lc_points=0,
                    lc_wins=0,
                    lc_losses=0,
                    lc_gamesFavor=0,
                    lc_gamesAgainst=0,
                    lc_gamesDiff=0,
                    lc_ranking=0+(player_age/100),
                )
                db.session.add(classification)
                db.session.commit()

        # Commit the changes to the database
        db.session.commit()

    except Exception as e:
        print(f"Error: {e}")
        # Handle the error, maybe log it or display a message to the user

def func_calculateGameDayClassification(gameDayID):
    #print("Enter GameDayClassification")
    # clear the league classification
    gameDay = GameDay.query.filter_by(gd_id=gameDayID).first()
    leagueID = gameDay.gd_idLeague
    league = League.query.filter_by(lg_id=leagueID).first()
    presence_points = league.lg_presence_points if league else 0
    try:
        GameDayClassification.query.filter_by(gc_idGameDay=gameDayID).delete()
        db.session.commit()

        players_query = Users.query.filter(Users.us_id.in_(db.session.query(GameDayPlayer.gp_idPlayer).filter(GameDayPlayer.gp_idGameDay == gameDayID).group_by(GameDayPlayer.gp_idPlayer)))
        players_data = players_query.all()


        for player in players_data:
            #print(player)
            id_player = player.us_id
            player_name = player.us_name
            player_birthday = player.us_birthday
            player_age = func_calculate_player_age(player_birthday)

            games_info_query = Game.query.filter(Game.gm_idGameDay == gameDayID, ((Game.gm_idPlayer_A1 == id_player) | (Game.gm_idPlayer_A2 == id_player) | (Game.gm_idPlayer_B1 == id_player) | (Game.gm_idPlayer_B2 == id_player)), ((Game.gm_result_A > 0) | (Game.gm_result_B > 0)))
            games_info = games_info_query.first()

            if games_info:
                subquery = (
                    db.session.query(
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("3")),
                            else_=None
                        ).label("POINTS"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_A2 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_B1 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_B2 == id_player), Game.gm_result_B),
                            else_=None
                        ).label("GAMESFAVOR"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_A2 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_B1 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_B2 == id_player), Game.gm_result_A),
                            else_=None
                        ).label("GAMESAGAINST"),
                        literal_column("1").label("GAMES"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            else_=None
                        ).label("WINS"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            else_=literal_column("0")
                        ).label("LOSSES")
                    )
                    .filter(Game.gm_idGameDay == gameDayID, (Game.gm_idPlayer_A1 == id_player) | (Game.gm_idPlayer_A2 == id_player) | (Game.gm_idPlayer_B1 == id_player) | (Game.gm_idPlayer_B2 == id_player))
                    .subquery("TOTALS")
                )
                
                query = (
                    db.session.query(
                        literal_column(str(leagueID)).label("LEAGUEID"),
                        literal_column(str(gameDayID)).label("GAMEDAYID"),
                        literal_column(str(id_player)).label("PLAYERID"),
                        literal_column(f"'{player_name}'").label("PLAYERNAME"), 
                        (func.sum(subquery.c.POINTS)+(presence_points)).label("POINTS"),
                        func.sum(subquery.c.WINS).label("WINS"),
                        func.sum(subquery.c.LOSSES).label("LOSSES"),
                        func.sum(subquery.c.GAMESFAVOR).label("GAMESFAVOR"),
                        func.sum(subquery.c.GAMESAGAINST).label("GAMESAGAINST"),
                        (func.sum(subquery.c.GAMESFAVOR) - func.sum(subquery.c.GAMESAGAINST)).label("GAMESDIFFERENCE"),
                        (
                            ((func.sum(subquery.c.POINTS) + presence_points) * 100000) +
                            (func.sum(subquery.c.WINS) *10000) +
                            (func.sum(subquery.c.GAMES) *1000) +
                            ((func.sum(subquery.c.GAMESFAVOR)- func.sum(subquery.c.GAMESAGAINST))*100) +
                            # ((func.sum(subquery.c.WINS) / func.sum(subquery.c.GAMES)) * 10000) +
                            # ((func.sum(subquery.c.GAMESFAVOR) / (func.sum(subquery.c.GAMESFAVOR) + func.sum(subquery.c.GAMESAGAINST))) * 100) +
                            (player_age / 100)
                        ).label("RANKING")
                    )
                    .select_from(subquery)
                    .group_by("GAMEDAYID", "PLAYERID", "PLAYERNAME")
                )
                #print(f"query: {query}")
                result = query.all()
                #print(f"result: {result}")

                for r2 in result:
                    #print(r2)
                    # Write Classification
                    classification = GameDayClassification(
                        gc_idLeague=leagueID,
                        gc_idGameDay=gameDayID,
                        gc_idPlayer=r2.PLAYERID,
                        # gc_namePlayer=r2.PLAYERNAME,
                        gc_points=r2.POINTS or 0,
                        gc_wins=r2.WINS or 0,
                        gc_losses=r2.LOSSES or 0,
                        gc_gamesFavor=r2.GAMESFAVOR or 0,
                        gc_gamesAgainst=r2.GAMESAGAINST or 0,
                        gc_gamesDiff=r2.GAMESDIFFERENCE or 0,
                        gc_ranking=r2.RANKING or 0,
                    )
                    db.session.add(classification)

                # Commit the changes to the database
                db.session.commit()

            else:
                # Calculation for players without games
                # Write Classification
                classification = GameDayClassification(
                    gc_idLeague=leagueID,
                    gc_idGameDay=gameDayID,
                    gc_idPlayer=id_player,
                    # gc_namePlayer=player_name,
                    gc_points=0,
                    gc_wins=0,
                    gc_losses=0,
                    gc_gamesFavor=0,
                    gc_gamesAgainst=0,
                    gc_gamesDiff=0,
                    gc_ranking=0+(player_age/100),
                )
                db.session.add(classification)
                db.session.commit()

        # Commit the changes to the database
        db.session.commit()

    except Exception as e:
        print(f"Error: {e}")
        # Handle the error, maybe log it or display a message to the user

    #print("Reached Finally")
    # Finally we need to update the winners
    winners_query = (
        db.session.query(
            GameDayClassification.gc_idPlayer.label('idPlayer'),
            Users.us_name.label('namePlayer')
        )
        .join(Users, GameDayClassification.gc_idPlayer == Users.us_id)
        .filter(GameDayClassification.gc_idLeague == leagueID)
        .filter(GameDayClassification.gc_idGameDay == gameDayID)
        .order_by(GameDayClassification.gc_ranking.desc())
        .limit(2)
        .subquery()
    )

    # Fetch the first winner
    winner1 = (
        db.session.query(winners_query.c.idPlayer, winners_query.c.namePlayer)
        .order_by(winners_query.c.idPlayer.asc())
        .first()
    )

    # Fetch the second winner
    winner2 = (
        db.session.query(winners_query.c.idPlayer, winners_query.c.namePlayer)
        .order_by(winners_query.c.idPlayer.desc())
        .first()
    )

    # Update winners to tb_gameday
    gameday_update_query = (
        db.session.query(GameDay)
        .filter(GameDay.gd_idLeague == leagueID)
        .filter(GameDay.gd_id == gameDayID)
        .update(
            {
                GameDay.gd_idWinner1: winner1.idPlayer,
                GameDay.gd_idWinner2: winner2.idPlayer,
            }
        )
    )

    # Commit the changes
    db.session.commit()
    #print("Ended Finally")

def func_calculateEventClassification(eventID):
    """
    Calculate classification for an event similar to GameDay classification.
    Uses alphabetical order instead of player ranking and age for tie-breaking.
    """
    # Get the event
    event = Event.query.filter_by(ev_id=eventID).first()
    if not event:
        print(f"Event with ID {eventID} not found")
        return
    
    try:
        # Clear existing event classification
        EventClassification.query.filter_by(ec_event_id=eventID).delete()
        db.session.commit()

        # Get all players who participated in the event (from registrations or games)
        players_from_registrations = db.session.query(EventRegistration.er_player_id).filter(
            EventRegistration.er_event_id == eventID,
            EventRegistration.er_is_substitute == False
        ).subquery()
        
        players_from_games = db.session.query(
            Game.gm_idPlayer_A1.label('player_id')
        ).filter(Game.gm_idEvent == eventID, Game.gm_idPlayer_A1.isnot(None)).union(
            db.session.query(Game.gm_idPlayer_A2.label('player_id'))
            .filter(Game.gm_idEvent == eventID, Game.gm_idPlayer_A2.isnot(None))
        ).union(
            db.session.query(Game.gm_idPlayer_B1.label('player_id'))
            .filter(Game.gm_idEvent == eventID, Game.gm_idPlayer_B1.isnot(None))
        ).union(
            db.session.query(Game.gm_idPlayer_B2.label('player_id'))
            .filter(Game.gm_idEvent == eventID, Game.gm_idPlayer_B2.isnot(None))
        ).subquery()

        # Get all unique player IDs from both sources
        all_player_ids = db.session.query(players_from_registrations.c.er_player_id.label('player_id')).union(
            db.session.query(players_from_games.c.player_id)
        ).distinct()
        
        players_query = Users.query.filter(Users.us_id.in_(all_player_ids))
        players_data = players_query.all()

        for player in players_data:
            id_player = player.us_id
            player_name = player.us_name

            # Check if player has any games in this event
            games_info_query = Game.query.filter(
                Game.gm_idEvent == eventID, 
                ((Game.gm_idPlayer_A1 == id_player) | (Game.gm_idPlayer_A2 == id_player) | 
                 (Game.gm_idPlayer_B1 == id_player) | (Game.gm_idPlayer_B2 == id_player)),
                ((Game.gm_result_A.isnot(None)) | (Game.gm_result_B.isnot(None)))
            )
            games_info = games_info_query.first()

            if games_info:
                # Player has played games - calculate statistics
                subquery = (
                    db.session.query(
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("3")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("3")),
                            else_=None
                        ).label("POINTS"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_A2 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_B1 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_B2 == id_player), Game.gm_result_B),
                            else_=None
                        ).label("GAMESFAVOR"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_A2 == id_player), Game.gm_result_B),
                            (and_(Game.gm_idPlayer_B1 == id_player), Game.gm_result_A),
                            (and_(Game.gm_idPlayer_B2 == id_player), Game.gm_result_A),
                            else_=None
                        ).label("GAMESAGAINST"),
                        literal_column("1").label("GAMES"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A == Game.gm_result_B), literal_column("0")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            else_=None
                        ).label("WINS"),
                        case(
                            (and_(Game.gm_idPlayer_A1 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_A2 == id_player, Game.gm_result_A < Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B1 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            (and_(Game.gm_idPlayer_B2 == id_player, Game.gm_result_A > Game.gm_result_B), literal_column("1")),
                            else_=literal_column("0")
                        ).label("LOSSES")
                    )
                    .filter(
                        Game.gm_idEvent == eventID, 
                        (Game.gm_idPlayer_A1 == id_player) | (Game.gm_idPlayer_A2 == id_player) | 
                        (Game.gm_idPlayer_B1 == id_player) | (Game.gm_idPlayer_B2 == id_player)
                    )
                    .subquery("TOTALS")
                )
                
                # Create alphabetical sort value for tie-breaking (lower = better alphabetically)
                alphabetical_sort = ord(player_name[0].upper()) if player_name else 999
                
                query = (
                    db.session.query(
                        literal_column(str(eventID)).label("EVENTID"),
                        literal_column(str(id_player)).label("PLAYERID"),
                        literal_column(f"'{player_name}'").label("PLAYERNAME"), 
                        func.sum(subquery.c.POINTS).label("POINTS"),
                        func.sum(subquery.c.WINS).label("WINS"),
                        func.sum(subquery.c.LOSSES).label("LOSSES"),
                        func.sum(subquery.c.GAMESFAVOR).label("GAMESFAVOR"),
                        func.sum(subquery.c.GAMESAGAINST).label("GAMESAGAINST"),
                        (func.sum(subquery.c.GAMESFAVOR) - func.sum(subquery.c.GAMESAGAINST)).label("GAMESDIFFERENCE"),
                        (
                            (func.sum(subquery.c.POINTS) * 100000) +
                            (func.sum(subquery.c.WINS) * 10000) +
                            (func.sum(subquery.c.GAMES) * 1000) +
                            ((func.sum(subquery.c.GAMESFAVOR) - func.sum(subquery.c.GAMESAGAINST)) * 100) +
                            # Use negative alphabetical sort so A comes before Z in ranking
                            (-alphabetical_sort)
                        ).label("RANKING")
                    )
                    .select_from(subquery)
                    .group_by("EVENTID", "PLAYERID", "PLAYERNAME")
                )
                
                result = query.all()

                for r2 in result:
                    # Write Classification
                    classification = EventClassification(
                        ec_event_id=eventID,
                        ec_player_id=r2.PLAYERID,
                        ec_points=r2.POINTS or 0,
                        ec_wins=r2.WINS or 0,
                        ec_losses=r2.LOSSES or 0,
                        ec_games_favor=r2.GAMESFAVOR or 0,
                        ec_games_against=r2.GAMESAGAINST or 0,
                        ec_games_diff=r2.GAMESDIFFERENCE or 0,
                        ec_ranking=r2.RANKING or 0,
                    )
                    db.session.add(classification)

            else:
                # Player registered but didn't play any games
                alphabetical_sort = ord(player_name[0].upper()) if player_name else 999
                classification = EventClassification(
                    ec_event_id=eventID,
                    ec_player_id=id_player,
                    ec_points=0,
                    ec_wins=0,
                    ec_losses=0,
                    ec_games_favor=0,
                    ec_games_against=0,
                    ec_games_diff=0,
                    ec_ranking=-alphabetical_sort,  # Negative for proper sorting
                )
                db.session.add(classification)

        # Commit all classifications
        db.session.commit()

        # Update event winners
        winners_query = (
            db.session.query(
                EventClassification.ec_player_id.label('idPlayer'),
                Users.us_name.label('namePlayer')
            )
            .join(Users, EventClassification.ec_player_id == Users.us_id)
            .filter(EventClassification.ec_event_id == eventID)
            .order_by(EventClassification.ec_ranking.desc())
            .limit(2)
            .subquery()
        )

        # Fetch the first winner
        winner1 = (
            db.session.query(winners_query.c.idPlayer, winners_query.c.namePlayer)
            .order_by(winners_query.c.idPlayer.asc())
            .first()
        )

        # Fetch the second winner (if exists)
        winner2 = (
            db.session.query(winners_query.c.idPlayer, winners_query.c.namePlayer)
            .order_by(winners_query.c.idPlayer.desc())
            .first()
        )

        # Update event winners
        update_data = {}
        if winner1:
            update_data[Event.ev_winner1_id] = winner1.idPlayer
        if winner2 and winner2.idPlayer != (winner1.idPlayer if winner1 else None):
            update_data[Event.ev_winner2_id] = winner2.idPlayer

        if update_data:
            db.session.query(Event).filter(Event.ev_id == eventID).update(update_data)

        # Final commit
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print(f"Error calculating event classification: {e}")
        # Handle the error, maybe log it or display a message to the user

def func_calculate_ELO_parcial():
    # Check if tb_ELO_ranking has any entries
    try:
        elo_count = db.session.query(ELOranking).count()
        if elo_count == 0:
            # Initialize all players with default ELO ratings
            players = Users.query.all()
            for player in players:
                new_elo = ELOranking(
                    pl_id=player.us_id,
                    pl_rankingNow=1000,
                    pl_totalRankingOpo=0,
                    pl_wins=0,
                    pl_losses=0,
                    pl_totalGames=0
                )
                db.session.add(new_elo)
            db.session.commit()

        # Check if there are any ELO history entries
        elo_hist_count = db.session.query(ELOrankingHist).count()
        if elo_hist_count == 0:
            # The history will be populated naturally as games are played
            pass

        # Select every game if league as K higher than 0 and is not on ranking yet
        r1 = db.session.execute(
            text(f"SELECT gm_id, gm_idPlayer_A1, gm_idPlayer_A2, gm_idPlayer_B1, gm_idPlayer_B2, gm_result_A, gm_result_B, gm_idLeague, gm_date, gm_timeStart FROM tb_game WHERE gm_idLeague IN ( SELECT lg_id FROM tb_league WHERE lg_eloK > 0 AND lg_startDate >= :start_date ) AND gm_id not in (select el_gm_id from tb_ELO_ranking_hist GROUP BY el_gm_id) AND gm_idPlayer_A1 IS NOT NULL ORDER BY gm_date ASC, gm_timeStart ASC"),
            {"start_date": datetime(2024, 1, 1)},
        ).fetchall()
        

        for d1 in r1:
            # Get current ranking for A1
            A1_ID = d1[1]
            playerInfo = db.session.execute(text(f"SELECT pl_rankingNow FROM tb_ELO_ranking WHERE pl_id=:player_id"), {'player_id': A1_ID}).fetchone()
            A1_ranking = playerInfo[0]
            
            # Get current ranking for A2
            A2_ID = d1[2]
            playerInfo = db.session.execute(text(f"SELECT pl_rankingNow FROM tb_ELO_ranking WHERE pl_id=:player_id"), {'player_id': A2_ID}).fetchone()
            A2_ranking = playerInfo[0]
            
            # Get current ranking for B1
            B1_ID = d1[3]
            playerInfo = db.session.execute(text(f"SELECT pl_rankingNow FROM tb_ELO_ranking WHERE pl_id=:player_id"), {'player_id': B1_ID}).fetchone()
            B1_ranking = playerInfo[0]
            
            # Get current ranking for B2
            B2_ID = d1[4]
            playerInfo = db.session.execute(text(f"SELECT pl_rankingNow FROM tb_ELO_ranking WHERE pl_id=:player_id"), {'player_id': B2_ID}).fetchone()
            B2_ranking = playerInfo[0]

            # Calculate current ELO from teamA and teamB
            ranking_TeamA = (A1_ranking + A2_ranking) / 2
            ranking_TeamB = (B1_ranking + B2_ranking) / 2

            ELO_idLeague = d1[7]
            leagueInfo = db.session.execute(text(f"SELECT lg_eloK FROM tb_league WHERE lg_id=:league_id"), {'league_id': ELO_idLeague}).fetchone()
            ELO_K = leagueInfo[0]

            # Calculate new ratings
            if d1[5] > d1[6]:
                # Update ratings for team A
                # Calculate rating changes for A1
                delta_A1 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamB - A1_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_wins = pl_wins + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_A1, 'player_id': A1_ID})
                # Calculate rating changes for A2
                delta_A2 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamB - A2_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_wins = pl_wins + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_A2, 'player_id': A2_ID})
                # Update ratings for team B
                # Calculate rating changes for B1
                delta_B1 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamA - B1_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_losses = pl_losses + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_B1, 'player_id': B1_ID})
                # Calculate rating changes for B2
                delta_B2 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamA - B2_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_losses = pl_losses + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_B2, 'player_id': B2_ID})
            elif d1[6] > d1[5]:
                # Update ratings for team A
                # Calculate rating changes for A1
                delta_A1 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamB - A1_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_losses = pl_losses + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_A1, 'player_id': A1_ID})
                # Calculate rating changes for A2
                delta_A2 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamB - A2_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_losses = pl_losses + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_A2, 'player_id': A2_ID})
                # Update ratings for team B
                # Calculate rating changes for B1
                delta_B1 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamA - B1_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_wins = pl_wins + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_B1, 'player_id': B1_ID})
                # Calculate rating changes for B2
                delta_B2 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamA - B2_ranking) / 400))))
                db.session.execute(text(f"UPDATE tb_ELO_ranking SET pl_rankingNow = pl_rankingNow + :delta, pl_wins = pl_wins + 1, pl_totalGames = pl_totalGames + 1 WHERE pl_id = :player_id"), {'delta': delta_B2, 'player_id': B2_ID})

            if d1[5] == 0 and d1[6] == 0:
                pass
            else:
                # Define the queries
                queries = [
                    {
                        'gm_id': d1[0],
                        'pl_id': A1_ID,
                        'date': d1[8],
                        'time_start': d1[9],
                        'teammate_id': A2_ID,
                        'op1_id': B1_ID,
                        'op2_id': B2_ID,
                        'result_team': d1[5],
                        'result_op': d1[6],
                        'before_rank': A1_ranking
                    },
                    {
                        'gm_id': d1[0],
                        'pl_id': A2_ID,
                        'date': d1[8],
                        'time_start': d1[9],
                        'teammate_id': A1_ID,
                        'op1_id': B1_ID,
                        'op2_id': B2_ID,
                        'result_team': d1[5],
                        'result_op': d1[6],
                        'before_rank': A2_ranking
                    },
                    {
                        'gm_id': d1[0],
                        'pl_id': B1_ID,
                        'date': d1[8],
                        'time_start': d1[9],
                        'teammate_id': B2_ID,
                        'op1_id': A1_ID,
                        'op2_id': A2_ID,
                        'result_team': d1[5],
                        'result_op': d1[6],
                        'before_rank': B1_ranking
                    },
                    {
                        'gm_id': d1[0],
                        'pl_id': B2_ID,
                        'date': d1[8],
                        'time_start': d1[9],
                        'teammate_id': B1_ID,
                        'op1_id': A1_ID,
                        'op2_id': A2_ID,
                        'result_team': d1[5],
                        'result_op': d1[6],
                        'before_rank': B2_ranking
                    }
                ]
                try:
                    for query in queries:
                        # Convert date strings to Python date objects
                        el_date = datetime.strptime(query['date'], '%Y-%m-%d')
                        # Parse time string, handles both HH:MM:SS and HH:MM:SS.microseconds formats
                        el_start_time = datetime.strptime(query['time_start'].split('.')[0], '%H:%M:%S').time()
                        # Execute the query
                        db.session.add(
                            ELOrankingHist(
                                el_gm_id=query['gm_id'],
                                el_pl_id=query['pl_id'],
                                el_date=el_date,
                                el_startTime=el_start_time,
                                el_pl_id_teammate=query['teammate_id'],
                                el_pl_id_op1=query['op1_id'],
                                el_pl_id_op2=query['op2_id'],
                                el_result_team=query['result_team'],
                                el_result_op=query['result_op'],
                                el_beforeRank=query['before_rank'],
                                el_afterRank=db.session.query(ELOranking.pl_rankingNow).filter(ELOranking.pl_id == query['pl_id']).scalar() or 1000
                            )
                        )
                        db.session.commit()
                    # Commit the transaction
                    db.session.commit()

                except Exception as e:
                    # Rollback the transaction if an error occurs
                    print("Error RHIST:", e)
                    db.session.rollback()

                finally:
                    # Close the session
                    db.session.close()

    except Exception as e:
        print("Error99:", e)

    #print("Print from end of ELO calc")

def func_create_gameday_games(league_id, gameday_id):
    """Helper function to create games for a gameday
    Args:
        league_id (int): The ID of the league
        gameday_id (int): The ID of the gameday
    """
    league = League.query.get_or_404(league_id)
    gameday = GameDay.query.get_or_404(gameday_id)

    # Get the courts for the league from LeagueCourts
    league_courts = LeagueCourts.query.filter_by(lc_league_id=league_id).all()
    if not league_courts:
        print(f"Warning: No courts found for league {league_id}")
        return

    # Get the start time and settings from league
    game_start_time = league.lg_startTime
    warm_up_minutes = league.lg_minWarmUp or 0
    game_minutes = league.lg_minPerGame or 0
    between_games = league.lg_minBetweenGames or 0

    # Calculate number of rounds based on number of teams
    num_teams = league.lg_nbrTeams
    if num_teams < 4 or num_teams % 2 != 0:
        print(f"Error: Invalid number of teams: {num_teams}")
        return
        
    num_rounds = num_teams - 1
    courts_available = len(league_courts)
    
    # Initialize the base datetime for the first round
    base_datetime = datetime.combine(gameday.gd_date, game_start_time)
    last_game_end = None
    
    # For each round
    for round_num in range(num_rounds):
        # Calculate round start time
        if round_num == 0:
            # First round: Add warm-up time to the league start time
            round_start_datetime = base_datetime + timedelta(minutes=warm_up_minutes)
        else:
            # Subsequent rounds: Start after the between-games time from last game's end
            round_start_datetime = datetime.combine(gameday.gd_date, last_game_end) + timedelta(minutes=between_games)
        
        round_start_time = round_start_datetime.time()
        
        # Create games for this round using available courts
        for court_index, court_relation in enumerate(league_courts):
            # Calculate game end time
            game_end_datetime = round_start_datetime + timedelta(minutes=game_minutes)
            game_end_time = game_end_datetime.time()
            
            game = Game(
                gm_idLeague=league_id,
                gm_idGameDay=gameday_id,
                gm_date=gameday.gd_date,
                gm_timeStart=round_start_time,
                gm_timeEnd=game_end_time,
                gm_court=court_relation.lc_court_id
            )
            db.session.add(game)
            
            # Update last game end time for next round calculation
            last_game_end = game_end_time
    
    db.session.commit()

def func_create_games_for_gameday(gameDayID):
    #CHECK IF IN tb_game there are already all the games necessary
    GameD = GameDay.query.filter_by(gd_id=gameDayID).first()
    league = League.query.filter_by(lg_id=GameD.gd_idLeague).first()
    league_nbrTeams= league.lg_nbrTeams
    startTime = league.lg_startTime
    league_minWarmUp = league.lg_minWarmUp
    league_minPerGame = league.lg_minPerGame
    league_minBetweenGames = league.lg_minBetweenGames
    leagueId = league.lg_id
    gameDay_Day = GameD.gd_date

    if league_nbrTeams == 2:
        necessary_games = 1
    elif league_nbrTeams == 3:
        necessary_games = 3
    elif league_nbrTeams == 4:
        necessary_games = 6
    elif league_nbrTeams == 5:
        necessary_games = 10
    elif league_nbrTeams == 6:
        necessary_games = 15
    elif league_nbrTeams == 7:
        necessary_games = 21
    elif league_nbrTeams == 8:
        necessary_games = 28
    else:
        necessary_games = 0

    # $gameStart = date('H:i:s', strtotime("+".$league_minWarmUp." minutes", strtotime($startTime)));
    # $gameEnd = date('H:i:s', strtotime("+".$league_minPerGame." minutes", strtotime($gameStart)));
    # Assuming you have startTime as a datetime object, league_minWarmUp, and league_minPerGame as integers
    strTime = datetime.strptime(str(startTime), "%H:%M:%S")  # Convert startTime to datetime if needed

    # Add league_minWarmUp minutes to startTime
    gameStart = strTime + timedelta(minutes=league_minWarmUp)

    # Add league_minPerGame minutes to gameStart
    gameEnd = gameStart + timedelta(minutes=league_minPerGame)

    # Convert gameStart and gameEnd to string format 'H:i:s'
    gameStart_str = gameStart.strftime("%H:%M:%S")
    gameEnd_str = gameEnd.strftime("%H:%M:%S")  
    gameDay_Day_str = gameDay_Day.strftime("%Y-%m-%d")
    #print(gameDay_Day_str)                                      
    # if there are games but the number of games is not the same as the necessary delete all the games
    num_games = Game.query.filter_by(gm_idGameDay=gameDayID).count()
    if num_games != necessary_games:
        Game.query.filter_by(gm_idGameDay=gameDayID).delete()
        # Commit the changes to the database
        db.session.commit()
        num_games = 0

    # if there aren't any games or if they were deleted in the last step create all the necessary games
    if num_games == 0:
        if league_nbrTeams == 2:
            necessary_games = 1
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
        
        elif league_nbrTeams == 3:
            necessary_games = 3
            # Game 1
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 2
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'B', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 3
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'C', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
        
        elif league_nbrTeams == 4:
            necessary_games = 6
            # Game 1 and 2
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'C', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 3 and 4
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'B', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 5 and 6
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'B', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()

        elif league_nbrTeams == 5:
            necessary_games = 10
            # Game 1 and 2
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'B', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 3 and 4
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'C', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'D', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 5 and 6
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'E', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'A', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 7 and 8
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'B', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'C', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 9 and 10
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'D', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'E', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
        
        elif league_nbrTeams == 6:
            necessary_games = 15
            # Game 1, 2 and 3 ROUND 1
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'B', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'C', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'D', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 4, 5 and 6 ROUND 2
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'C', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'F', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'B', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 7, 8 and 9 ROUND 3
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'F', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'B', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'A', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 10, 11 and 12 ROUND 4
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'D', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'E', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'F', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 13, 14 and 15 ROUND 5
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'E', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'A', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'D', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            
        elif league_nbrTeams == 7:
            necessary_games = 21
            # Game 1, 2 and 3 ROUND 1
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'B', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'C', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 4, 5 and 6 ROUND 2
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'D', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'E', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'F', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 7, 8 and 9 ROUND 3
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'B', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'C', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'D', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 10, 11 and 12 ROUND 4
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'E', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'F', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'G', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # Game 13, 14 and 15 ROUND 5
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'C', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'D', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'E', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 6
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'F', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'G', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'A', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 7
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'G', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'A', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'B', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()

        elif league_nbrTeams == 8:
            necessary_games = 28
            # ROUND 1
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameday_day, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'B', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameday_day": gameDay_Day_str, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'C', 'H')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'D', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'E', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 2
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'C', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'A', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'H', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'B', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 3
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'F', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'G', 'H')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'D', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'E', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 4
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'G', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'H', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'B', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'F', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 5
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'A', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'D', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'E', 'H')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'F', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 6
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'D', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'H', 'A')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'B', 'G')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'C', 'F')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            # ROUND 7
            gameStart = gameEnd + timedelta(minutes=league_minBetweenGames)
            gameEnd = gameStart + timedelta(minutes=league_minPerGame)
            gameStart_str = gameStart.strftime("%H:%M:%S")
            gameEnd_str = gameEnd.strftime("%H:%M:%S")  
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 1', 0, 0, 'G', 'C')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 2', 0, 0, 'H', 'B')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 3', 0, 0, 'A', 'E')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            db.session.execute(
                text(f"INSERT INTO tb_game (gm_idLeague, gm_idGameDay, gm_date, gm_timeStart, gm_timeEnd, gm_court, gm_result_A, gm_result_B, gm_teamA, gm_teamB) VALUES (:league_id, :gameDay_id, :gameStart, :gameEnd, 'Campo 4', 0, 0, 'F', 'D')"),
                {"league_id": leagueId, "gameDay_id": gameDayID, "gameStart": gameStart_str, "gameEnd": gameEnd_str}
            )
            db.session.commit()
            
        else:
            necessary_games = 0

def func_create_gameday_games_full(league_id, gameday_id):
    """Helper function to create games for a gameday with team assignments
    Args:
        league_id (int): The ID of the league
        gameday_id (int): The ID of the gameday
    """
    league = League.query.get_or_404(league_id)
    gameday = GameDay.query.get_or_404(gameday_id)

    # Get the courts for the league from LeagueCourts
    league_courts = LeagueCourts.query.filter_by(lc_league_id=league_id).all()
    if not league_courts:
        print(f"Warning: No courts found for league {league_id}")
        return

    # Get league settings
    game_start_time = league.lg_startTime
    warm_up_minutes = league.lg_minWarmUp or 0
    game_minutes = league.lg_minPerGame or 0
    between_games = league.lg_minBetweenGames or 0
    num_teams = league.lg_nbrTeams

    # Calculate necessary games based on number of teams
    necessary_games = {
        2: 1, 3: 3, 4: 6, 5: 10, 
        6: 15, 7: 21, 8: 28
    }.get(num_teams, 0)

    if necessary_games == 0:
        print(f"Error: Invalid number of teams: {num_teams}")
        return

    # Delete existing games if count doesn't match
    num_existing = Game.query.filter_by(gm_idGameDay=gameday_id).count()
    if num_existing != necessary_games:
        Game.query.filter_by(gm_idGameDay=gameday_id).delete()
        db.session.commit()

    # Initialize the base datetime for the first round
    base_datetime = datetime.combine(gameday.gd_date, game_start_time)
    last_game_end = None
    
    # Team pairings for each number of teams
    team_pairings = {
        2: [('A','B')],
        3: [('A','B'), ('B','C'), ('C','A')],
        4: [('A','B'), ('C','D'), ('A','C'), ('B','D'), ('A','D'), ('B','C')],
        5: [('A','B'), ('C','D'), ('A','C'), ('B','E'), ('D','E'), ('A','D'), ('B','C'), ('E','C'), ('D','B'), ('A','E')],
        6: [('A','B'), ('C','D'), ('E','F'), ('A','C'), ('B','D'), ('E','A'), ('F','B'), ('C','E'), ('D','F'), ('A','D'),
            ('B','E'), ('C','F'), ('A','F'), ('B','C'), ('D','E')],
        7: [('A','B'), ('C','D'), ('E','F'), ('A','C'), ('B','D'), ('F','G'), ('D','E'), ('A','F'), ('B','G'), ('C','E'),
            ('A','D'), ('B','E'), ('F','C'), ('G','A'), ('E','B'), ('D','F'), ('G','C'), ('A','E'), ('B','F'), ('D','G'), ('C','F')],
        8: [('A','B'), ('C','D'), ('E','F'), ('G','H'), ('A','C'), ('B','D'), ('E','G'), ('F','H'), ('A','D'), ('B','C'),
            ('E','H'), ('F','G'), ('A','E'), ('B','F'), ('C','G'), ('D','H'), ('A','F'), ('B','E'), ('C','H'), ('D','G'),
            ('A','G'), ('B','H'), ('C','E'), ('D','F'), ('A','H'), ('B','G'), ('C','F'), ('D','E')]
    }

    pairs = team_pairings[num_teams]
    courts_available = len(league_courts)
    num_rounds = (necessary_games + courts_available - 1) // courts_available

    game_index = 0
    for round_num in range(num_rounds):
        # Calculate round start time
        if round_num == 0:
            round_start_datetime = base_datetime + timedelta(minutes=warm_up_minutes)
        else:
            round_start_datetime = datetime.combine(gameday.gd_date, last_game_end) + timedelta(minutes=between_games)
        
        round_start_time = round_start_datetime.time()
        
        # Create games for this round using available courts
        for court_index in range(min(courts_available, necessary_games - game_index)):
            if game_index >= len(pairs):
                break
                
            # Calculate game end time
            game_end_datetime = round_start_datetime + timedelta(minutes=game_minutes)
            game_end_time = game_end_datetime.time()
            
            # Get teams for this game
            team_a, team_b = pairs[game_index]
            
            game = Game(
                gm_idLeague=league_id,
                gm_idGameDay=gameday_id,
                gm_date=gameday.gd_date,
                gm_timeStart=round_start_time,
                gm_timeEnd=game_end_time,
                gm_court=league_courts[court_index].lc_court_id,
                gm_result_A=0,
                gm_result_B=0,
                gm_teamA=team_a,
                gm_teamB=team_b
            )
            db.session.add(game)
            game_index += 1
            
            # Update last game end time for next round calculation
            last_game_end = game_end_time
    
    db.session.commit()

def func_create_league_gamedays(league_id, league_name, start_date, num_days):
    """Helper function to create gamedays for a league
    Args:
        league_id (int): The ID of the league
        league_name (str): The name of the league 
        start_date (datetime): The start date for the first gameday
        num_days (int): Number of gamedays to create
    """
    current_date = start_date
    for day_number in range(1, int(num_days) + 1):
        gameday = GameDay(
            gd_idLeague=league_id,
            gd_date=current_date,
            gd_status='pending',  # Initial status
            gd_gameDayName=f"{league_name} {day_number}"
        )
        db.session.add(gameday)
        db.session.commit()
        new_gameday_id = gameday.gd_id
        func_create_gameday_games_full(league_id, new_gameday_id)
        current_date += timedelta(days=7)  # Next week

def func_calculate_ELO_full():
    #print("Print from beggining of ELO calc")
    # Delete all rows from tb_ELO_ranking
    try:
        db.session.execute(
            text(f"DELETE FROM tb_ELO_ranking")
        )
        db.session.commit()             
    except Exception as e:
        print("Error1:", e)

    # Delete all rows from tb_ELO_ranking_hist
    try:
        db.session.execute(
            text(f"DELETE FROM tb_ELO_ranking_hist")
        )
        db.session.commit()
    except Exception as e:
        print("Error1:", e)

    # Write every player with 1000 points and 0 games
    try:
        # Get all users who are players from Users model
        users = Users.query.filter_by(us_is_player=True).all()

        for user in users:
            # Create new ELO ranking entry for each player with default values
            new_elo = ELOranking(
                pl_id=user.us_id,
                pl_rankingNow=1000,  # Default ELO rating
                pl_totalRankingOpo=0,
                pl_wins=0,
                pl_losses=0,
                pl_totalGames=0
            )
            db.session.add(new_elo)

        # Commit the transaction
        db.session.commit()
    except Exception as e:
        print("Error2:", e)
        db.session.rollback()

    # Select every game if league has K higher than 0
    try:
        # Query games using SQLAlchemy ORM
        games = db.session.query(Game).join(
            League, Game.gm_idLeague == League.lg_id
        ).filter(
            League.lg_eloK > 0,
            League.lg_startDate >= datetime(2024, 1, 1),
            Game.gm_idPlayer_A1.isnot(None)
        ).order_by(
            Game.gm_date.asc(), 
            Game.gm_timeStart.asc()
        ).all()
        
        for game in games:
            # Get current ranking for A1
            A1_ID = game.gm_idPlayer_A1
            A1_elo = ELOranking.query.get(A1_ID)
            A1_ranking = A1_elo.pl_rankingNow if A1_elo else 1000
            
            # Get current ranking for A2
            A2_ID = game.gm_idPlayer_A2
            A2_elo = ELOranking.query.get(A2_ID)
            A2_ranking = A2_elo.pl_rankingNow if A2_elo else 1000
            
            # Get current ranking for B1
            B1_ID = game.gm_idPlayer_B1
            B1_elo = ELOranking.query.get(B1_ID)
            B1_ranking = B1_elo.pl_rankingNow if B1_elo else 1000
            
            # Get current ranking for B2
            B2_ID = game.gm_idPlayer_B2
            B2_elo = ELOranking.query.get(B2_ID)
            B2_ranking = B2_elo.pl_rankingNow if B2_elo else 1000

            # Calculate current ELO from teamA and teamB
            ranking_TeamA = (A1_ranking + A2_ranking) / 2
            ranking_TeamB = (B1_ranking + B2_ranking) / 2

            # Get league K factor
            league = League.query.get(game.gm_idLeague)
            ELO_K = league.lg_eloK

            # Calculate new ratings
            if game.gm_result_A > game.gm_result_B:
                # Update ratings for team A
                # Calculate rating changes for A1
                delta_A1 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamB - A1_ranking) / 400))))
                if A1_elo:
                    A1_elo.pl_rankingNow += delta_A1
                    A1_elo.pl_wins += 1
                    A1_elo.pl_totalGames += 1
                
                # Calculate rating changes for A2
                delta_A2 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamB - A2_ranking) / 400))))
                if A2_elo:
                    A2_elo.pl_rankingNow += delta_A2
                    A2_elo.pl_wins += 1
                    A2_elo.pl_totalGames += 1
                
                # Update ratings for team B
                # Calculate rating changes for B1
                delta_B1 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamA - B1_ranking) / 400))))
                if B1_elo:
                    B1_elo.pl_rankingNow += delta_B1
                    B1_elo.pl_losses += 1
                    B1_elo.pl_totalGames += 1
                
                # Calculate rating changes for B2
                delta_B2 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamA - B2_ranking) / 400))))
                if B2_elo:
                    B2_elo.pl_rankingNow += delta_B2
                    B2_elo.pl_losses += 1
                    B2_elo.pl_totalGames += 1
            
            elif game.gm_result_B > game.gm_result_A:
                # Update ratings for team A
                # Calculate rating changes for A1
                delta_A1 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamB - A1_ranking) / 400))))
                if A1_elo:
                    A1_elo.pl_rankingNow += delta_A1
                    A1_elo.pl_losses += 1
                    A1_elo.pl_totalGames += 1
                
                # Calculate rating changes for A2
                delta_A2 = ELO_K * (0 - (1 / (1 + 10 ** ((ranking_TeamB - A2_ranking) / 400))))
                if A2_elo:
                    A2_elo.pl_rankingNow += delta_A2
                    A2_elo.pl_losses += 1
                    A2_elo.pl_totalGames += 1
                
                # Update ratings for team B
                # Calculate rating changes for B1
                delta_B1 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamA - B1_ranking) / 400))))
                if B1_elo:
                    B1_elo.pl_rankingNow += delta_B1
                    B1_elo.pl_wins += 1
                    B1_elo.pl_totalGames += 1
                
                # Calculate rating changes for B2
                delta_B2 = ELO_K * (1 - (1 / (1 + 10 ** ((ranking_TeamA - B2_ranking) / 400))))
                if B2_elo:
                    B2_elo.pl_rankingNow += delta_B2
                    B2_elo.pl_wins += 1
                    B2_elo.pl_totalGames += 1

            # Save the updated ELO values
            db.session.commit()

            # Skip history for games with no score (0-0)
            if game.gm_result_A == 0 and game.gm_result_B == 0:
                continue
            else:
                # Define data for history records
                history_entries = [
                    {
                        'game_id': game.gm_id,
                        'player_id': A1_ID,
                        'date': game.gm_date,
                        'time_start': game.gm_timeStart,
                        'teammate_id': A2_ID,
                        'op1_id': B1_ID,
                        'op2_id': B2_ID,
                        'result_team': game.gm_result_A,
                        'result_op': game.gm_result_B,
                        'before_rank': A1_ranking
                    },
                    {
                        'game_id': game.gm_id,
                        'player_id': A2_ID,
                        'date': game.gm_date,
                        'time_start': game.gm_timeStart,
                        'teammate_id': A1_ID,
                        'op1_id': B1_ID,
                        'op2_id': B2_ID,
                        'result_team': game.gm_result_A,
                        'result_op': game.gm_result_B,
                        'before_rank': A2_ranking
                    },
                    {
                        'game_id': game.gm_id,
                        'player_id': B1_ID,
                        'date': game.gm_date,
                        'time_start': game.gm_timeStart,
                        'teammate_id': B2_ID,
                        'op1_id': A1_ID,
                        'op2_id': A2_ID,
                        'result_team': game.gm_result_B,
                        'result_op': game.gm_result_A,
                        'before_rank': B1_ranking
                    },
                    {
                        'game_id': game.gm_id,
                        'player_id': B2_ID,
                        'date': game.gm_date,
                        'time_start': game.gm_timeStart,
                        'teammate_id': B1_ID,
                        'op1_id': A1_ID,
                        'op2_id': A2_ID,
                        'result_team': game.gm_result_B,
                        'result_op': game.gm_result_A,
                        'before_rank': B2_ranking
                    }
                ]
                try:
                    for entry in history_entries:
                        # Get player and calculate after rank
                        player_elo = ELOranking.query.get(entry['player_id'])
                        after_rank = player_elo.pl_rankingNow if player_elo else 1000
                        
                        # Create and add history entry
                        hist_entry = ELOrankingHist(
                            el_gm_id=entry['game_id'],
                            el_pl_id=entry['player_id'],
                            el_date=entry['date'],
                            el_startTime=entry['time_start'],
                            el_pl_id_teammate=entry['teammate_id'],
                            el_pl_id_op1=entry['op1_id'],
                            el_pl_id_op2=entry['op2_id'],
                            el_result_team=entry['result_team'],
                            el_result_op=entry['result_op'],
                            el_beforeRank=entry['before_rank'],
                            el_afterRank=after_rank
                        )
                        db.session.add(hist_entry)
                    
                    # Commit all history entries
                    db.session.commit()

                except Exception as e:
                    # Rollback the transaction if an error occurs
                    print("Error RHIST:", e)
                    db.session.rollback()

    except Exception as e:
        print("Error99:", e)
        db.session.rollback()

    #print("Print from end of ELO calc")
