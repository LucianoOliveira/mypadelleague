from flask_login import login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, func, cast, String, text, desc, case, literal_column
from flask import render_template, Blueprint, flash, request, redirect, url_for
from website import db
from website.models import League, Club, Users, GameDay, GameDayPlayer, Game, LeagueClassification, GameDayClassification, ClubAuthorization, LeaguePlayers
from PIL import Image
from datetime import datetime, date, timedelta
from .tools import *
import json
from flask import session

def translate(text):
    # Import translations file
    with open('translations/translations.json', 'r', encoding='utf-8') as f:
        translations = json.load(f)
    
    # Get current language from cookie or default to English
    lang = request.cookies.get('lang', 'en')
    
    # Try to get translation, return original text if not found
    if text in translations and lang in translations[text]:
        return translations[text][lang]
    return text

# Gameday management routes
def func_create_gamedays():
    # Get league_id from query parameter
    league_id = request.args.get('league_id')
    if not league_id:
        flash(translate('League ID is required'), 'error')
        return redirect(url_for('views.managementLeagues'))
    
    # Get the league
    league = League.query.get_or_404(league_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this league!'), 'error')
        return redirect(url_for('views.managementLeagues'))
    
    # Create GameDays for the league using helper function
    func_create_league_gamedays(league.lg_id, league.lg_name, league.lg_startDate, league.lg_nbrDays)
    db.session.commit()

    flash(translate('Game days created successfully!'), 'success')
    return redirect(url_for('views.edit_league', league_id=league_id))

def func_create_gameday_games_route(league_id, gameday_id):
    # Get the league
    league = League.query.get_or_404(league_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to create games for this gameday!'), 'error')
        return redirect(url_for('views.managementLeagues'))
    
    # Create the games using the helper function
    func_create_gameday_games_full(league_id, gameday_id)
    
    flash(translate('Games created successfully!'), 'success')
    return redirect(url_for('views.edit_gameday', gameday_id=gameday_id))

def func_edit_gameday(gameday_id):
    # Get the gameday
    gameday = GameDay.query.get_or_404(gameday_id)
    results = Game.query.filter_by(gm_idGameDay=gameday_id).order_by(Game.gm_timeStart).all()
    
    # Precompute if any game is missing players
    button_disabled = any(
        game.gm_idPlayer_A1 is None or 
        game.gm_idPlayer_A2 is None or 
        game.gm_idPlayer_B1 is None or 
        game.gm_idPlayer_B2 is None 
        for game in results
    )
    
    classifications = GameDayClassification.query.filter_by(gc_idGameDay=gameday_id).order_by(desc(GameDayClassification.gc_ranking)).all()
    
    # Get the associated league
    league = League.query.get_or_404(gameday.gd_idLeague)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this gameday!'), 'error')
        return redirect(url_for('views.managementLeagues'))
    
    # Get the club information
    club = Club.query.get_or_404(league.lg_club_id)
    
    if request.method == 'POST':
        new_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
        original_date = datetime.strptime(request.form.get('original_date'), '%Y-%m-%d')
        now = datetime.now().date()

        # Check if the original date is in the past
        if original_date.date() < now:
            flash(translate('Cannot modify past gamedays'), 'error')
            return redirect(url_for('views.edit_league', league_id=league.lg_id) + '#gamedays')

        update_subsequent = request.form.get('update_subsequent') == 'true'
        
        # Calculate the date difference
        date_diff = new_date - original_date
        
        # Get all gamedays that need to be updated, including the current one
        gamedays_to_update = [gameday]  # Start with current gameday
        if update_subsequent:
            subsequent_gamedays = GameDay.query.filter(
                GameDay.gd_idLeague == league.lg_id,
                GameDay.gd_date > original_date
            ).order_by(GameDay.gd_date).all()
            gamedays_to_update.extend(subsequent_gamedays)
        
        # Update all affected gamedays and their games
        for gd in gamedays_to_update:
            # If it's the current gameday, use new_date directly
            if gd.gd_id == gameday_id:
                gd.gd_date = new_date
            else:
                # For subsequent gamedays, apply the date difference
                gd.gd_date += date_diff
            
            # Update all games for this gameday
            for game in gd.games:
                game.gm_date = gd.gd_date
        
        db.session.commit()
        
        # Update league status if this is the first gameday and its date has arrived
        first_gameday = GameDay.query.filter_by(gd_idLeague=league.lg_id).order_by(GameDay.gd_date).first()
        if first_gameday and first_gameday.gd_date <= datetime.now().date() and league.lg_status == "registration complete":
            league.lg_status = "being played"
            db.session.commit()
        
        flash(translate('Game day date updated successfully!'), 'success')
        return redirect(url_for('views.edit_league', league_id=league.lg_id) + '#gamedays')
    
    gameDayPlayers = GameDayPlayer.query.filter_by(gp_idGameDay=gameday_id).all()
    number_of_teamsGD = len(gameDayPlayers)
    number_of_teams_league = league.lg_nbrTeams
    playersGameDay = GameDayPlayer.query.filter_by(gp_idGameDay=gameday_id).order_by(GameDayPlayer.gp_team.asc(), GameDayPlayer.gp_id.asc()).all()
    players_data = Users.query.join(
        LeaguePlayers, 
        Users.us_id == LeaguePlayers.lp_player_id
    ).filter(
        LeaguePlayers.lp_league_id == league.lg_id
    ).order_by(Users.us_name).all()
    league_id = league.lg_id
    gameDay_id = gameday_id
    # Organize players by team
    teams = {}
    for player in playersGameDay:
        if player.gp_team not in teams:
            teams[player.gp_team] = []
        teams[player.gp_team].append(player)
    
    return render_template('gameday_edit.html',
                         user=current_user,
                         gameday=gameday,
                         results=results,
                         gameday_classification=classifications,
                         number_of_teamsGD=number_of_teamsGD,
                         number_of_teams_league=number_of_teams_league,
                         players_data=players_data,
                         gameDayPlayers=gameDayPlayers,
                         league_id=league_id,
                         gameDay_id=gameDay_id,
                         league=league,
                         club=club,
                         teams=teams,
                         button_disabled=button_disabled,
                         has_game_results=any(game.gm_result_A is not None or game.gm_result_B is not None for game in results)) 

def func_insert_game_day_players(gameDayID):
    gameDay_data = GameDay.query.filter_by(gd_id=gameDayID).first()
    leagueID = gameDay_data.gd_idLeague
    # DONE - Add logic for inserting game day players
    league_id = request.form.get('leagueId')
    # gameDay_id = request.form.get('gameDayId')
    gameDay_id = gameDayID
    type_of_teams = request.form.get('defineTeams')
    alpha_arr = [chr(i) for i in range(ord('A'), ord('Z') + 1)]
    league_info = League.query.with_entities(League.lg_nbrTeams).filter_by(lg_id=league_id).first()
    if league_info:
        num_players = league_info[0] * 2
    else:
        num_players = 0

    # before doing anything we should delete all the players from the gameday and update classification
    func_delete_gameday_players_upd_class(gameDayID)

    # check if games are created and if not, create them
    # func_create_games_for_gameday(gameDayID)
    func_create_gameday_games_full(league_id, gameDayID)

    if type_of_teams == 'ranking':
        num_rankings = LeagueClassification.query.filter_by(lc_idLeague=league_id).count()
        if num_rankings == 0:
            type_of_teams = 'random'


    # FOR RANKING *************************************************************************************
    if type_of_teams == 'ranking':
        players_array = []
        for i in range(num_players):
            id_player = i + 1
            request_player = f"player{id_player}"
            player_id = request.form[request_player]
            # Get Ranking from player
            player_ranking = 0
            try:
                ranking_info = db.session.execute(
                    text(f"SELECT lc_ranking FROM tb_leagueClassification WHERE lc_idLeague=:league_id and lc_idPlayer=:player_id"),
                    {"league_id": league_id, "player_id": player_id}
                ).fetchone()
                if ranking_info:
                    player_ranking = ranking_info[0] * 100            
            except Exception as e:
                print("Error:", e)

            # if ranking is 0 we assume age/100 as ranking
            if player_ranking==0:
                player = Users.query.filter_by(us_id=player_id).first()
                if player:
                    player_birthday = player.us_birthday
                    player_age = func_calculate_player_age(player_birthday)
                    player_ranking = player_age/100  

            players_array.append({"id": player_id, "ranking": player_ranking})

        
        players_array.sort(key=lambda x: x["ranking"], reverse=True)

        try:
            # Delete all existing records on tb_gameDayPlayer
            db.session.execute(
                text(f"DELETE FROM tb_gameDayPlayer WHERE gp_idLeague=:league_id and gp_idGameDay=:gameDay_id"),
                {"league_id": league_id, "gameDay_id": gameDay_id}
            )
            db.session.commit()
        except Exception as e:
            print("Error DELETE tb_gameDayPlayer:", e)

        num_teams = num_players // 2
        for j in range(num_teams):
            team_name = chr(ord('A') + j)

            player1_result = players_array.pop(0)
            player1_team_id = player1_result['id']
            player1_team_name = Users.query.get(player1_team_id).us_name

            player2_result = players_array.pop()
            player2_team_id = player2_result['id']
            player2_team_name = Users.query.get(player2_team_id).us_name

            for player_id, player_name in [(player1_team_id, player1_team_name), (player2_team_id, player2_team_name)]:
                try:
                    game_day_player = GameDayPlayer(
                        gp_idLeague=league_id,
                        gp_idGameDay=gameDay_id,
                        gp_idPlayer=player_id,
                        gp_team=team_name
                    )
                    db.session.add(game_day_player)
                    db.session.commit()
                except Exception as e:
                    print("Error:", e)


            # go through all the teams in GameDayPlayer
            gd_players = GameDayPlayer.query.filter_by(gp_idGameDay=gameDay_id).order_by(GameDayPlayer.gp_team.asc(), GameDayPlayer.gp_id.asc()).all()
    
            # Organize players by team
            teams = {}
            for gd_player in gd_players:
                if gd_player.gp_team not in teams:
                    teams[gd_player.gp_team] = []
                teams[gd_player.gp_team].append(gd_player)

            
            for team, players in teams.items():
                player1ID=0
                player1Name=''
                player2ID=0
                player2Name=''
                for player in players:
                    if player1ID==0:
                        player1ID = player.gp_idPlayer
                        player1Name = player.player.us_name
                    else:
                        player2ID = player.gp_idPlayer
                        player2Name = player.player.us_name

                db.session.execute(
                text(f"update tb_game set gm_idPlayer_A1=:player1ID, gm_idPlayer_A2=:player2ID where gm_idGameDay=:gameDay_id and gm_teamA=:team"),
                    {"player1ID": player1ID, "player2ID": player2ID, "gameDay_id": gameDay_id, "team": team}
                )
                db.session.commit()
                db.session.execute(
                text(f"update tb_game set gm_idPlayer_B1=:player1ID, gm_idPlayer_B2=:player2ID where gm_idGameDay=:gameDay_id and gm_teamB=:team"),
                    {"player1ID": player1ID, "player2ID": player2ID, "gameDay_id": gameDay_id, "team": team}
                )
                db.session.commit()

    # FOR RANDOM*******************************************************************************                
    elif type_of_teams == 'random':
        # Fill the players_array with the players selected in the page
        players_array = []
        for i in range(num_players):
            id_player = i + 1
            request_player = f"player{id_player}"
            player_id = request.form[request_player]
            players_array.append(player_id)

        try:
            # Delete every player from tb_gameDayPlayer for that gameday
            GameDayPlayer.query.filter_by(gp_idLeague=league_id, gp_idGameDay=gameDay_id).delete()
            db.session.commit()
        except Exception as e:
            print("Error Delete:", e)

        import random
        random.shuffle(players_array)

        num_teams = num_players // 2
        for j in range(num_teams):
            team_name = chr(ord('A') + j)

            player1_team_id = players_array.pop(0)
            player1_team_name = Users.query.get(player1_team_id).us_name

            player2_team_id = players_array.pop()
            player2_team_name = Users.query.get(player2_team_id).us_name

            for player_id, player_name in [(player1_team_id, player1_team_name), (player2_team_id, player2_team_name)]:
                try:
                    game_day_player = GameDayPlayer(
                        gp_idLeague=league_id,
                        gp_idGameDay=gameDay_id,
                        gp_idPlayer=player_id,
                        gp_team=team_name
                    )
                    db.session.add(game_day_player)
                    db.session.commit()
                except Exception as e:
                    print(f"Error: {e}")

            # go through all the teams in GameDayPlayer
            gd_players = GameDayPlayer.query.filter_by(gp_idGameDay=gameDay_id).order_by(GameDayPlayer.gp_team.asc(), GameDayPlayer.gp_id.asc()).all()
    
            # Organize players by team
            teams = {}
            for gd_player in gd_players:
                if gd_player.gp_team not in teams:
                    teams[gd_player.gp_team] = []
                teams[gd_player.gp_team].append(gd_player)

            
            for team, players in teams.items():
                player1ID=0
                player1Name=''
                player2ID=0
                player2Name=''
                for player in players:
                    if player1ID==0:
                        player1ID = player.gp_idPlayer
                        player1Name = player.player.us_name
                    else:
                        player2ID = player.gp_idPlayer
                        player2Name = player.player.us_name

                db.session.execute(
                text(f"update tb_game set gm_idPlayer_A1=:player1ID, gm_namePlayer_A1=:player1Name, gm_idPlayer_A2=:player2ID, gm_namePlayer_A2=:player2Name where gm_idGameDay=:gameDay_id and gm_teamA=:team"),
                    {"player1ID": player1ID, "player1Name": player1Name, "player2ID": player2ID, "player2Name": player2Name, "gameDay_id": gameDay_id, "team": team}
                )
                db.session.commit()
                db.session.execute(
                text(f"update tb_game set gm_idPlayer_B1=:player1ID, gm_namePlayer_B1=:player1Name, gm_idPlayer_B2=:player2ID, gm_namePlayer_B2=:player2Name where gm_idGameDay=:gameDay_id and gm_teamB=:team"),
                    {"player1ID": player1ID, "player1Name": player1Name, "player2ID": player2ID, "player2Name": player2Name, "gameDay_id": gameDay_id, "team": team}
                )
                db.session.commit()

    # FOR MANUAL*************************************************************************************
    elif type_of_teams == 'manual':
        players_array = []
        for i in range(num_players):
            id_player = i + 1
            request_player = f"player{id_player}"
            player_id = request.form[request_player]
            players_array.append(player_id)

        try:
            # Delete every player from tb_gameDayPlayer for that gameday
            db.session.execute(
                text(f"DELETE FROM tb_gameDayPlayer WHERE gp_idLeague=:league_id and gp_idGameDay=:gameDay_id"),
                {"league_id": league_id, "gameDay_id": gameDay_id}
            )
            db.session.commit()
        except Exception as e:
            print("Error Delete:", e)

        num_teams = num_players // 2
        for j in range(num_teams):
            team_name = chr(ord('A') + j)

            player1_team_id = players_array.pop(0)
            player1_team_name = Users.query.get(player1_team_id).us_name

            player2_team_id = players_array.pop(0)
            player2_team_name = Users.query.get(player2_team_id).us_name

            for player_id, player_name in [(player1_team_id, player1_team_name), (player2_team_id, player2_team_name)]:
                try:
                    game_day_player = GameDayPlayer(
                        gp_idLeague=league_id,
                        gp_idGameDay=gameDay_id,
                        gp_idPlayer=player_id,
                        gp_team=team_name
                    )
                    db.session.add(game_day_player)
                    db.session.commit()
                except Exception as e:
                    print("Error:", e)

            # go through all the teams in GameDayPlayer
            gd_players = GameDayPlayer.query.filter_by(gp_idGameDay=gameDay_id).order_by(GameDayPlayer.gp_team.asc(), GameDayPlayer.gp_id.asc()).all()
    
            # Organize players by team
            teams = {}
            for gd_player in gd_players:
                if gd_player.gp_team not in teams:
                    teams[gd_player.gp_team] = []
                teams[gd_player.gp_team].append(gd_player)

            
            for team, players in teams.items():
                player1ID=0
                player1Name=''
                player2ID=0
                player2Name=''
                for player in players:
                    if player1ID==0:
                        player1ID = player.gp_idPlayer
                        player1Name = player.player.us_name
                    else:
                        player2ID = player.gp_idPlayer
                        player2Name = player.player.us_name

                db.session.execute(
                text(f"update tb_game set gm_idPlayer_A1=:player1ID, gm_idPlayer_A2=:player2ID where gm_idGameDay=:gameDay_id and gm_teamA=:team"),
                    {"player1ID": player1ID, "player2ID": player2ID, "gameDay_id": gameDay_id, "team": team}
                )
                db.session.commit()
                db.session.execute(
                text(f"update tb_game set gm_idPlayer_B1=:player1ID, gm_idPlayer_B2=:player2ID where gm_idGameDay=:gameDay_id and gm_teamB=:team"),
                    {"player1ID": player1ID, "player2ID": player2ID, "gameDay_id": gameDay_id, "team": team}
                )
                db.session.commit()
    
    flash(translate('Players registered successfully!'), 'success')
    return redirect(url_for('views.edit_gameday', gameday_id=gameDayID))

def func_submitResultsGameDay(gameDayID):
    gameDay_data = GameDay.query.filter_by(gd_id=gameDayID).first()
    league_id = gameDay_data.gd_idLeague
    league = League.query.get(league_id)
    
    if league.lg_status != "being played":
        flash(translate('Cannot submit results - league is not in progress'), 'error')
        return redirect(url_for('views.edit_gameday', gameday_id=gameDayID))
    
    #Get all ids of that gameday
    result = Game.query.filter_by(gm_idGameDay=gameDayID).all()
    if result:
        for data in result:
            resultA = f"resultGameA{data.gm_id}"
            resultB = f"resultGameB{data.gm_id}"
            gameID = data.gm_id
            getResultA = request.form.get(resultA)
            getResultB = request.form.get(resultB)
            db.session.execute(
            text(f"update tb_game set gm_result_A=:getResultA, gm_result_B=:getResultB where gm_id=:gameID and gm_idLeague=:league_id"),
                {"getResultA": getResultA, "getResultB": getResultB, "gameID": gameID, "league_id": league_id}
            )
            db.session.commit()

        db.session.execute(
        text(f"update tb_gameday SET gd_status='finished' where gd_id=:gameDayID and gd_idLeague=:league_id"),
            {"gameDayID": gameDayID, "league_id": league_id}
        )
        db.session.commit()

        #If all gamedays of that league are Terminado change status of League to finished
        pending_game_days_count = GameDay.query.filter(
            GameDay.gd_idLeague == league_id,
            GameDay.gd_status != 'finished'
        ).count()

        if pending_game_days_count == 0:
            # Update the league status to 'finished'
            league.lg_status = 'finished'
            db.session.commit()

        func_calculateGameDayClassification(gameDayID)
        func_calculateLeagueClassification(league_id)
        func_calculate_ELO_parcial()
    
    flash(translate('Results submitted successfully!'), 'success')
    return redirect(url_for('views.edit_gameday', gameday_id=gameDayID))
