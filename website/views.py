from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Flask, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import (Users, UserRequests, Messages, League, Club, ClubAuthorization, 
                    Court, GameDay, LeagueCourts, Game, GameDayPlayer, GameDayClassification, 
                    LeagueClassification, ELOranking, ELOrankingHist, LeaguePlayers, GameDayRegistration,
                    Event, EventRegistration, EventClassification, EventCourts, EventPlayerNames,
                    EventType, MexicanConfig)
from . import db
import json, os, threading
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import and_, func, cast, String, text, desc, case, literal_column, or_
from PIL import Image
from io import BytesIO
from .user_info_func import ext_home, ext_userInfo
from .tools import *
from .gameday import *
import shutil

def translate(text):
    # Import translations file
    translations_path = os.path.join(os.path.dirname(__file__), '..', 'translations', 'translations.json')
    with open(translations_path, 'r', encoding='utf-8') as f:
        translations = json.load(f)
    
    # Get current language from cookie or default to English
    lang = request.cookies.get('lang', 'en')
    
    # Try to get translation, return original text if not found
    if text in translations and lang in translations[text]:
        return translations[text][lang]
    return text

views =  Blueprint('views', __name__)

# Template context processors
@views.context_processor
def utility_processor():
    return {
        'now': datetime.now,
        'translate': translate,
    }

# Home route
@views.route('/', methods=['GET', 'POST'])
def home():
    return ext_home()

@views.route('/event/<int:event_id>', methods=['GET'])
def public_event_detail(event_id):
    """Public event detail page"""
    event = Event.query.get_or_404(event_id)
    
    # Check if user is registered for this event
    is_registered = False
    if current_user.is_authenticated:
        is_registered = EventRegistration.query.filter_by(
            er_event_id=event_id,
            er_player_id=current_user.us_id
        ).first() is not None
    
    # Get club info if event has a club
    club = None
    if event.ev_club_id:
        club = Club.query.get(event.ev_club_id)
    
    return render_template('event_detail_public.html', 
                         event=event,
                         club=club,
                         user=current_user,
                         is_registered=is_registered)


# Events public page
@views.route('/Events', methods=['GET'])
def events():
    """Public page to display all events"""
    # Get all active events ordered by date (exclude canceled events)
    # Include events with and without clubs
    events_data = Event.query\
        .outerjoin(Club, Event.ev_club_id == Club.cl_id)\
        .filter(Event.ev_status != 'canceled')\
        .filter(db.or_(Event.ev_club_id.is_(None), Club.cl_active == True))\
        .order_by(Event.ev_date.desc())\
        .all()
    
    return render_template("events.html", user=current_user, events_data=events_data)

# User own info routes
@views.route('/userOwnInfo', methods=['GET', 'POST'])
@login_required
def userOwnInfo():
    return render_template("user_own_info.html", user=current_user)

@views.route('/userInfo/<int:user_id>', methods=['GET', 'POST'])
@login_required
def userInfo(p_user_id):
    return ext_userInfo(p_user_id)

@views.route('/register_gameday/<int:gameday_id>')
@login_required
def register_gameday(gameday_id):
    gameday = GameDay.query.get_or_404(gameday_id)
    
    # Check if user is registered in the league
    league_registration = LeaguePlayers.query.filter_by(
        lp_league_id=gameday.gd_idLeague,
        lp_player_id=current_user.us_id
    ).first()
    
    if not league_registration:
        flash('You must be registered in the league to register for gamedays.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

    now = datetime.now(timezone.utc)

    # Use timezone-aware properties from GameDay model
    if now < gameday.registration_start_utc:
        flash('Registration period has not started yet.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))
    
    if now > gameday.registration_end_utc:
        flash('Registration period has ended.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

    # Check if already registered
    existing_registration = GameDayRegistration.query.filter_by(
        gdr_gameday_id=gameday_id,
        gdr_player_id=current_user.us_id
    ).first()
    
    if existing_registration:
        flash('You are already registered for this gameday.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

    # Check if maximum players reached
    if gameday.current_player_count >= gameday.max_players:
        flash('Maximum number of players reached.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

    # Create registration
    registration = GameDayRegistration(
        gdr_gameday_id=gameday_id,
        gdr_player_id=current_user.us_id,
        gdr_registered_by_id=current_user.us_id
    )
    
    try:
        db.session.add(registration)
        db.session.commit()
        flash('Successfully registered for gameday.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while registering.', 'error')
    
    return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

@views.route('/unregister_gameday/<int:gameday_id>', methods=['POST'])
@login_required
def unregister_gameday(gameday_id):
    gameday = GameDay.query.get_or_404(gameday_id)
    now = datetime.now(timezone.utc)
    
    # Check if registration period ended
    if now > gameday.gd_registration_end:
        flash('Registration period has ended. Cannot unregister.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

    registration = GameDayRegistration.query.filter_by(
        gdr_gameday_id=gameday_id,
        gdr_player_id=current_user.us_id
    ).first()
    
    if not registration:
        flash('You are not registered for this gameday.', 'error')
        return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

    try:
        db.session.delete(registration)
        db.session.commit()
        flash('Successfully unregistered from gameday.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while unregistering.', 'error')
    
    return redirect(url_for('views.gameday_detail', gameday_id=gameday_id))

@views.route('/league/<int:league_id>/add_player', methods=['GET', 'POST'])
@login_required
def add_league_player(league_id):
    league = League.query.get_or_404(league_id)
    return_url = request.args.get('return_url') or url_for('views.edit_league', league_id=league_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to add players to this league!'), 'error')
        return redirect(return_url)

    if league.current_player_count >= league.lg_max_players:
        flash(translate('League is already full!'), 'error')
        return redirect(return_url)

    if request.method == 'POST':
        fullname = request.form.get('fullname')
        telephone = request.form.get('telephone')
        email = request.form.get('email')
        photo = request.files.get('photo')

        # Check if user already exists by telephone
        user = Users.query.filter_by(us_telephone=telephone).first()
        
        if not user:
            # Create new user
            user = Users(
                us_name=fullname,
                us_email=email,
                us_telephone=telephone,
                us_is_active=True,
                us_is_player=True,
                us_pwd='welcome2padel'  # Default password
            )
            db.session.add(user)
            db.session.commit()

            # Handle photo upload if provided
            if photo:
                path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'photos', 'users', str(user.us_id))
                if not os.path.exists(path):
                    os.makedirs(path)
                photo.save(os.path.join(path, 'main.jpg'))

        # Check if user is already registered in this league
        existing_registration = LeaguePlayers.query.filter_by(
            lp_league_id=league_id,
            lp_player_id=user.us_id
        ).first()

        if existing_registration:
            flash(translate('Player is already registered in this league!'), 'error')
        else:
            # Register player to league
            new_registration = LeaguePlayers(
                lp_league_id=league_id,
                lp_player_id=user.us_id,
                lp_registered_by_id=current_user.us_id
            )
            db.session.add(new_registration)
            db.session.commit()
            flash(translate('Player successfully added to league!'), 'success')

        return redirect(return_url)

    title_add_user_event = f"{translate('Add Player')} - {league.lg_name}"
    return render_template('add_user_event.html', 
                         user=current_user, 
                         league=league, 
                         return_url=return_url,
                         title_add_user_event=title_add_user_event)

# User management routes
@views.route('/managementUsersSU', methods=['GET', 'POST'])
@login_required
def managementUsersSU():
    result_data = Users.query.order_by(Users.us_id.desc()).all()
    return render_template("managementUsersSU.html", user=current_user, result=result_data)

@views.route('/managementUsersAdmin', methods=['GET', 'POST'])
@login_required
def managementUsersAdmin():
    result_data = Users.query.filter(Users.us_is_admin == 0, Users.us_is_superuser == 0).order_by(Users.us_id.desc()).all()
    return render_template("managementUsersAdmin.html", user=current_user, result=result_data)

@views.route('/updateOwnUser', methods=['GET', 'POST'])
@login_required
def updateOwnUser():
    user_id = current_user.us_id
    user_Name = request.form.get('user_name')
    user_Email = request.form.get('user_email')
    user_birthday = request.form.get('user_birthday')
    
    if request.form.get('user_active') == 'on':
        user_is_active = 1
    else:
        user_is_active = 0

    if request.form.get('user_player') == 'on':
        user_is_player = 1
    else:
        user_is_player = 0

    if request.form.get('user_manager') == 'on':
        user_is_manager = 1
    else:
        user_is_manager = 0

    if request.form.get('user_admin') == 'on':
        user_is_admin = 1
    else:
        user_is_admin = 0

    if request.form.get('user_superuser') == 'on':
        user_is_superuser = 1
    else:
        user_is_superuser = 0
    # user_Photo = request.form.get('user_photo')
    
    # Update User
    try:
        db.session.execute(
        text(f"UPDATE tb_users SET us_name=:user_Name, us_email=:user_Email, us_birthday=:user_birthday, us_is_active=:user_is_active, us_is_player=:user_is_player, us_is_manager=:user_is_manager, us_is_admin=:user_is_admin, us_is_superuser=:user_is_superuser WHERE us_id=:user_id"),
            {"user_Name": user_Name, "user_Email": user_Email, "user_id": user_id, "user_birthday": user_birthday, "user_is_active": user_is_active, "user_is_player": user_is_player, "user_is_manager": user_is_manager, "user_is_admin": user_is_admin, "user_is_superuser": user_is_superuser}
        )
        db.session.commit()
    except Exception as e:
        print("Error: " + str(e))

    # Insert photo of user
    image = request.files.get('user_photo')
    if image and image.filename and user_id > 0:
        photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'users', str(user_id))
        file_path = os.path.join(photos_dir, 'main.jpg')
                
        # Create directory if it doesn't exist
        if not os.path.exists(photos_dir):
            os.makedirs(photos_dir)
            
        # Remove existing photo if it exists
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Upload image to directory
        image.save(file_path)

    return render_template("user_own_info.html", user=current_user)

@views.route('/updateUser/<int:userID>', methods=['GET', 'POST'])
@login_required
def updateUser(userID):
    user_id = userID
    pass_user = Users.query.get_or_404(userID)
    user_Name = request.form.get('user_name')
    user_Email = request.form.get('user_email')
    user_birthday = request.form.get('user_birthday')
    
    # Check if email exists for another user
    if user_Email and user_Email.strip():
        existing_email = Users.query.filter(
            Users.us_email == user_Email,
            Users.us_id != userID
        ).first()
        if existing_email:
            flash(translate('Email already exists for another user'), 'error')
            return render_template("user_info.html", user=current_user, p_user=pass_user)

    if request.form.get('user_active') == 'on':
        user_is_active = 1
    else:
        user_is_active = 0

    if request.form.get('user_player') == 'on':
        user_is_player = 1
    else:
        user_is_player = 0

    if request.form.get('user_manager') == 'on':
        user_is_manager = 1
    else:
        user_is_manager = 0

    if request.form.get('user_admin') == 'on':
        user_is_admin = 1
    else:
        user_is_admin = 0

    if request.form.get('user_superuser') == 'on':
        user_is_superuser = 1
    else:
        user_is_superuser = 0
    # Update User
    try:
        db.session.execute(
        text(f"UPDATE tb_users SET us_name=:user_Name, us_email=:user_Email, us_birthday=:user_birthday, us_is_active=:user_is_active, us_is_player=:user_is_player, us_is_manager=:user_is_manager, us_is_admin=:user_is_admin, us_is_superuser=:user_is_superuser WHERE us_id=:user_id"),
            {"user_Name": user_Name, "user_Email": user_Email, "user_id": user_id, "user_birthday": user_birthday, "user_is_active": user_is_active, "user_is_player": user_is_player, "user_is_manager": user_is_manager, "user_is_admin": user_is_admin, "user_is_superuser": user_is_superuser}
        )
        db.session.commit()
    except Exception as e:
        print("Error: " + str(e))

    # Insert photo of user
    image = request.files.get('user_photo')  # Using get() instead of direct access
    if image and image.filename and user_id > 0:
        path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/users/'+str(user_id)+'/'
        pathRelative = 'static\\photos\\users\\'+str(user_id)+'\\'
        filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/users/'+str(user_id)+'/main.jpg'
                
        # Check if directory exists, if not, create it.
        if not os.path.exists(path):
            os.makedirs(path)  # Using makedirs instead of mkdir
            
        # Check if main.jpg exists, if exists delete it
        if os.path.exists(filePath):
            os.remove(filePath)
        
        # Upload image to directory
        image.save(filePath)

    # return render_template("user_info.html", user=current_user, p_user=pass_user)
    return redirect(url_for('views.managementUsersSU'))

@views.route('/saveUserChanges', methods=['POST'])
@login_required
def saveUserChanges():
    for user in Users.query.all():
        user.us_is_player = 'us_is_player_' + str(user.us_id) in request.form
        user.us_is_manager = 'us_is_manager_' + str(user.us_id) in request.form
        user.us_is_admin = 'us_is_admin_' + str(user.us_id) in request.form
        user.us_is_active = 'us_is_active_' + str(user.us_id) in request.form
        user.us_is_superuser = 'us_is_superuser_' + str(user.us_id) in request.form
    db.session.commit()
    return redirect(url_for('views.managementUsersSU'))

@views.route('/editUser/<int:user_id>', methods=['GET', 'POST'])
@login_required
def editUser(user_id):
    p_user = Users.query.get_or_404(user_id)
    
    # Check if user has participated in any games
    has_games = db.session.query(Game).filter(
        db.or_(
            Game.gm_idPlayer_A1 == user_id,
            Game.gm_idPlayer_A2 == user_id,
            Game.gm_idPlayer_B1 == user_id,
            Game.gm_idPlayer_B2 == user_id
        )
    ).first() is not None
    
    return render_template('user_info.html', user=current_user, p_user=p_user, has_games=has_games)

@views.route('/deleteUser/<int:userID>', methods=['POST'])
@login_required
def deleteUser(userID):
    if not current_user.us_is_superuser:
        flash(translate('You do not have permission to delete users.'), 'error')
        return redirect(url_for('views.home'))
    
    user_to_delete = Users.query.get_or_404(userID)
    
    # Check if user has participated in any games
    has_games = db.session.query(Game).filter(
        db.or_(
            Game.gm_idPlayer_A1 == userID,
            Game.gm_idPlayer_A2 == userID,
            Game.gm_idPlayer_B1 == userID,
            Game.gm_idPlayer_B2 == userID
        )
    ).first() is not None
    
    if has_games:
        flash(translate('Cannot delete user who has participated in games.'), 'error')
        return redirect(url_for('views.editUser', user_id=userID))
    
    # Delete user's photo folder
    import os
    import shutil
    user_photo_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'photos', 'users', str(userID))
    if os.path.exists(user_photo_dir):
        shutil.rmtree(user_photo_dir)
    
    try:
        # Delete user's league registrations
        LeaguePlayers.query.filter_by(lp_player_id=userID).delete()
        
        # Delete user's gameday registrations
        GameDayRegistration.query.filter_by(gdr_player_id=userID).delete()
        
        # Delete user's league classifications
        LeagueClassification.query.filter_by(lc_idPlayer=userID).delete()
        
        # Delete user's gameday classifications
        GameDayClassification.query.filter_by(gc_idPlayer=userID).delete()
        
        # Delete user's ELO ranking data
        ELOranking.query.filter_by(pl_id=userID).delete()
        
        # Delete user's club authorizations
        ClubAuthorization.query.filter_by(ca_user_id=userID).delete()
        
        # Delete user's messages (sent and received)
        Messages.query.filter(
            db.or_(
                Messages.msg_sender_id == userID,
                Messages.msg_receiver_id == userID
            )
        ).delete()
        
        # Delete user's requests
        UserRequests.query.filter(
            db.or_(
                UserRequests.ur_user_id == userID,
                UserRequests.ur_response_user_id == userID
            )
        ).delete()
        
        # Finally delete the user
        db.session.delete(user_to_delete)
        db.session.commit()
        
        flash(translate('User deleted successfully.'), 'success')
        return redirect(url_for('views.managementUsersSU'))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('An error occurred while deleting the user.'), 'error')
        return redirect(url_for('views.editUser', user_id=userID))

@views.route('/register_league/<int:league_id>')
def register_league(league_id):
    if not current_user.is_authenticated:
        # Store the next URL in session
        session['next'] = url_for('views.register_league', league_id=league_id)
        flash(translate('Please login to register for the league'), 'info')
        return redirect(url_for('auth.login'))

    league = League.query.get_or_404(league_id)

    # Check if league is accepting registrations
    if league.lg_status != "accepting registrations":
        if league.lg_status == "announced":
            flash(translate('Registration has not started yet'), 'error')
        elif league.lg_status == "registration complete":
            flash(translate('Registration period has ended - maximum players reached'), 'error')
        elif league.lg_status == "canceled":
            flash(translate('League has been canceled'), 'error')
        elif league.lg_status == "being played":
            flash(translate('League is already in progress'), 'error')
        elif league.lg_status == "finished":
            flash(translate('League has ended'), 'error')
        else:
            flash(translate('League is not accepting registrations'), 'error')
        return redirect(url_for('views.detail_league', league_id=league_id))

    now = datetime.now(timezone.utc)

    # Ensure registration dates are timezone-aware
    registration_start = league.lg_registration_start.replace(tzinfo=timezone.utc) if league.lg_registration_start else None
    registration_end = league.lg_registration_end.replace(tzinfo=timezone.utc) if league.lg_registration_end else None

    # Check if registration is open
    if registration_start is None or registration_end is None:
        flash(translate('Registration dates not set'), 'error')
        return redirect(url_for('views.detail_league', league_id=league_id))

    if now < registration_start:
        flash(translate('Registration has not started yet'), 'error')
        return redirect(url_for('views.detail_league', league_id=league_id))
    
    if now > registration_end:
        flash(translate('Registration period has ended'), 'error')
        return redirect(url_for('views.detail_league', league_id=league_id))

    # Check if user is already registered
    existing_registration = LeaguePlayers.query.filter_by(
        lp_league_id=league_id, 
        lp_player_id=current_user.us_id
    ).first()
    
    if existing_registration:
        flash(translate('You are already registered for this league'), 'info')
        return redirect(url_for('views.detail_league', league_id=league_id))

    # Add the player to the league
    new_registration = LeaguePlayers(
        lp_league_id=league_id,
        lp_player_id=current_user.us_id,
        lp_registered_by_id=current_user.us_id
    )
    db.session.add(new_registration)
    db.session.commit()

    # Check if we exceeded max players and need cleanup
    registered_players = LeaguePlayers.query.filter_by(lp_league_id=league_id).order_by(LeaguePlayers.lp_registered_at).all()
    
    if len(registered_players) > league.lg_max_players:
        # Remove excess players starting from the most recent
        players_to_remove = registered_players[league.lg_max_players:]
        for player_reg in players_to_remove:
            db.session.delete(player_reg)
        db.session.commit()

        # Check if current user was removed
        current_player = LeaguePlayers.query.filter_by(
            lp_league_id=league_id, 
            lp_player_id=current_user.us_id
        ).first()
        
        if not current_player:
            flash(translate('The league is already full'), 'error')
        else:
            flash(translate('You have been successfully registered for the league'), 'success')
    else:
        flash(translate('You have been successfully registered for the league'), 'success')

    return redirect(url_for('views.detail_league', league_id=league_id))

@views.route('/unregister_league/<int:league_id>', methods=['POST'])
@login_required
def unregister_league(league_id):
    league = League.query.get_or_404(league_id)
    
    # Check if user is registered
    registration = LeaguePlayers.query.filter_by(
        lp_league_id=league_id,
        lp_player_id=current_user.us_id
    ).first()
    
    if not registration:
        flash(translate('You are not registered for this league'), 'error')
        return redirect(url_for('views.detail_league', league_id=league_id))
    
    # Delete the registration
    db.session.delete(registration)
    db.session.commit()
    
    flash(translate('You have been unregistered from the league'), 'success')
    return redirect(url_for('views.detail_league', league_id=league_id))

# Request management routes
@views.route('/request_manager', methods=['POST'])
@login_required
def request_manager():
    if not current_user.us_is_manager:
        new_request = UserRequests(
            ur_user_id=current_user.us_id,
            ur_request_type='manager'
        )
        db.session.add(new_request)
        db.session.commit()
        flash('Your request to become a manager has been submitted.', 'success')
    else:
        flash('You are already a manager.', 'info')
    return redirect(url_for('views.userOwnInfo'))

@views.route('/manage_requests', methods=['GET', 'POST'])
@login_required
def manage_requests():
    if not current_user.us_is_superuser:
        flash('Access denied.', 'error')
        return redirect(url_for('views.home'))
    requests = UserRequests.query.filter_by(ur_responded=False).all()
    return render_template('manage_requests.html', user=current_user, requests=requests)

@views.route('/respond_request/<int:request_id>', methods=['POST'])
@login_required
def respond_request(request_id):
    if not current_user.us_is_superuser:
        flash('Access denied.', 'error')
        return redirect(url_for('views.home'))
    user_request = UserRequests.query.get_or_404(request_id)
    response = request.form.get('response')
    reason = request.form.get('reason')
    user_request.ur_responded = True
    user_request.ur_accepted = (response == 'accept')
    user_request.ur_response_time = func.now()
    user_request.ur_response_user_id = current_user.us_id
    user_request.ur_response_reason = reason
    if response == 'accept' and user_request.ur_request_type == 'manager':
        user = Users.query.get(user_request.ur_user_id)
        user.us_is_manager = 1
    db.session.commit()
    flash('Request has been responded to.', 'success')
    return redirect(url_for('views.manage_requests'))

@views.context_processor
def inject_unresponded_requests_count():
    if current_user.is_authenticated and current_user.us_is_superuser:
        unresponded_requests_count = UserRequests.query.filter_by(ur_responded=False).count()
    else:
        unresponded_requests_count = 0
    return dict(unresponded_requests_count=unresponded_requests_count)

# Club management routes
@views.route('/managementClubs')
@login_required
def management_clubs():
    if not (current_user.us_is_manager or current_user.us_is_admin or current_user.us_is_superuser):
        flash(translate('You do not have permission to access this page.'), 'error')
        return redirect(url_for('views.home'))
    
    authorized_clubs = Club.query.join(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id
    ).all()
    
    return render_template('managementClubs.html', user=current_user, authorized_clubs=authorized_clubs)

@views.route('/create_club', methods=['GET', 'POST'])
@login_required
def create_club():
    if not (current_user.us_is_manager or current_user.us_is_admin or current_user.us_is_superuser):
        flash(translate('You do not have permission to access this page.'), 'error')
        return redirect(url_for('views.home'))
    
    if request.method == 'POST':
        name = request.form.get('club_name')
        email = request.form.get('club_email')
        phone = request.form.get('club_phone')
        address = request.form.get('club_address')
        
        # Create new club
        new_club = Club(
            cl_name=name,
            cl_email=email,
            cl_phone=phone,
            cl_address=address,
            cl_active=True
        )
        db.session.add(new_club)
        db.session.commit()
        cl_id = new_club.cl_id
        
        # Create authorization for the current user
        club_auth = ClubAuthorization(
            ca_user_id=current_user.us_id,
            ca_club_id=new_club.cl_id
        )
        db.session.add(club_auth)
        db.session.commit()

        # register main photo
        image = request.files.get('club_main_photo')
        if image and image.filename and cl_id > 0:
            photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'clubs', str(cl_id))
            file_path = os.path.join(photos_dir, 'main.jpg')
            
            if not os.path.exists(photos_dir):
                os.makedirs(photos_dir)
            
            if os.path.exists(file_path):
                os.remove(file_path)
            
            image.save(file_path)

        # register secondary photos
        secondary_photos = request.files.getlist('club_secondary_photos')
        if secondary_photos and any(photo.filename for photo in secondary_photos):
            photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'clubs', str(cl_id))
            secondary_dir = os.path.join(photos_dir, 'secondary')
            
            if not os.path.exists(secondary_dir):
                os.makedirs(secondary_dir)
            
            for idx, photo in enumerate(secondary_photos, start=1):
                if photo.filename:
                    photo_path = os.path.join(secondary_dir, f'{idx}.jpg')
                    photo.save(photo_path)

        flash(translate('Club created successfully!'), 'success')
        return redirect(url_for('views.management_clubs'))
    
    return render_template('create_club.html', user=current_user)

@views.route('/edit_club/<int:club_id>', methods=['GET', 'POST'])
@login_required
def edit_club(club_id):
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not club:
        flash(translate('Club not found or you do not have permission to edit it.'), 'error')
        return redirect(url_for('views.home'))
    
    if request.method == 'POST':
        club.cl_name = request.form.get('club_name')
        club.cl_email = request.form.get('club_email')
        club.cl_phone = request.form.get('club_phone')
        club.cl_address = request.form.get('club_address')
        
        db.session.commit()

        cl_id = club.cl_id
        # Define paths outside of conditional blocks
        path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/clubs/'+str(cl_id)+'/'
        pathRelative = 'static\\photos\\clubs\\'+str(cl_id)+'\\'
        
        # register main photo
        image = request.files.get('club_main_photo')  # Using get() instead of direct access
        if image and image.filename and cl_id > 0:
            filePath = os.path.join(path, 'main.jpg')
                    
            # Check if directory exists, if not, create it.
            if not os.path.exists(path):
                os.makedirs(path)  # Using makedirs instead of mkdir to create parent directories if needed
            
            # Check if main.jpg exists, if exists delete it
            if os.path.exists(filePath):
                os.remove(filePath)
            
            # Upload image to directory
            image.save(filePath)

        # register secondary photos
        secondary_photos = request.files.getlist('club_secondary_photos')
        if secondary_photos and any(photo.filename for photo in secondary_photos):
            secondary_path = os.path.join(path, 'secondary')
            if not os.path.exists(secondary_path):
                os.makedirs(secondary_path)
            
            # Remove existing secondary photos
            for existing_file in os.listdir(secondary_path) if os.path.exists(secondary_path) else []:
                os.remove(os.path.join(secondary_path, existing_file))
            
            # Save new photos
            for idx, photo in enumerate(secondary_photos, start=1):
                if photo.filename:
                    photo_path = os.path.join(secondary_path, f'{idx}.jpg')
                    photo.save(photo_path)

        flash(translate('Club updated successfully.'), 'success')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    return render_template('edit_club.html', club=club, user=current_user)

@views.route('/club/<int:club_id>/activate', methods=['POST'])
@login_required
def activate_club(club_id):
    if not (current_user.us_is_manager or current_user.us_is_admin or current_user.us_is_superuser):
        flash(translate('Unauthorized'), 'error')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not club:
        flash(translate('Club not found'), 'error')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    club.cl_active = True
    db.session.commit()
    flash(translate('Club activated successfully'), 'success')
    return redirect(url_for('views.edit_club', club_id=club_id))

@views.route('/club/<int:club_id>/deactivate', methods=['POST'])
@login_required
def deactivate_club(club_id):
    if not (current_user.us_is_manager or current_user.us_is_admin or current_user.us_is_superuser):
        flash(translate('Unauthorized'), 'error')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not club:
        flash(translate('Club not found'), 'error')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    club.cl_active = False
    db.session.commit()
    flash(translate('Club deactivated successfully'), 'success')
    return redirect(url_for('views.edit_club', club_id=club_id))

@views.route('/club/<int:club_id>/courts/add', methods=['POST'])
@login_required
def add_court(club_id):
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not club:
        return jsonify({'error': translate('Unauthorized')}), 403
    
    court_name = request.form.get('court_name')
    court_sport = request.form.get('court_sport')
    
    if not court_name or not court_sport:
        return jsonify({'error': translate('Missing required fields')}), 400
    
    new_court = Court(
        ct_name=court_name,
        ct_sport=court_sport,
        ct_club_id=club_id
    )
    db.session.add(new_court)
    db.session.commit()
    
    flash(translate('Court added successfully'), 'success')
    return redirect(url_for('views.edit_club', club_id=club_id))

@views.route('/court/<int:court_id>/delete', methods=['POST'])
@login_required
def delete_court(court_id):
    court = Court.query.join(Club).join(ClubAuthorization).filter(
        Court.ct_id == court_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not court:
        return jsonify({'error': translate('Unauthorized')}), 403
    
    club_id = court.ct_club_id  # Save club_id before deleting the court
    db.session.delete(court)
    db.session.commit()
    
    flash(translate('Court deleted successfully'), 'success')
    return redirect(url_for('views.edit_club', club_id=club_id))

@views.route('/club/<int:club_id>/users/add', methods=['POST'])
@login_required
def add_club_user(club_id):
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not club:
        return jsonify({'error': translate('Unauthorized')}), 403
    
    user_input = request.form.get('user_email')
    if not user_input:
        return jsonify({'error': translate('Email is required')}), 400
    
    # Extract email from the "name - email" format
    email = user_input.split(' - ')[-1].strip() if ' - ' in user_input else user_input
    
    user = Users.query.filter_by(us_email=email).first()
    if not user:
        flash(translate('User not found'), 'error')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    existing_auth = ClubAuthorization.query.filter_by(
        ca_user_id=user.us_id,
        ca_club_id=club_id
    ).first()
    
    if existing_auth:
        flash(translate('User already has access to this club'), 'error')
        return redirect(url_for('views.edit_club', club_id=club_id))
    
    auth = ClubAuthorization(
        ca_user_id=user.us_id,
        ca_club_id=club_id
    )
    db.session.add(auth)
    db.session.commit()
    
    flash(translate('User added successfully'), 'success')
    return redirect(url_for('views.edit_club', club_id=club_id))

@views.route('/club_authorization/<int:auth_id>/delete', methods=['POST'])
@login_required
def delete_club_authorization(auth_id):
    # Get the authorization to be deleted
    auth_to_delete = ClubAuthorization.query.get_or_404(auth_id)
    user_to_delete = Users.query.get(auth_to_delete.ca_user_id)
    
    # Check authorization rules based on user roles
    if not (
        current_user.us_is_superuser or 
        (current_user.us_is_admin and not user_to_delete.us_is_admin and not user_to_delete.us_is_superuser) or
        (current_user.us_is_manager and not user_to_delete.us_is_admin and not user_to_delete.us_is_superuser and not user_to_delete.us_is_manager)
    ):
        flash(translate('You do not have permission to remove this user'), 'error')
        return redirect(url_for('views.edit_club', club_id=auth_to_delete.ca_club_id))
    
    # Check if current user has authorization for the same club
    user_has_auth = ClubAuthorization.query.filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == auth_to_delete.ca_club_id
    ).first() is not None
    
    # Only allow if user has authorization for this club
    if not user_has_auth:
        flash(translate('Unauthorized'), 'error')
        return redirect(url_for('views.home'))
    
    club_id = auth_to_delete.ca_club_id  # Save the club_id before deleting the authorization
    
    db.session.delete(auth_to_delete)
    db.session.commit()
    
    flash(translate('User authorization removed successfully'), 'success')
    return redirect(url_for('views.edit_club', club_id=club_id))


@views.route('/edit_league/<int:league_id>', methods=['GET', 'POST'])
@login_required
def edit_league(league_id):
    league = League.query.get_or_404(league_id)
    
    # Check if user is authorized for this club through ClubAuthorization
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You do not have permission to edit this league.'), category='error')
        return redirect(url_for('views.index'))

    club = Club.query.get_or_404(league.lg_club_id)
    courts = Court.query.filter_by(ct_club_id=club.cl_id).all()
    gamedays = GameDay.query.filter_by(gd_idLeague=league_id).order_by(GameDay.gd_date).all()

    # Get registered users with their registration info
    registered_users = (
        db.session.query(Users, LeaguePlayers)
        .join(LeaguePlayers, Users.us_id == LeaguePlayers.lp_player_id)
        .filter(LeaguePlayers.lp_league_id == league_id)
        .order_by(LeaguePlayers.lp_registered_at)
        .all()
    )

    # Format the data for the template
    users_data = []
    for user, league_player in registered_users:
        users_data.append({
            'us_name': user.us_name,
            'us_id': user.us_id,
            'registration_date': league_player.lp_registered_at,
            'registered_by_id': league_player.lp_registered_by_id,
            'is_substitute': False  # LeaguePlayers doesn't have substitute info yet
        })
    
    if request.method == 'POST':
        # Update league details
        league.lg_name = request.form.get('title')
        league.lg_level = request.form.get('level')
        league.lg_status = request.form.get('status')
        league.lg_nbrDays = request.form.get('nbr_days')
        league.lg_nbrTeams = request.form.get('nbr_teams')
        league.lg_startDate = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        league.lg_startTime = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
        league.lg_minWarmUp = request.form.get('min_warm_up')
        league.lg_minPerGame = request.form.get('min_per_game')
        league.lg_minBetweenGames = request.form.get('min_between_games')
        league.lg_typeOfLeague = request.form.get('type_of_league')
        league.tb_maxLevel = request.form.get('max_level')
        league.lg_eloK = request.form.get('elo_k')
        
        db.session.commit()

        # Handle main photo upload
        image = request.files.get('league_photo')
        if image and image.filename:
            path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(league_id)+'/'
            if not os.path.exists(path):
                os.makedirs(path)
                
            filePath = path + 'main.jpg'
            if os.path.exists(filePath):
                os.remove(filePath)
            
            image.save(filePath)

        # Handle secondary photos
        secondary_photos = request.files.getlist('league_secondary_photos')
        if secondary_photos and any(photo.filename for photo in secondary_photos):
            path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(league_id)+'/'
            secondary_path = os.path.join(path, 'secondary')
            if not os.path.exists(secondary_path):
                os.makedirs(secondary_path)
                
            # Remove existing secondary photos
            for existing_file in os.listdir(secondary_path) if os.path.exists(secondary_path) else []:
                os.remove(os.path.join(secondary_path, existing_file))
            
            # Save new photos
            for idx, photo in enumerate(secondary_photos, start=1):
                if photo.filename:
                    photo_path = os.path.join(secondary_path, f'{idx}.jpg')
                    photo.save(photo_path)

        flash(translate('League updated successfully!'), 'success')
        return redirect(url_for('views.edit_league', league_id=league_id) + '#court-details')

    # Check if league can be deleted
    can_delete, delete_message = can_delete_league(league_id)
    
    return render_template('edit_league.html', 
                           user=current_user, 
                           league=league,
                           club=club,
                           courts=courts,
                           gamedays=gamedays,
                           registered_users=users_data,
                           can_delete_league=can_delete,
                           delete_message=delete_message,
                           now=datetime.utcnow())

# League management routes
@views.route('/managementLeagues', methods=['GET', 'POST'])
@login_required
def managementLeagues():
    # Query leagues joined with club authorizations for the current user
    leagues_data = League.query\
        .join(Club, League.lg_club_id == Club.cl_id)\
        .join(ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id)\
        .filter(ClubAuthorization.ca_user_id == current_user.us_id)\
        .order_by(League.lg_status, League.lg_endDate.desc())\
        .all()
    return render_template("managementLeagues.html", user=current_user, result=leagues_data)

@views.route('/create_league', methods=['GET', 'POST'])
@login_required
def create_league():
    # Get authorized clubs
    authorized_clubs = Club.query.join(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id
    ).all()

    if request.method == 'POST':
        # Get form data
        club_id = request.form.get('club_id')
        name = request.form.get('title')
        
        # Check if user is authorized for this club
        is_authorized = any(club.cl_id == int(club_id) for club in authorized_clubs)
        if not is_authorized:
            flash(translate('You are not authorized to create leagues for this club!'), 'error')
            return redirect(url_for('views.managementLeagues'))

        # Check for courts
        selected_club = next((club for club in authorized_clubs if club.cl_id == int(club_id)), None)
        if not selected_club or not selected_club.courts:
            flash(translate('The selected club does not have any courts!'), 'error')
            return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

        # Get number of teams and check if club has enough courts
        nbr_teams = int(request.form.get('nbr_teams', 0))
        required_courts = (nbr_teams + 1) // 2  # Equivalent to Math.ceil(nbr_teams / 2)
        
        if len(selected_club.courts) < required_courts:
            flash(translate(f'The selected club does not have enough courts. You need {required_courts} courts for {nbr_teams} teams, but this club only has {len(selected_club.courts)} courts.'), 'error')
            return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

        level = request.form.get('level')
        nbr_days = request.form.get('nbr_days')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        registration_start = datetime.strptime(request.form.get('registration_start'), '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
        registration_end = datetime.strptime(request.form.get('registration_end'), '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)

        # Get max_players from form
        max_players = int(request.form.get('max_players', 0))
        # Ensure max_players is at least nbr_teams * 2
        min_required_players = nbr_teams * 2
        if max_players < min_required_players:
            max_players = min_required_players

        # Only create basic league details in step 1
        new_league = League(
            lg_club_id=club_id,
            lg_name=name,
            lg_level=level,
            lg_status='announced',  # Initial status for new leagues
            lg_nbrDays=nbr_days,
            lg_nbrTeams=nbr_teams,
            lg_startDate=start_date,
            lg_endDate=start_date + timedelta(weeks=int(nbr_days)),  # Use weeks instead of days
            lg_registration_start=registration_start,
            lg_registration_end=registration_end,
            lg_max_players=max_players,  # Use the form value for max_players
            lg_typeOfLeague="Non-Stop League",  # Default value
            tb_maxLevel=0,  # Default value
            lg_eloK=nbr_teams * 10  # Default value based on number of teams
        )
        
        # Validate registration dates
        if registration_start >= registration_end:
            flash(translate('Registration end must be after registration start'), 'error')
            return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

        # Make sure registration ends before the league starts - convert both to date objects for comparison
        if registration_end.date() > start_date.date():
            flash(translate('Registration must end before league start date'), 'error')
            return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

        db.session.add(new_league)
        db.session.commit()

        # Create GameDays for the league using helper function
        #func_create_league_gamedays(new_league.lg_id, name, start_date, nbr_days)
        #db.session.commit()

        # Proceed to step 2
        return redirect(url_for('views.create_league_step2', league_id=new_league.lg_id))

    return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

@views.route('/create_league_step2/<int:league_id>', methods=['GET'])
@login_required
def create_league_step2(league_id):
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
    
    # Get club and courts
    club = Club.query.get_or_404(league.lg_club_id)
    courts = Court.query.filter_by(ct_club_id=club.cl_id).all()
    
    return render_template('create_league_step2.html', 
                           user=current_user, 
                           league=league, 
                           courts=courts,
                           club_name=club.cl_name)

@views.route('/complete_league_creation/<int:league_id>', methods=['POST'])
@login_required
def complete_league_creation(league_id):
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
    
    # Validate selected courts
    selected_courts = request.form.getlist('selected_courts')
    required_courts = (league.lg_nbrTeams + 1) // 2
    
    if len(selected_courts) != required_courts:
        club = Club.query.get_or_404(league.lg_club_id)
        courts = Court.query.filter_by(ct_club_id=club.cl_id).all()
        flash(translate(f'You must select exactly {required_courts} courts for {league.lg_nbrTeams} teams.'), 'error')
        return render_template('create_league_step2.html', 
                               user=current_user, 
                               league=league, 
                               courts=courts,
                               club_name=club.cl_name)
    
    # Update league with step 2 details
    start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
    min_warm_up = request.form.get('min_warm_up')
    min_per_game = request.form.get('min_per_game')
    min_between_games = request.form.get('min_between_games')
    type_of_league = request.form.get('type_of_league')
    max_level = request.form.get('max_level')
    elo_k = request.form.get('elo_k')
    lg_nbr_substitutes = request.form.get('lg_nbr_substitutes', 0, type=int)
    lg_nbr_auto_substitutes = request.form.get('lg_nbr_auto_substitutes', 0, type=int)
    lg_presence_points = request.form.get('lg_presence_points', 0, type=int)
    
    league.lg_startTime = start_time
    league.lg_minWarmUp = min_warm_up
    league.lg_minPerGame = min_per_game
    league.lg_minBetweenGames = min_between_games
    league.lg_typeOfLeague = type_of_league
    league.tb_maxLevel = max_level
    league.lg_eloK = elo_k
    league.lg_nbr_substitutes = lg_nbr_substitutes
    league.lg_nbr_auto_substitutes = lg_nbr_auto_substitutes
    league.lg_presence_points = lg_presence_points
    
    # Validate the values
    try:
        league.validate_substitutes()
    except ValueError as e:
        flash(translate(str(e)), 'error')
        return render_template('create_league_step2.html', 
                             user=current_user, 
                             league=league, 
                             courts=courts,
                             club_name=club.cl_name)
    
    # Store selected courts for the league
    for court_id in selected_courts:
        league_court = LeagueCourts(
            lc_league_id=league_id,
            lc_court_id=int(court_id)
        )
        db.session.add(league_court)
    
    db.session.commit()

    # Handle photos
    photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'leagues', str(league_id))
    
    # Handle main photo upload
    image = request.files.get('league_photo')
    if image and image.filename:
        if not os.path.exists(photos_dir):
            os.makedirs(photos_dir)
            
        file_path = os.path.join(photos_dir, 'main.jpg')
        if os.path.exists(file_path):
            os.remove(file_path)
        
        image.save(file_path)

    # Handle secondary photos
    secondary_photos = request.files.getlist('league_secondary_photos')
    if secondary_photos and any(photo.filename for photo in secondary_photos):
        secondary_dir = os.path.join(photos_dir, 'secondary')
        if not os.path.exists(secondary_dir):
            os.makedirs(secondary_dir)
            
        # Remove existing secondary photos
        for existing_file in os.listdir(secondary_dir) if os.path.exists(secondary_dir) else []:
            os.remove(os.path.join(secondary_dir, existing_file))
        
        # Save new photos
        for idx, photo in enumerate(secondary_photos, start=1):
            if photo.filename:
                photo_path = os.path.join(secondary_dir, f'{idx}.jpg')
                photo.save(photo_path)

    #Create GameDays for the league using helper function
    func_create_league_gamedays(league.lg_id, league.lg_name, league.lg_startDate, league.lg_nbrDays)
    db.session.commit()

    flash(translate('League created successfully!'), 'success')
    return redirect(url_for('views.managementLeagues'))

@views.route('/update_league_basic/<int:league_id>', methods=['POST'])
@login_required
def update_league_basic(league_id):
    league = League.query.get_or_404(league_id)
    
    # Check authorization
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this league!'), 'error')
        return redirect(url_for('views.managementLeagues'))
    
    league.lg_name = request.form.get('title')
    league.lg_level = request.form.get('level')
    league.lg_nbrDays = request.form.get('nbr_days')
    league.lg_nbrTeams = request.form.get('nbr_teams')
    league.lg_max_players = int(request.form.get('nbr_teams')) * 2
    league.lg_startDate = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    league.lg_endDate = league.lg_startDate + timedelta(weeks=int(league.lg_nbrDays))  # Use weeks instead of days
    
    # Ensure timezone info is set for registration dates
    league.lg_registration_start = datetime.strptime(
        request.form.get('registration_start'), 
        '%Y-%m-%dT%H:%M'
    ).replace(tzinfo=timezone.utc)
    
    league.lg_registration_end = datetime.strptime(
        request.form.get('registration_end'), 
        '%Y-%m-%dT%H:%M'
    ).replace(tzinfo=timezone.utc)
    
    db.session.commit()
    flash(translate('Basic league information updated successfully!'), 'success')

    image = request.files.get('league_photo')
    if image and image.filename:
        photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'leagues', str(league_id))
        file_path = os.path.join(photos_dir, 'main.jpg')
        
        if not os.path.exists(photos_dir):
            os.makedirs(photos_dir)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        
        image.save(file_path)

    # Register secondary photos
    secondary_photos = request.files.getlist('league_secondary_photos')
    if secondary_photos and any(photo.filename for photo in secondary_photos):
        photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'leagues', str(league_id))
        secondary_dir = os.path.join(photos_dir, 'secondary')
        
        if not os.path.exists(secondary_dir):
            os.makedirs(secondary_dir)
            
        # Remove existing secondary photos
        for existing_file in os.listdir(secondary_dir) if os.path.exists(secondary_dir) else []:
            os.remove(os.path.join(secondary_dir, existing_file))
        
        # Save new photos
        for idx, photo in enumerate(secondary_photos, start=1):
            if photo.filename:
                photo_path = os.path.join(secondary_dir, f'{idx}.jpg')
                photo.save(photo_path)

    return redirect(url_for('views.edit_league', league_id=league_id) + '#basic-info')

@views.route('/update_league_details/<int:league_id>', methods=['POST'])
@login_required
def update_league_details(league_id):
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

    # Check if league settings can be modified
    if not league.can_modify_league_settings():
        flash(translate('League settings cannot be modified after the first gameday date'), 'error')
        return redirect(url_for('views.edit_league', league_id=league_id) + '#court-details')
    
    # Validate selected courts
    selected_courts = request.form.getlist('selected_courts')
    required_courts = (league.lg_nbrTeams + 1) // 2
    
    if len(selected_courts) != required_courts:
        flash(translate(f'You must select exactly {required_courts} courts for {league.lg_nbrTeams} teams.'), 'error')
        return redirect(url_for('views.edit_league', league_id=league_id) + '#court-details')
    
    # Update league details
    league.lg_startTime = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
    league.lg_minWarmUp = request.form.get('min_warm_up')
    league.lg_minPerGame = request.form.get('min_per_game')
    league.lg_minBetweenGames = request.form.get('min_between_games')
    league.lg_typeOfLeague = request.form.get('type_of_league')
    league.lg_maxLevel = request.form.get('max_level')
    league.lg_eloK = request.form.get('elo_k')

    # Handle new fields if league settings can be modified
    league.lg_nbr_substitutes = request.form.get('lg_nbr_substitutes', 0, type=int)
    league.lg_nbr_auto_substitutes = request.form.get('lg_nbr_auto_substitutes', 0, type=int)
    league.lg_presence_points = request.form.get('lg_presence_points', 0, type=int)

    # Validate the values
    try:
        league.validate_substitutes()
    except ValueError as e:
        flash(translate(str(e)), 'error')
        return redirect(url_for('views.edit_league', league_id=league_id) + '#court-details')
    
    # Update court selections - first remove existing relationships
    LeagueCourts.query.filter_by(lc_league_id=league_id).delete()
    
    # Add new court relationships
    for court_id in selected_courts:
        league_court = LeagueCourts(
            lc_league_id=league_id,
            lc_court_id=int(court_id)
        )
        db.session.add(league_court)
    
    db.session.commit()

    # Handle main photo upload
    image = request.files.get('league_photo')
    if image and image.filename:
        path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(league_id)+'/'
        if not os.path.exists(path):
            os.makedirs(path)
            
        filePath = path + 'main.jpg'
        if os.path.exists(filePath):
            os.remove(filePath)
        
        image.save(filePath)

    # Handle secondary photos
    secondary_photos = request.files.getlist('league_secondary_photos')
    if secondary_photos and any(photo.filename for photo in secondary_photos):
        path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(league_id)+'/'
        secondary_path = os.path.join(path, 'secondary')
        if not os.path.exists(secondary_path):
            os.makedirs(secondary_path)
            
        # Remove existing secondary photos
        for existing_file in os.listdir(secondary_path) if os.path.exists(secondary_path) else []:
            os.remove(os.path.join(secondary_path, existing_file))
        
        # Save new photos
        for idx, photo in enumerate(secondary_photos, start=1):
            if photo.filename:
                photo_path = os.path.join(secondary_path, f'{idx}.jpg')
                photo.save(photo_path)

    flash(translate('League details updated successfully!'), 'success')
    return redirect(url_for('views.edit_league', league_id=league_id) + '#court-details')

@views.route('/create_and_add_league_player/<int:league_id>', methods=['GET', 'POST'])
@login_required
def create_and_add_league_player(league_id):
    league = League.query.get_or_404(league_id)
    return_url = request.args.get('return_url') or url_for('views.edit_league', league_id=league_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to add players to this league!'), 'error')
        return redirect(return_url)

    if league.current_player_count >= league.lg_max_players:
        flash(translate('League is already full!'), 'error')
        return redirect(return_url)

    if request.method == 'POST':
        fullname = request.form.get('fullname')
        telephone = request.form.get('telephone')
        email = request.form.get('email')
        photo = request.files.get('photo')
        user_id = request.form.get('user_id')

        if user_id:
            user_selected = Users.query.get_or_404(user_id)

        else:
            # Check for existing phone number
            existing_phone = Users.query.filter_by(us_telephone=telephone).first()
            if existing_phone:
                flash(translate('A user with this telephone number already exists!'), 'error')
                return redirect(return_url)

            if email:
                # Check for existing email
                existing_email = Users.query.filter_by(us_email=email).first()
                if existing_email:
                    flash(translate('A user with this email already exists!'), 'error')
                    return redirect(return_url)

        # Look up user by telephone or email
        if email:
            user = Users.query.filter(
                (Users.us_telephone == telephone) | (Users.us_email == email)
            ).first()
        else:
            user = Users.query.filter(
                (Users.us_telephone == telephone)
            ).first()
        
        if not user:
            # Create new user with hashed password
            # Make email optional
            if email:
                user = Users(
                    us_name=fullname,
                    us_email=email,
                    us_telephone=telephone,
                    us_is_active=True,
                    us_is_player=True,
                    us_birthday=datetime.strptime('1995-01-01', '%Y-%m-%d').date(),
                    us_pwd=generate_password_hash('welcome2padel', method='pbkdf2:sha256')
                )
            else:
                user = Users(
                    us_name=fullname,
                    us_telephone=telephone,
                    us_is_active=True,
                    us_is_player=True,
                    us_birthday=datetime.strptime('1995-01-01', '%Y-%m-%d').date(),
                    us_pwd=generate_password_hash('welcome2padel', method='pbkdf2:sha256')
                )
            db.session.add(user)
            db.session.commit()

            # Handle photo upload if provided
            if photo:
                path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'photos', 'users', str(user.us_id))
                if not os.path.exists(path):
                    os.makedirs(path)
                photo.save(os.path.join(path, 'main.jpg'))

        # Check if user is already registered in this league
        existing_registration = LeaguePlayers.query.filter_by(
            lp_league_id=league_id,
            lp_player_id=user.us_id
        ).first()

        if existing_registration:
            flash(translate('Player is already registered in this league!'), 'error')
        else:
            # Register player to league
            new_registration = LeaguePlayers(
                lp_league_id=league_id,
                lp_player_id=user.us_id,
                lp_registered_by_id=current_user.us_id
            )
            db.session.add(new_registration)
            db.session.commit()
            flash(translate('Player successfully added to league!'), 'success')

        return redirect(return_url)

    title_add_user_event = f"{translate('Add Player')} - {league.lg_name}"
    return render_template('add_user_event.html', 
                         user=current_user, 
                         league=league, 
                         return_url=return_url,
                         title_add_user_event=title_add_user_event)

# Gameday management routes
@views.route('/create_gamedays', methods=['GET'])
@login_required
def create_gamedays():
    return func_create_gamedays()

@views.route('/create_gameday_games/<int:league_id>/<int:gameday_id>', methods=['GET'])
@login_required
def create_gameday_games_route(league_id, gameday_id):
    func_create_gameday_games_full(league_id, gameday_id)
    
    flash(translate('Games created successfully!'), 'success')
    return redirect(url_for('views.edit_gameday', gameday_id=gameday_id))

@views.route('/edit_gameday/<int:gameday_id>', methods=['GET', 'POST'])
@login_required
def edit_gameday(gameday_id):
    return func_edit_gameday(gameday_id)  # Add return statement

@views.route('/insert_game_day_players/<gameDayID>', methods=['GET', 'POST'])
@login_required
def insert_game_day_players(gameDayID):
    return func_insert_game_day_players(gameDayID)


@views.route('/submitResultsGameDay/<gameDayID>', methods=['GET', 'POST'])
@login_required
def submitResultsGameDay(gameDayID):
    return func_submitResultsGameDay(gameDayID)

@views.route('/league/<int:league_id>/remove_player/<int:user_id>', methods=['POST'])
@login_required
def remove_league_player(league_id, user_id):
    league = League.query.get_or_404(league_id)
    user = Users.query.get_or_404(user_id)
    
    # Check if user is authorized for this club through ClubAuthorization
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == league.lg_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You do not have permission to remove players from this league.'), 'error')
        return redirect(url_for('views.edit_league', league_id=league_id))
    
    league_player = LeaguePlayers.query.filter_by(lp_league_id=league_id, lp_player_id=user_id).first()
    if league_player:
        db.session.delete(league_player)
        db.session.commit()
        flash(translate('Player successfully removed from the league.'), 'success')
    else:
        flash(translate('Player not found in this league.'), 'error')
    
    return redirect(url_for('views.edit_league', league_id=league_id))

# Other routes
@views.route('/display_user_image/<userID>')
def display_user_image(userID):
    photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'users', str(userID))
    file_path = os.path.join(photos_dir, 'main.jpg')
    
    if os.path.isfile(file_path):
        img = func_crop_image_in_memory(file_path)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/users/nophoto.jpg'), code=301)

@views.route('/display_club_main_image/<clubID>')
def display_club_main_image(clubID):
    photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'clubs', str(clubID))
    file_path = os.path.join(photos_dir, 'main.jpg')
    
    if os.path.isfile(file_path):
        img = func_crop_image_in_memory(file_path)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/clubs/nophoto.jpg'), code=301)
    
@views.route('/display_club_second_image/<clubID>')
def display_club_second_image(clubID):
    photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'clubs', str(clubID), 'secondary')
    file_path = os.path.join(photos_dir, '1.jpg')
    
    if os.path.isfile(file_path):
        img = func_crop_image_in_memory(file_path)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/clubs/nophoto.jpg'), code=301)

@views.route('/display_package_main_image/<int:eventID>/<int:packageID>')
def display_package_main_image(eventID, packageID):
    filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/clubs/'+str(eventID)+'/packages/'+str(packageID)+'/main.jpg'
    if os.path.isfile(filePath):
        img = func_crop_image_in_memory(filePath)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/clubs/nophoto.jpg'), code=301)

@views.route('/display_league_main_image/<leagueID>')
def display_league_main_image(leagueID):
    photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'leagues', str(leagueID))
    file_path = os.path.join(photos_dir, 'main.jpg')
    
    if os.path.isfile(file_path):
        img = func_crop_image_in_memory(file_path)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/leagues/nophoto.jpg'), code=301)
    
@views.route('/display_league_second_image/<leagueID>')
def display_league_second_image(leagueID):
    photos_dir = os.path.join(os.path.dirname(__file__), 'static', 'photos', 'leagues', str(leagueID), 'secondary')
    file_path = os.path.join(photos_dir, '1.jpg')
    
    if os.path.isfile(file_path):
        img = func_crop_image_in_memory(file_path)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/leagues/nophoto.jpg'), code=301)

@views.route('/league/<int:league_id>', methods=['GET'])
def detail_league(league_id):
    # Get the league with registered players loaded
    league = League.query.options(db.joinedload(League.registered_players)).get_or_404(league_id)
    
    # Get the club information
    club = Club.query.get_or_404(league.lg_club_id)
    
    # Get gamedays for this league
    gamedays = GameDay.query.filter_by(gd_idLeague=league_id).order_by(GameDay.gd_date).all()
    
    # Calculate player statistics from league classification
    players_stats = []
    for player in league.registered_players:
        # Get player info
        user = Users.query.get(player.lp_player_id)
        
        # Get player's league classification
        league_class = LeagueClassification.query.filter_by(
            lc_idLeague=league_id,
            lc_idPlayer=player.lp_player_id
        ).first()
        
        if league_class:
            wins = league_class.lc_wins
            losses = league_class.lc_losses
            gamesFavor = league_class.lc_gamesFavor
            gamesAgainst = league_class.lc_gamesAgainst
            gamesDiff = gamesFavor - gamesAgainst
            ranking = league_class.lc_ranking   
            games_played = wins + losses
            win_rate = wins / games_played if games_played > 0 else 0
            points = league_class.lc_points
        else:
            # If no classification exists yet, initialize with zeros
            wins = 0
            losses = 0
            gamesFavor = 0
            gamesAgainst = 0
            gamesDiff = 0
            ranking = 0
            games_played = 0
            win_rate = 0
            points = 0

        players_stats.append({
            'us_id': user.us_id,
            'us_name': user.us_name,
            'games_played': games_played,
            'wins': wins,
            'losses': losses,
            'gamesFavor': gamesFavor,
            'gamesAgainst': gamesAgainst,
            'gamesDiff': gamesDiff,
            'ranking': ranking,
            'win_rate': win_rate,
            'points': points
        })

    # Sort players by points and win rate
    players_stats.sort(key=lambda x: (-x['points'], -x['win_rate']))
    
    return render_template('league_detail.html', 
                           user=current_user, 
                           league=league,
                           club=club,
                           gamedays=gamedays,
                           players=players_stats)

@views.route('/gameday/<int:gameday_id>', methods=['GET'])
def gameday_detail(gameday_id):
    # Get the gameday with games relationship explicitly loaded
    gameday = GameDay.query.options(db.joinedload(GameDay.games)).get_or_404(gameday_id)
    
    # Get the associated league
    league = League.query.get_or_404(gameday.gd_idLeague)
    
    # Get the club information
    club = Club.query.get_or_404(league.lg_club_id)
    
    # Debug games and results
    has_games = bool(gameday.games)
    has_results = any((game.gm_result_A and game.gm_result_A != 0) or 
                     (game.gm_result_B and game.gm_result_B != 0) 
                     for game in gameday.games) if has_games else False
    
    # Check if user is registered for this gameday
    is_registered = False
    is_league_player = False
    if current_user.is_authenticated:
        is_registered = GameDayRegistration.query.filter_by(
            gdr_gameday_id=gameday_id,
            gdr_player_id=current_user.us_id
        ).first() is not None
        
        # Check if user is registered in the league
        is_league_player = LeaguePlayers.query.filter_by(
            lp_league_id=league.lg_id,
            lp_player_id=current_user.us_id
        ).first() is not None

    # Ensure registration dates are timezone-aware
    if gameday.gd_registration_start and gameday.gd_registration_start.tzinfo is None:
        registration_start = gameday.gd_registration_start.replace(tzinfo=timezone.utc)
    else:
        registration_start = gameday.gd_registration_start

    if gameday.gd_registration_end and gameday.gd_registration_end.tzinfo is None:
        registration_end = gameday.gd_registration_end.replace(tzinfo=timezone.utc)
    else:
        registration_end = gameday.gd_registration_end

    return render_template('gameday_detail.html', 
                         user=current_user, 
                         gameday=gameday,
                         league=league,
                         club=club,
                         is_registered=is_registered,
                         is_league_player=is_league_player,
                         registration_start=registration_start,
                         registration_end=registration_end,
                         now=lambda: datetime.now(timezone.utc))

@views.route('/search_users', methods=['GET'])
def search_users():
    try:
        query = request.args.get('query', '').lower()
        
        if len(query) < 3:
            return jsonify([])
            
        users = Users.query.filter(
            db.or_(
                db.func.lower(Users.us_name).like(f'%{query}%'),
                db.func.lower(Users.us_email).like(f'%{query}%'),
                Users.us_telephone.like(f'%{query}%')
            )
        ).limit(10).all()
        
        results = [{
            'id': user.us_id,
            'name': user.us_name,
            'email': user.us_email,
            'telephone': user.us_telephone
        } for user in users]
        
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@views.route('/player_info/<int:user_id>', methods=['GET'])
def player_info(user_id):
    p_user = Users.query.get_or_404(user_id)
    
    # Define the cutoff date for statistics
    cutoff_date = datetime.strptime('2024-01-01', '%Y-%m-%d').date()
    
    # Count won game days
    num_game_day_won = db.session.query(func.count()).filter(
        ((GameDay.gd_idWinner1 == user_id) | (GameDay.gd_idWinner2 == user_id)) &
        (GameDay.gd_date > cutoff_date)
    ).scalar()
    num_game_day_won_text = f"Winner of {num_game_day_won} events!" if num_game_day_won > 0 else "Has not won any events yet!"

    # Get last game date
    last_game_date = db.session.query(Game.gm_date).filter(
        ((Game.gm_idPlayer_A1 == user_id) |
        (Game.gm_idPlayer_A2 == user_id) |
        (Game.gm_idPlayer_B1 == user_id) |
        (Game.gm_idPlayer_B2 == user_id)) & (Game.gm_date > cutoff_date)
    ).order_by(Game.gm_date.desc()).first()
    last_game_date_string = last_game_date[0].strftime('%Y-%m-%d') if last_game_date else "No games registered yet!"

    # Get all games with ELO changes
    try:
        games_query = db.session.execute(
            text("SELECT g.gm_date, g.gm_timeStart, g.gm_timeEnd, c.ct_name as gm_court, "
                "u1.us_name as gm_namePlayer_A1, u2.us_name as gm_namePlayer_A2, "
                "g.gm_result_A, g.gm_result_B, "
                "u3.us_name as gm_namePlayer_B1, u4.us_name as gm_namePlayer_B2, "
                "g.gm_id, g.gm_idPlayer_A1, g.gm_idPlayer_A2, g.gm_idPlayer_B1, g.gm_idPlayer_B2, "
                "(eh.el_afterRank - eh.el_beforeRank) AS gm_points_var "
                "FROM tb_game g "
                "JOIN tb_court c ON c.ct_id = g.gm_court "
                "JOIN tb_users u1 ON u1.us_id = g.gm_idPlayer_A1 "
                "JOIN tb_users u2 ON u2.us_id = g.gm_idPlayer_A2 "
                "JOIN tb_users u3 ON u3.us_id = g.gm_idPlayer_B1 "
                "JOIN tb_users u4 ON u4.us_id = g.gm_idPlayer_B2 "
                "LEFT JOIN tb_ELO_ranking_hist eh ON eh.el_gm_id = g.gm_id AND eh.el_pl_id = :userID "
                "WHERE (g.gm_idPlayer_A1 = :userID OR g.gm_idPlayer_A2 = :userID OR "
                "g.gm_idPlayer_B1 = :userID OR g.gm_idPlayer_B2 = :userID) "
                "AND (g.gm_result_A > 0 OR g.gm_result_B > 0) "
                "ORDER BY g.gm_date DESC, g.gm_timeStart DESC"),
            {"userID": user_id}
        ).fetchall()
    except Exception as e:
        print(f"Error getting games: {str(e)}")
        games_query = []

    # Get worst nightmare
    try:
        worst_nightmare = db.session.execute(
            text("""
                WITH OpponentGames AS (
                    SELECT 
                        CASE 
                            WHEN gm_idPlayer_A1 = :userID OR gm_idPlayer_A2 = :userID THEN 
                                CASE 
                                    WHEN gm_result_B > gm_result_A THEN 
                                        CASE 
                                            WHEN gm_idPlayer_B1 != :userID THEN gm_idPlayer_B1 
                                            ELSE gm_idPlayer_B2 
                                        END 
                                END
                            WHEN gm_idPlayer_B1 = :userID OR gm_idPlayer_B2 = :userID THEN
                                CASE 
                                    WHEN gm_result_A > gm_result_B THEN 
                                        CASE 
                                            WHEN gm_idPlayer_A1 != :userID THEN gm_idPlayer_A1 
                                            ELSE gm_idPlayer_A2 
                                        END 
                                END
                        END AS winning_opponent
                    FROM tb_game
                    WHERE (gm_idPlayer_A1 = :userID OR gm_idPlayer_A2 = :userID OR 
                          gm_idPlayer_B1 = :userID OR gm_idPlayer_B2 = :userID)
                    AND gm_date > :cutoff_date
                )
                SELECT 
                    u.us_id as oponent,
                    u.us_name as playerName,
                    COUNT(*) as losses,
                    (
                        SELECT COUNT(*) 
                        FROM tb_game g
                        WHERE (
                            (g.gm_idPlayer_A1 = :userID OR g.gm_idPlayer_A2 = :userID) AND 
                            (g.gm_idPlayer_B1 = u.us_id OR g.gm_idPlayer_B2 = u.us_id)
                        ) OR (
                            (g.gm_idPlayer_B1 = :userID OR g.gm_idPlayer_B2 = :userID) AND 
                            (g.gm_idPlayer_A1 = u.us_id OR g.gm_idPlayer_A2 = u.us_id)
                        )
                        AND g.gm_date > :cutoff_date
                    ) as games,
                    CAST(COUNT(*) AS FLOAT) * 100 / (
                        SELECT COUNT(*) 
                        FROM tb_game g
                        WHERE (
                            (g.gm_idPlayer_A1 = :userID OR g.gm_idPlayer_A2 = :userID) AND 
                            (g.gm_idPlayer_B1 = u.us_id OR g.gm_idPlayer_B2 = u.us_id)
                        ) OR (
                            (g.gm_idPlayer_B1 = :userID OR g.gm_idPlayer_B2 = :userID) AND 
                            (g.gm_idPlayer_A1 = u.us_id OR g.gm_idPlayer_A2 = u.us_id)
                        )
                        AND g.gm_date > :cutoff_date
                    ) as lostPerc
                FROM OpponentGames og
                JOIN tb_users u ON og.winning_opponent = u.us_id
                GROUP BY u.us_id, u.us_name
                ORDER BY lostPerc DESC, losses DESC
                LIMIT 1
            """),
            {"userID": user_id, "cutoff_date": cutoff_date}
        ).fetchone() or ['', '', 0, 0, 0]
    except Exception as e:
        print(f"Error getting worst nightmare: {str(e)}")
        worst_nightmare = ['', '', 0, 0, 0]

    # Get best opponent (opponent you beat the most)
    try:
        best_opponent = db.session.execute(
            text("""
                WITH OpponentGames AS (
                    SELECT 
                        CASE 
                            WHEN gm_idPlayer_A1 = :userID OR gm_idPlayer_A2 = :userID THEN 
                                CASE 
                                    WHEN gm_result_A > gm_result_B THEN 
                                        CASE 
                                            WHEN gm_idPlayer_B1 != :userID THEN gm_idPlayer_B1 
                                            ELSE gm_idPlayer_B2 
                                        END 
                                END
                            WHEN gm_idPlayer_B1 = :userID OR gm_idPlayer_B2 = :userID THEN
                                CASE 
                                    WHEN gm_result_B > gm_result_A THEN 
                                        CASE 
                                            WHEN gm_idPlayer_A1 != :userID THEN gm_idPlayer_A1 
                                            ELSE gm_idPlayer_A2 
                                        END 
                                END
                        END AS losing_opponent
                    FROM tb_game
                    WHERE (gm_idPlayer_A1 = :userID OR gm_idPlayer_A2 = :userID OR 
                          gm_idPlayer_B1 = :userID OR gm_idPlayer_B2 = :userID)
                    AND gm_date > :cutoff_date
                )
                SELECT 
                    u.us_id as oponent,
                    u.us_name as playerName,
                    COUNT(*) as victories,
                    (
                        SELECT COUNT(*) 
                        FROM tb_game g
                        WHERE (
                            (g.gm_idPlayer_A1 = :userID OR g.gm_idPlayer_A2 = :userID) AND 
                            (g.gm_idPlayer_B1 = u.us_id OR g.gm_idPlayer_B2 = u.us_id)
                        ) OR (
                            (g.gm_idPlayer_B1 = :userID OR g.gm_idPlayer_B2 = :userID) AND 
                            (g.gm_idPlayer_A1 = u.us_id OR g.gm_idPlayer_A2 = u.us_id)
                        )
                        AND g.gm_date > :cutoff_date
                    ) as games,
                    CAST(COUNT(*) AS FLOAT) * 100 / (
                        SELECT COUNT(*) 
                        FROM tb_game g
                        WHERE (
                            (g.gm_idPlayer_A1 = :userID OR g.gm_idPlayer_A2 = :userID) AND 
                            (g.gm_idPlayer_B1 = u.us_id OR g.gm_idPlayer_B2 = u.us_id)
                        ) OR (
                            (g.gm_idPlayer_B1 = :userID OR g.gm_idPlayer_B2 = :userID) AND 
                            (g.gm_idPlayer_A1 = u.us_id OR g.gm_idPlayer_A2 = u.us_id)
                        )
                        AND g.gm_date > :cutoff_date
                    ) as victPerc
                FROM OpponentGames og
                JOIN tb_users u ON og.losing_opponent = u.us_id
                GROUP BY u.us_id, u.us_name
                ORDER BY victPerc DESC, victories DESC
                LIMIT 1
            """),
            {"userID": user_id, "cutoff_date": cutoff_date}
        ).fetchone() or ['', '', 0, 0, 0]
    except Exception as e:
        print(f"Error getting best opponent: {str(e)}")
        best_opponent = ['', '', 0, 0, 0]

    # Get best teammate using SQLAlchemy ORM
    try:
        subquery = db.session.query(
            case(
                (and_(Game.gm_idPlayer_A1 == user_id, Game.gm_idPlayer_A2), Game.gm_idPlayer_A2),
                (and_(Game.gm_idPlayer_A2 == user_id, Game.gm_idPlayer_A1), Game.gm_idPlayer_A1),
                (and_(Game.gm_idPlayer_B1 == user_id, Game.gm_idPlayer_B2), Game.gm_idPlayer_B2),
                (and_(Game.gm_idPlayer_B2 == user_id, Game.gm_idPlayer_B1), Game.gm_idPlayer_B1)
            ).label('teamMate'),
            case(
                (and_(or_(Game.gm_idPlayer_A1 == user_id, Game.gm_idPlayer_A2 == user_id),
                      Game.gm_result_A > Game.gm_result_B), 1),
                (and_(or_(Game.gm_idPlayer_B1 == user_id, Game.gm_idPlayer_B2 == user_id),
                      Game.gm_result_B > Game.gm_result_A), 1),
                else_=0
            ).label('won')
        ).filter(
            or_(Game.gm_idPlayer_A1 == user_id, Game.gm_idPlayer_A2 == user_id,
                Game.gm_idPlayer_B1 == user_id, Game.gm_idPlayer_B2 == user_id),
            or_(Game.gm_result_A > 0, Game.gm_result_B > 0),
            Game.gm_date > cutoff_date
        ).subquery()

        best_teammate = db.session.query(
            Users.us_name,
            (func.sum(subquery.c.won) * 100.0 / func.count(subquery.c.teamMate)).label('winPerc'),
            func.sum(subquery.c.won).label('won'),
            func.count(subquery.c.teamMate).label('totalgames')
        ).join(
            subquery, subquery.c.teamMate == Users.us_id
        ).group_by(
            subquery.c.teamMate
        ).order_by(
            desc('winPerc'),
            desc('won')
        ).first() or ['', 0, 0, 0]
    except Exception as e:
        print(f"Error getting best teammate: {str(e)}")
        best_teammate = ['', 0, 0, 0]

    # Get worst teammate using SQL query for better performance
    try:
        worst_teammate = db.session.execute(
            text("""
                WITH PlayerGames AS (
                    SELECT 
                        CASE 
                            WHEN gm_idPlayer_A1 = :userID THEN gm_idPlayer_A2
                            WHEN gm_idPlayer_A2 = :userID THEN gm_idPlayer_A1
                            WHEN gm_idPlayer_B1 = :userID THEN gm_idPlayer_B2
                            WHEN gm_idPlayer_B2 = :userID THEN gm_idPlayer_B1
                        END AS teamMate,
                        CASE
                            WHEN ((gm_idPlayer_A1 = :userID OR gm_idPlayer_A2 = :userID) AND gm_result_B > gm_result_A)
                                OR ((gm_idPlayer_B1 = :userID OR gm_idPlayer_B2 = :userID) AND gm_result_A > gm_result_B)
                            THEN 1
                            ELSE 0
                        END AS lost
                    FROM tb_game
                    WHERE (gm_idPlayer_A1 = :userID OR gm_idPlayer_A2 = :userID OR 
                          gm_idPlayer_B1 = :userID OR gm_idPlayer_B2 = :userID)
                    AND gm_date > :cutoff_date
                )
                SELECT 
                    u.us_name as pl_name,
                    ((SUM(lost)*100.0) / COUNT(*)) as lostPerc,
                    SUM(lost) as lost,
                    COUNT(*) as totalgames
                FROM PlayerGames pg
                JOIN tb_users u ON u.us_id = pg.teamMate
                GROUP BY teamMate, u.us_name
                ORDER BY lostPerc DESC, lost DESC
                LIMIT 1
            """),
            {"userID": user_id, "cutoff_date": cutoff_date}
        ).fetchone() or ['', 0, 0, 0]
    except Exception as e:
        print(f"Error getting worst teammate: {str(e)}")
        worst_teammate = ['', 0, 0, 0]

    # Get player stats (wins/losses)
    try:
        player_stats = db.session.query(
            func.sum(case(
                (and_(or_(Game.gm_idPlayer_A1 == user_id, Game.gm_idPlayer_A2 == user_id),
                      Game.gm_result_A > Game.gm_result_B), 1),
                (and_(or_(Game.gm_idPlayer_B1 == user_id, Game.gm_idPlayer_B2 == user_id),
                      Game.gm_result_B > Game.gm_result_A), 1),
                else_=0
            )).label('games_won'),
            func.count(Game.gm_id).label('total_games')
        ).filter(
            or_(Game.gm_idPlayer_A1 == user_id, Game.gm_idPlayer_A2 == user_id,
                Game.gm_idPlayer_B1 == user_id, Game.gm_idPlayer_B2 == user_id),
            or_(Game.gm_result_A > 0, Game.gm_result_B > 0),
            Game.gm_date > cutoff_date
        ).first() or (0, 0)

        # Get best and worst ELO ratings from history
        rankingELO_bestWorst = db.session.execute(
            text("""
                SELECT max(el_afterRank) as best, min(el_afterRank) as worst, (SELECT el_afterRank from `tb_ELO_ranking_hist` where el_pl_id=:userID order by el_date desc, el_startTime desc limit 1) as rankNow FROM `tb_ELO_ranking_hist` where el_pl_id=:userID
            """),
            {"userID": user_id}
        ).fetchone() or [1000, 1000, 1000]

    except Exception as e:
        print(f"Error getting player stats: {str(e)}")
        player_stats = (0, 0)
        rankingELO_bestWorst = [1000, 1000, 1000]

    # rankingELO_hist
    try:
        rankingELO_hist = db.session.execute(
            text(f"SELECT el_gm_id, el_date, el_startTime, el_result_team, el_result_op, el_beforeRank, el_afterRank FROM tb_ELO_ranking_hist where el_pl_id=:playerID order by el_date desc, el_startTime desc LIMIT 50"),
            {"playerID": user_id},
        ).fetchall()
    except Exception as e:
        print(f"Error: {str(e)}")

    if rankingELO_hist:
        pass
    else:
        rankingELO_hist=[0,0,0,0,0,0,0,0,0]

    # rankingELO_histShort
    try:
        rankingELO_histShort = db.session.execute(
            text(f"SELECT el_gm_id, el_date, el_startTime, el_result_team, el_result_op, el_beforeRank, el_afterRank FROM tb_ELO_ranking_hist where el_pl_id=:playerID order by el_date desc, el_startTime desc LIMIT 10"),
            {"playerID": user_id},
        ).fetchall()
    except Exception as e:
        print(f"Error: {str(e)}")

    if rankingELO_histShort:
        pass
    else:
        rankingELO_histShort=[0,0,0,0,0,0,0,0,0]

    player_data = {
        "player_id": p_user.us_id,
        "player_name": p_user.us_name,
        "player_email": p_user.us_email,
        "player_birthday": p_user.us_birthday,
        "numGameDayWins": num_game_day_won_text,
        "lastGamePlayed": last_game_date_string,
        "games_won": player_stats[0] if player_stats[0] else 0,
        "total_games": player_stats[1] if player_stats[1] else 0,
        "best_teammate_name": str(best_teammate[0]),
        "best_teammate_win_percentage": "{:.2f}".format(best_teammate[1]),
        "best_teammate_total_games": best_teammate[3],
        "worst_teammate_name": str(worst_teammate[0]),
        "worst_teammate_lost_percentage": "{:.2f}".format(worst_teammate[1]),
        "worst_teammate_total_games": worst_teammate[3],
        "worst_nightmare_name": str(worst_nightmare[1]),
        "worst_nightmare_lost_percentage": "{:.2f}".format(worst_nightmare[4]),
        "worst_nightmare_games": worst_nightmare[3],
        "best_opponent_name": str(best_opponent[1]),
        "best_opponent_victory_percentage": "{:.2f}".format(best_opponent[4]),
        "best_opponent_games": best_opponent[3],
    }

    return render_template("player_info.html", 
                         user=current_user, 
                         p_user=p_user, 
                         player=player_data,
                         results=games_query,
                         player_stats=player_stats,
                         rankingELO_bestWorst=rankingELO_bestWorst, 
                         rankingELO_hist=rankingELO_hist, 
                         rankingELO_histShort=rankingELO_histShort)


@views.route('/recalculate_ELO_full', methods=['GET', 'POST'])
@login_required
def recalculate_ELO_full():
    return func_calculate_ELO_full()


# =================== EVENT MANAGEMENT ROUTES ===================

@views.route('/managementEvents', methods=['GET', 'POST'])
@login_required
def managementEvents():
    """Management page for club events"""
    # Superusers can see all events, regular users see events from authorized clubs + their own events
    if current_user.us_is_superuser == 1:
        # Superuser: show all non-hidden events
        events_data = Event.query\
            .outerjoin(Club, Event.ev_club_id == Club.cl_id)\
            .filter(Event.ev_status != 'canceled')\
            .order_by(Event.ev_status, Event.ev_date.desc())\
            .all()
    else:
        # Regular user: show events from authorized clubs + events they created without clubs
        club_events = Event.query\
            .join(Club, Event.ev_club_id == Club.cl_id)\
            .join(ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id)\
            .filter(ClubAuthorization.ca_user_id == current_user.us_id)\
            .filter(Event.ev_status != 'canceled')
        
        personal_events = Event.query\
            .filter(Event.ev_club_id.is_(None))\
            .filter(Event.ev_created_by_id == current_user.us_id)\
            .filter(Event.ev_status != 'canceled')
        
        events_data = club_events.union(personal_events)\
            .order_by(Event.ev_status, Event.ev_date.desc())\
            .all()
        
    return render_template("managementEvents.html", user=current_user, result=events_data)


@views.route('/create_event_public', methods=['GET', 'POST'])
def create_event_public():
    """Public event creation - no login required"""
    # Get available event types for the form
    event_types = EventType.query.filter(EventType.et_is_active == True).order_by(EventType.et_order).all()

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        location = request.form.get('location')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        event_type_id = request.form.get('event_type_id')
        max_players = request.form.get('max_players')
        organizer_name = request.form.get('organizer_name')
        organizer_email = request.form.get('organizer_email')
        organizer_phone = request.form.get('organizer_phone')
        registration_start = request.form.get('registration_start')
        registration_end = request.form.get('registration_end')
        
        # Validate required fields
        if not all([title, location, event_date, event_time, event_type_id, max_players, organizer_name]):
            flash(translate('Please fill in all required fields!'), 'error')
            return render_template("create_event_public.html", event_types=event_types)
        
        # Validate event type exists and is active
        event_type = EventType.query.filter_by(et_id=int(event_type_id), et_is_active=True).first()
        if not event_type:
            flash(translate('Invalid event type selected!'), 'error')
            return render_template("create_event_public.html", event_types=event_types)

        try:
            # Parse date and time
            event_date_parsed = datetime.strptime(event_date, "%Y-%m-%d").date()
            event_time_parsed = datetime.strptime(event_time, "%H:%M").time()
            
            # Parse registration dates if provided
            reg_start_utc = None
            reg_end_utc = None
            if registration_start:
                reg_start_utc = datetime.strptime(registration_start, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            if registration_end:
                reg_end_utc = datetime.strptime(registration_end, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)

            # Find or create organizer user
            organizer_user = None
            if current_user.is_authenticated:
                organizer_user = current_user
            else:
                # Try to find existing user by email or phone
                if organizer_email:
                    organizer_user = Users.query.filter_by(us_email=organizer_email).first()
                if not organizer_user and organizer_phone:
                    organizer_user = Users.query.filter_by(us_telephone=organizer_phone).first()
                
                # Create new user if not found
                if not organizer_user:
                    organizer_user = Users(
                        us_name=organizer_name,
                        us_email=organizer_email,
                        us_telephone=organizer_phone,
                        us_is_active=True,
                        us_is_player=True,
                        us_birthday=datetime.strptime('1990-01-01', '%Y-%m-%d').date(),
                        us_pwd=generate_password_hash('welcome2padel', method='pbkdf2:sha256')
                    )
                    db.session.add(organizer_user)
                    db.session.commit()

            # Create new event without club
            new_event = Event(
                ev_title=title,
                ev_club_id=None,  # No club association
                ev_location=location,
                ev_date=event_date_parsed,
                ev_start_time=event_time_parsed,
                ev_type_id=int(event_type_id),
                ev_max_players=int(max_players),
                ev_registration_start=reg_start_utc,
                ev_registration_end=reg_end_utc,
                ev_status='announced',
                ev_created_by_id=organizer_user.us_id
            )

            db.session.add(new_event)
            db.session.commit()

            flash(translate('Event created successfully! Event ID: {}'.format(new_event.ev_id)), 'success')
            return redirect(url_for('views.public_event_detail', event_id=new_event.ev_id))

        except ValueError as e:
            flash(translate('Invalid date/time format!'), 'error')
            return render_template("create_event_public.html", event_types=event_types)
        except Exception as e:
            db.session.rollback()
            flash(translate('Error creating event!'), 'error')
            return render_template("create_event_public.html", event_types=event_types)

    return render_template("create_event_public.html", event_types=event_types)


@views.route('/create_event', methods=['GET', 'POST'])
@login_required
def create_event():
    """Create a new club event"""
    # Get authorized clubs
    authorized_clubs = Club.query.join(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id
    ).all()
    
    # Get available event types for the form
    event_types = EventType.query.filter(EventType.et_is_active == True).order_by(EventType.et_order).all()

    if request.method == 'POST':
        # Get form data
        club_id = request.form.get('club_id')  # Optional now
        title = request.form.get('title')
        location = request.form.get('location')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        event_type_id = request.form.get('event_type_id')
        max_players = request.form.get('max_players')
        registration_start = request.form.get('registration_start')
        registration_end = request.form.get('registration_end')
        
        # Validate required fields (club_id is now optional)
        if not all([title, location, event_date, event_time, event_type_id, max_players]):
            flash(translate('Please fill in all required fields!'), 'error')
            return render_template("create_event.html", user=current_user, clubs=authorized_clubs, event_types=event_types)
        
        # DEBUG: Show exactly what we received
        flash(f"DEBUG: event_date='{event_date}', event_time='{event_time}', reg_start='{registration_start}', reg_end='{registration_end}'", 'info')
        
        # Check club authorization only if club is selected
        if club_id:
            is_authorized = any(club.cl_id == int(club_id) for club in authorized_clubs)
            if not is_authorized:
                flash(translate('You are not authorized to create events for this club!'), 'error')
                return redirect(url_for('views.managementEvents'))

        # Validate event type exists and is active
        event_type = EventType.query.filter_by(et_id=int(event_type_id), et_is_active=True).first()
        if not event_type:
            flash(translate('Invalid event type selected!'), 'error')
            return render_template("create_event.html", user=current_user, clubs=authorized_clubs, event_types=event_types)

        try:
            # Parse date and time - try multiple formats
            event_date_parsed = None
            try:
                event_date_parsed = datetime.strptime(event_date, "%Y-%m-%d").date()
            except ValueError:
                try:
                    # Try DD/MM/YYYY format (European)
                    event_date_parsed = datetime.strptime(event_date, "%d/%m/%Y").date()
                except ValueError:
                    try:
                        # Try MM/DD/YYYY format (American)
                        event_date_parsed = datetime.strptime(event_date, "%m/%d/%Y").date()
                    except ValueError:
                        raise ValueError(f"Invalid event date format: '{event_date}'. Expected YYYY-MM-DD, DD/MM/YYYY or MM/DD/YYYY")
            
            if event_date_parsed is None:
                raise ValueError(f"Could not parse event_date: {event_date}")
                
            try:
                event_time_parsed = datetime.strptime(event_time, "%H:%M").time()
            except ValueError:
                raise ValueError(f"Invalid event time format: '{event_time}'. Expected HH:MM")
            
            # Parse registration dates if provided - handle multiple formats
            reg_start_utc = None
            reg_end_utc = None
            if registration_start:
                try:
                    reg_start_utc = datetime.strptime(registration_start, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
                except ValueError:
                    try:
                        # Try DD/MM/YYYY, HH:MM format
                        reg_start_utc = datetime.strptime(registration_start, "%d/%m/%Y, %H:%M").replace(tzinfo=timezone.utc)
                    except ValueError:
                        try:
                            # Try other common formats
                            reg_start_utc = datetime.strptime(registration_start, "%d/%m/%Y %H:%M").replace(tzinfo=timezone.utc)
                        except ValueError:
                            raise ValueError(f"Invalid registration start format: '{registration_start}'. Expected YYYY-MM-DDTHH:MM, DD/MM/YYYY, HH:MM or DD/MM/YYYY HH:MM")
            if registration_end:
                try:
                    reg_end_utc = datetime.strptime(registration_end, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
                except ValueError:
                    try:
                        # Try DD/MM/YYYY, HH:MM format
                        reg_end_utc = datetime.strptime(registration_end, "%d/%m/%Y, %H:%M").replace(tzinfo=timezone.utc)
                    except ValueError:
                        try:
                            # Try other common formats
                            reg_end_utc = datetime.strptime(registration_end, "%d/%m/%Y %H:%M").replace(tzinfo=timezone.utc)
                        except ValueError:
                            raise ValueError(f"Invalid registration end format: '{registration_end}'. Expected YYYY-MM-DDTHH:MM, DD/MM/YYYY, HH:MM or DD/MM/YYYY HH:MM")

            # Create new event
            new_event = Event(
                ev_title=title,
                ev_club_id=int(club_id) if club_id else None,  # Handle optional club
                ev_location=location,
                ev_date=event_date_parsed,
                ev_start_time=event_time_parsed,
                ev_type_id=int(event_type_id),
                ev_max_players=int(max_players),
                ev_registration_start=reg_start_utc,
                ev_registration_end=reg_end_utc,
                ev_status='announced',  # Start as announced
                ev_created_by_id=current_user.us_id
            )

            db.session.add(new_event)
            db.session.commit()

            flash(translate('Event created successfully! Now configure courts and game settings.'), 'success')
            return redirect(url_for('views.create_event_step2', event_id=new_event.ev_id))

        except ValueError as e:
            flash(f"Invalid date/time format! {str(e)}", 'error')
            return render_template("create_event.html", user=current_user, clubs=authorized_clubs, event_types=event_types)
        except Exception as e:
            db.session.rollback()
            flash(translate('Error creating event!'), 'error')
            return render_template("create_event.html", user=current_user, clubs=authorized_clubs, event_types=event_types)

    return render_template("create_event.html", user=current_user, clubs=authorized_clubs, event_types=event_types)


@views.route('/create_event_step2/<int:event_id>', methods=['GET'])
@login_required
def create_event_step2(event_id):
    """Step 2: Configure courts and game settings for event"""
    # Get the event
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == event.ev_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this event!'), 'error')
        return redirect(url_for('views.managementEvents'))
    
    # Get club and courts
    club = Club.query.get_or_404(event.ev_club_id)
    
    # Calculate number of courts needed (max_players / 4)
    courts_needed = event.ev_max_players // 4
    
    return render_template('create_event_step2.html', 
                           user=current_user, 
                           event=event, 
                           courts_needed=courts_needed,
                           club_name=club.cl_name)

@views.route('/create_event_step2/<int:event_id>', methods=['POST'])
@login_required
def process_event_step2(event_id):
    """Process step 2 and redirect to step 3"""
    # Get the event
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == event.ev_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this event!'), 'error')
        return redirect(url_for('views.managementEvents'))
    
    try:
        # Get court names and pairing type
        courts_needed = event.ev_max_players // 4
        court_names = []
        pairing_type = request.form.get('pairing_type')
        
        # Collect court names
        for i in range(courts_needed):
            court_name = request.form.get(f'court_name_{i}')
            if not court_name or not court_name.strip():
                flash(translate(f'Court name {i+1} is required!'), 'error')
                return redirect(url_for('views.create_event_step2', event_id=event_id))
            court_names.append(court_name.strip())
        
        # Validate pairing type
        valid_pairing_types = ['Random', 'Manual', 'L&R Random']
        if pairing_type not in valid_pairing_types:
            flash(translate('Invalid pairing type selected!'), 'error')
            return redirect(url_for('views.create_event_step2', event_id=event_id))
        
        # Store court names and pairing type
        # Clear any existing court assignments
        EventCourts.query.filter_by(evc_event_id=event.ev_id).delete()
        
        # Get or create courts with the specified names for this club
        for i, court_name in enumerate(court_names):
            # Try to find existing court with this name
            existing_court = Court.query.filter_by(
                ct_name=court_name, 
                ct_club_id=event.ev_club_id
            ).first()
            
            if existing_court:
                court = existing_court
            else:
                # Create new court if it doesn't exist
                court = Court(
                    ct_name=court_name,
                    ct_sport='Padel',  # Default to Padel
                    ct_club_id=event.ev_club_id
                )
                db.session.add(court)
                db.session.flush()  # Get the ID
            
            # Create EventCourts relationship
            event_court = EventCourts(
                evc_event_id=event.ev_id,
                evc_court_id=court.ct_id
            )
            db.session.add(event_court)
        
        # Store pairing type
        event.ev_pairing_type = pairing_type
        
        db.session.commit()
        
        # Redirect to step 3 for player registration
        return redirect(url_for('views.create_event_step3', event_id=event.ev_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error processing event configuration: {}').format(str(e)), 'error')
        return redirect(url_for('views.create_event_step2', event_id=event_id))

@views.route('/create_event_step3/<int:event_id>', methods=['GET'])
@login_required
def create_event_step3(event_id):
    """Step 3: Player registration based on pairing type"""
    # Get the event
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == event.ev_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this event!'), 'error')
        return redirect(url_for('views.managementEvents'))
    
    # Get club for display
    club = Club.query.get_or_404(event.ev_club_id)
    
    # Calculate variables needed for player registration UI
    max_players = event.ev_max_players
    pairing_type = event.ev_pairing_type or 'Random'
    
    # Calculate teams needed for Manual pairing
    teams_needed = max_players // 2 if pairing_type == 'Manual' else 0
    
    # Generate team letters (A, B, C, etc.)
    team_letters = [chr(65 + i) for i in range(teams_needed)]  # A, B, C...
    
    # Get existing player data for editing
    from .models import EventPlayerNames
    existing_players = EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).all()
    
    # Organize existing player data by type and position for easy template access
    player_data = {}
    if pairing_type == 'Random':
        player_data = {f'player_{p.epn_position_index}': p.epn_player_name 
                      for p in existing_players if p.epn_position_type == 'random'}
    elif pairing_type == 'Manual':
        for p in existing_players:
            if p.epn_position_type == 'team':
                key = f'team_{p.epn_team_identifier}_player{p.epn_team_position}'
                player_data[key] = p.epn_player_name
    elif pairing_type == 'L&R Random':
        for p in existing_players:
            if p.epn_position_type in ['left', 'right']:
                key = f'{p.epn_position_type}_player_{p.epn_position_index}'
                player_data[key] = p.epn_player_name
    
    return render_template('create_event_step3.html',
                           user=current_user,
                           event=event,
                           club_name=club.cl_name,
                           max_players=max_players,
                           pairing_type=pairing_type,
                           teams_needed=teams_needed,
                           team_letters=team_letters,
                           player_data=player_data)

@views.route('/complete_event_creation/<int:event_id>', methods=['POST'])
@login_required
def complete_event_creation(event_id):
    """Complete event creation with player registration (Step 3)"""
    # Get the event
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized for this club
    is_authorized = db.session.query(ClubAuthorization).filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == event.ev_club_id
    ).first() is not None
    
    if not is_authorized:
        flash(translate('You are not authorized to edit this event!'), 'error')
        return redirect(url_for('views.managementEvents'))
    
    try:
        # Import the new model
        from .models import EventPlayerNames
        
        # Clear any existing player names and registrations for this event
        EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).delete()
        EventRegistration.query.filter_by(er_event_id=event.ev_id).delete()
        
        pairing_type = event.ev_pairing_type or 'Random'
        max_players = event.ev_max_players
        players_registered = 0
        
        def get_or_create_user(player_name):
            """Get existing user or create new player user"""
            if not player_name or not player_name.strip():
                return None
                
            # Try to find existing user by name (case insensitive)
            user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
            
            if not user:
                # Create new user as player
                user = Users(
                    us_name=player_name.strip(),
                    us_email=f"{player_name.strip().lower().replace(' ', '.')}@temp.event",
                    us_telephone=f"temp_{player_name.strip().lower().replace(' ', '')}",
                    us_is_player=True,
                    us_is_active=True
                )
                db.session.add(user)
                db.session.flush()  # Get the user ID
            
            return user
        
        if pairing_type == 'Random':
            # Single column of players
            for i in range(max_players):
                player_name = request.form.get(f'player_{i}')
                if player_name and player_name.strip():
                    # Create/get user
                    user = get_or_create_user(player_name.strip())
                    if user:
                        # Store player name with position information
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=player_name.strip(),
                            epn_position_type='random',
                            epn_position_index=i,
                            epn_created_by_id=current_user.us_id
                        )
                        db.session.add(player_record)
                        
                        # Create event registration
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                    
        elif pairing_type == 'Manual':
            # Team-based registration
            teams_needed = max_players // 2
            for team_idx in range(teams_needed):
                team_letter = chr(65 + team_idx)  # A, B, C...
                player1_name = request.form.get(f'team_{team_letter}_player1')
                player2_name = request.form.get(f'team_{team_letter}_player2')
                
                for pos, player_name in enumerate([player1_name, player2_name], 1):
                    if player_name and player_name.strip():
                        user = get_or_create_user(player_name.strip())
                        if user:
                            player_record = EventPlayerNames(
                                epn_event_id=event.ev_id,
                                epn_player_name=player_name.strip(),
                                epn_position_type='team',
                                epn_position_index=team_idx,
                                epn_team_identifier=team_letter,
                                epn_team_position=pos,
                                epn_created_by_id=current_user.us_id
                            )
                            db.session.add(player_record)
                            
                            registration = EventRegistration(
                                er_event_id=event.ev_id,
                                er_player_id=user.us_id,
                                er_registered_by_id=current_user.us_id,
                                er_is_substitute=False
                            )
                            db.session.add(registration)
                            players_registered += 1
                    
        elif pairing_type == 'L&R Random':
            # Left and Right columns
            left_players = max_players // 2
            right_players = max_players // 2
            
            for i in range(left_players):
                left_player = request.form.get(f'left_player_{i}')
                if left_player and left_player.strip():
                    user = get_or_create_user(left_player.strip())
                    if user:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=left_player.strip(),
                            epn_position_type='left',
                            epn_position_index=i,
                            epn_created_by_id=current_user.us_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                        
            for i in range(right_players):
                right_player = request.form.get(f'right_player_{i}')
                if right_player and right_player.strip():
                    user = get_or_create_user(right_player.strip())
                    if user:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=right_player.strip(),
                            epn_position_type='right',
                            epn_position_index=i,
                            epn_created_by_id=current_user.us_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
        
        db.session.commit()
        
        flash(translate('Event created successfully with {} players registered!').format(players_registered), 'success')
        return redirect(url_for('views.managementEvents'))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error completing event creation: {}').format(str(e)), 'error')
        return redirect(url_for('views.create_event_step3', event_id=event_id))


@views.route('/event/<int:event_id>', methods=['GET'])
def detail_event(event_id):
    """Event detail page"""
    # Get the event with registered players loaded
    event = Event.query.options(db.joinedload(Event.registrations)).get_or_404(event_id)
    
    # Get the club information
    club = Club.query.get_or_404(event.ev_club_id)
    
    # Get event registrations with user info
    registrations = EventRegistration.query.filter_by(er_event_id=event_id).all()
    
    # Separate regular players and substitutes
    regular_players = []
    substitute_players = []
    
    for reg in registrations:
        user = Users.query.get(reg.er_player_id)
        reg_data = {
            'user': user,
            'registration': reg,
            'registered_at': reg.er_registered_at
        }
        
        if reg.er_is_substitute:
            substitute_players.append(reg_data)
        else:
            regular_players.append(reg_data)
    
    # If no regular players from registrations, check EventPlayerNames (after player substitution)
    if not regular_players:
        event_player_names = EventPlayerNames.query.filter_by(epn_event_id=event_id).all()
        for player_name in event_player_names:
            # Try to find matching user, or create a display entry for named player
            user = Users.query.filter(Users.us_name.ilike(player_name.epn_player_name.strip())).first()
            
            # Create a fake user object for display if no real user found
            if not user:
                class NamedPlayerDisplay:
                    def __init__(self, name):
                        self.us_name = name
                        self.us_id = None
                user = NamedPlayerDisplay(player_name.epn_player_name)
            
            reg_data = {
                'user': user,
                'registration': None,  # No actual registration record
                'registered_at': player_name.epn_created_at
            }
            regular_players.append(reg_data)
    
    # Check if current user can register
    can_register = False
    user_registration = None
    if current_user.is_authenticated:
        user_registration = EventRegistration.query.filter_by(
            er_event_id=event_id,
            er_player_id=current_user.us_id
        ).first()
        
        # User can register if:
        # 1. Not already registered
        # 2. Event is open for registration
        # 3. There's space available (or can register as substitute)
        can_register = (
            not user_registration and
            event.is_registration_open() and
            (len(regular_players) < event.ev_max_players or True)  # Allow substitute registration
        )
    
    # Get event games if any (now using unified Game table)
    # Temporarily handle missing gm_idEvent column
    try:
        event_games = Game.query.filter_by(gm_idEvent=event_id).all()
    except Exception as e:
        # Handle case where gm_idEvent column doesn't exist yet
        event_games = []
    
    # Get player names for games that use EventPlayerNames (named players)
    game_player_names = {}
    if event_games:
        # Get all EventPlayerNames for this event
        event_player_names = EventPlayerNames.query.filter_by(epn_event_id=event_id).all()
        
        # Create a mapping of player names by their position in pairing
        player_list = []
        if event.ev_pairing_type == 'Manual':
            # For manual pairing, sort by team and position
            sorted_players = sorted(event_player_names, 
                                  key=lambda x: (x.epn_team_identifier, x.epn_team_position))
            player_list = [p.epn_player_name for p in sorted_players]
        elif event.ev_pairing_type == 'L&R Random':
            # For L&R Random, group by left/right and shuffle within groups
            left_players = [p for p in event_player_names if p.epn_position_type == 'left']
            right_players = [p for p in event_player_names if p.epn_position_type == 'right']
            
            left_players.sort(key=lambda x: x.epn_position_index)
            right_players.sort(key=lambda x: x.epn_position_index)
            
            # Interleave left and right players
            for i in range(min(len(left_players), len(right_players))):
                player_list.append(left_players[i].epn_player_name)
                player_list.append(right_players[i].epn_player_name)
            # Add remaining players
            player_list.extend([p.epn_player_name for p in left_players[min(len(left_players), len(right_players)):]])
            player_list.extend([p.epn_player_name for p in right_players[min(len(left_players), len(right_players)):]])
        else:  # Random
            # For random pairing, sort by position index
            sorted_players = sorted(event_player_names, key=lambda x: x.epn_position_index)
            player_list = [p.epn_player_name for p in sorted_players]
        
        # Map player names to games (4 players per game)
        for i, game in enumerate(event_games):
            game_index = i
            if game_index * 4 + 3 < len(player_list):
                game_player_names[game.gm_id] = {
                    'A1': player_list[game_index * 4],
                    'A2': player_list[game_index * 4 + 1],
                    'B1': player_list[game_index * 4 + 2],
                    'B2': player_list[game_index * 4 + 3]
                }
    
    # Get event classification if event is completed
    classifications = []
    if event.ev_status == 'completed':
        classifications = EventClassification.query.filter_by(ec_event_id=event_id).order_by(EventClassification.ec_position).all()
    
    # Check if user can delete/hide this event
    can_delete = False
    delete_message = ""
    user_is_authorized = False
    
    if current_user.is_authenticated:
        # Check if user is authorized to manage this event
        if current_user.us_is_superuser == 1:
            user_is_authorized = True
        else:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            user_is_authorized = authorization is not None
            
        if user_is_authorized:
            can_delete, delete_message = can_delete_event(event_id)
    
    return render_template("event_detail.html", 
                         user=current_user, 
                         event=event,
                         club=club,
                         regular_players=regular_players,
                         substitute_players=substitute_players,
                         can_register=can_register,
                         user_registration=user_registration,
                         event_games=event_games,
                         game_player_names=game_player_names,
                         classifications=classifications,
                         can_delete=can_delete,
                         delete_message=delete_message,
                         user_is_authorized=user_is_authorized)


@views.route('/register_event/<int:event_id>', methods=['POST'])
@login_required
def register_event(event_id):
    """Register current user for an event"""
    event = Event.query.get_or_404(event_id)
    
    # Check if registration is open
    if not event.is_registration_open():
        flash(translate('Registration for this event is not currently open!'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # Check if user is already registered
    existing_reg = EventRegistration.query.filter_by(
        er_event_id=event_id,
        er_player_id=current_user.us_id
    ).first()
    
    if existing_reg:
        flash(translate('You are already registered for this event!'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # Check if there's space available
    current_registrations = EventRegistration.query.filter_by(
        er_event_id=event_id,
        er_is_substitute=False
    ).count()
    
    is_substitute = current_registrations >= event.ev_max_players
    
    try:
        # Create registration
        registration = EventRegistration(
            er_event_id=event_id,
            er_player_id=current_user.us_id,
            er_is_substitute=is_substitute,
            er_registered_at=datetime.now(timezone.utc)
        )
        
        db.session.add(registration)
        db.session.commit()
        
        if is_substitute:
            flash(translate('You have been registered as a substitute!'), 'success')
        else:
            flash(translate('You have been registered for the event!'), 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(translate('Error registering for event!'), 'error')
    
    return redirect(url_for('views.detail_event', event_id=event_id))


@views.route('/unregister_event/<int:event_id>', methods=['POST'])
@login_required
def unregister_event(event_id):
    """Unregister current user from an event"""
    event = Event.query.get_or_404(event_id)
    
    # Find user's registration
    registration = EventRegistration.query.filter_by(
        er_event_id=event_id,
        er_player_id=current_user.us_id
    ).first()
    
    if not registration:
        flash(translate('You are not registered for this event!'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # Check if unregistration is allowed (e.g., not too close to event date)
    event_datetime = datetime.combine(event.ev_date, event.ev_start_time).replace(tzinfo=timezone.utc)
    time_until_event = event_datetime - datetime.now(timezone.utc)
    if time_until_event.total_seconds() < 3600:  # Less than 1 hour
        flash(translate('Cannot unregister - event starts soon!'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    try:
        # Remove registration
        db.session.delete(registration)
        
        # If this was a regular player, promote a substitute if available
        if not registration.er_is_substitute:
            substitute = EventRegistration.query.filter_by(
                er_event_id=event_id,
                er_is_substitute=True
            ).order_by(EventRegistration.er_registered_at).first()
            
            if substitute:
                substitute.er_is_substitute = False
                flash(translate('You have been unregistered. A substitute has been promoted!'), 'success')
            else:
                flash(translate('You have been unregistered from the event!'), 'success')
        else:
            flash(translate('You have been unregistered from the event!'), 'success')
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error unregistering from event!'), 'error')
    
    return redirect(url_for('views.detail_event', event_id=event_id))


@views.route('/create_event_games/<int:event_id>', methods=['POST'])
@login_required
def create_event_games(event_id):
    """Create the first round of games for a Mexican event"""
    try:
        from random import shuffle
        from datetime import datetime, timedelta
        from .models import Game, EventCourts, EventRegistration, Users, ClubAuthorization, Event
        
        event = Event.query.get_or_404(event_id)
        
        # Check authorization
        if current_user.us_is_superuser != 1:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                flash(translate('You are not authorized to create games for this event'), 'error')
                return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Validate event type
        if event.ev_type != 'Mexicano':
            flash(translate('Game creation is currently only supported for Mexicano events'), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Check if games already exist
        existing_games = Game.query.filter_by(gm_idEvent=event_id).count()
        if existing_games > 0:
            flash(translate('Games already exist for this event'), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Get regular players (not substitutes) in registration order
        registrations = EventRegistration.query.filter_by(
            er_event_id=event_id, 
            er_is_substitute=False
        ).order_by(EventRegistration.er_registered_at).all()
        
        regular_players = []
        for reg in registrations:
            user = Users.query.get(reg.er_player_id)
            if user:
                regular_players.append(user)
        
        # Check if we have enough players
        if len(regular_players) < event.ev_max_players:
            flash(translate('Not enough players to create games. Need {} players, have {}').format(
                event.ev_max_players, len(regular_players)), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Get event courts
        event_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
        if not event_courts:
            flash(translate('No courts assigned to this event'), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Calculate number of games (4 players per game for Mexicano)
        num_games = event.ev_max_players // 4
        
        if len(event_courts) < num_games:
            flash(translate('Not enough courts for games. Need {} courts, have {}').format(
                num_games, len(event_courts)), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Create player pairings based on pairing type
        player_pairs = create_player_pairs(regular_players[:event.ev_max_players], event.ev_pairing_type, event_id)
        
        # Create games
        games_created = 0
        for i in range(num_games):
            if i * 4 + 3 < len(player_pairs):
                # Get court for this game
                court = event_courts[i].court
                
                # Calculate game times
                start_time = event.ev_start_time
                end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=20)).time()
                
                # Create game
                game = Game(
                    gm_idEvent=event_id,
                    gm_idLeague=None,  # Explicitly set to None
                    gm_idGameDay=None,  # Explicitly set to None
                    gm_date=event.ev_date,
                    gm_timeStart=start_time,
                    gm_timeEnd=end_time,
                    gm_court=court.ct_id,
                    gm_idPlayer_A1=player_pairs[i * 4].us_id,
                    gm_idPlayer_A2=player_pairs[i * 4 + 1].us_id,
                    gm_idPlayer_B1=player_pairs[i * 4 + 2].us_id,
                    gm_idPlayer_B2=player_pairs[i * 4 + 3].us_id,
                    gm_teamA=f"Team A{i+1}",
                    gm_teamB=f"Team B{i+1}"
                )
                
                db.session.add(game)
                games_created += 1
        
        db.session.commit()
        
        flash(translate('Successfully created {} games for the first round!').format(games_created), 'success')
        return redirect(url_for('views.detail_event', event_id=event_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error creating games: {}').format(str(e)), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))


def create_player_pairs(players, pairing_type, event_id=None):
    """Create player pairs based on pairing type"""
    from random import shuffle
    
    if pairing_type == 'Random':
        # Completely random pairing
        shuffled_players = players.copy()
        shuffle(shuffled_players)
        return shuffled_players
        
    elif pairing_type == 'Manual':
        # Manual pairing: use registration order (1&2 vs 3&4, 5&6 vs 7&8, etc.)
        return players  # Keep original order
        
    elif pairing_type == 'L&R Random':
        # Get players from left and right sides based on EventPlayerNames position_type
        from .models import EventPlayerNames
        
        left_players = []
        right_players = []
        
        for player in players:
            # Find this player's position type from EventPlayerNames
            player_name_record = EventPlayerNames.query.filter_by(
                epn_event_id=event_id,
                epn_player_name=player.us_name
            ).first()
            
            if player_name_record and player_name_record.epn_position_type == 'left':
                left_players.append(player)
            elif player_name_record and player_name_record.epn_position_type == 'right':
                right_players.append(player)
            else:
                # If not found in position types, add to right players as fallback
                right_players.append(player)
        
        # Shuffle each side separately
        shuffle(left_players)
        shuffle(right_players)
        
        # Interleave left and right players for team formation
        paired_players = []
        min_length = min(len(left_players), len(right_players))
        for i in range(min_length):
            paired_players.append(left_players[i])
            paired_players.append(right_players[i])
        
        # Add any remaining players
        paired_players.extend(left_players[min_length:])
        paired_players.extend(right_players[min_length:])
        
        return paired_players
    
    else:
        # Default to random if unknown type
        shuffled_players = players.copy()
        shuffle(shuffled_players)
        return shuffled_players


@views.route('/submitResultsEvent/<int:event_id>', methods=['GET', 'POST'])
@login_required
def submitResultsEvent(event_id):
    """Submit results for event games and handle Mexican round generation"""
    from .tools import func_calculateEventClassification, func_createEventMexicanRound, func_validateMexicanGameResult
    
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to submit results for this event'), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
    
    if request.method == 'POST':
        try:
            # Get all games for this event
            event_games = Game.query.filter_by(gm_idEvent=event_id).all()
            
            # Process each game result
            for game in event_games:
                result_a_key = f"resultGameA{game.gm_id}"
                result_b_key = f"resultGameB{game.gm_id}"
                
                result_a = request.form.get(result_a_key)
                result_b = request.form.get(result_b_key)
                
                if result_a is not None and result_b is not None:
                    try:
                        result_a = int(result_a) if result_a else 0
                        result_b = int(result_b) if result_b else 0
                        
                        # Validate Mexican game result if applicable
                        if event.is_mexicano:
                            is_valid, error_msg = func_validateMexicanGameResult(event_id, result_a, result_b)
                            if not is_valid:
                                flash(translate('Invalid result for game {}: {}').format(game.gm_id, error_msg), 'error')
                                return redirect(url_for('views.detail_event', event_id=event_id))
                        
                        # Update game results
                        game.gm_result_A = result_a
                        game.gm_result_B = result_b
                        
                    except ValueError:
                        flash(translate('Invalid result format for game {}').format(game.gm_id), 'error')
                        return redirect(url_for('views.detail_event', event_id=event_id))
            
            db.session.commit()
            
            # Calculate event classification
            func_calculateEventClassification(event_id)
            
            # For Mexican events, check if we need to generate next round
            if event.is_mexicano:
                # Check if all current games are completed (no more 0-0 results)
                remaining_zero_games = Game.query.filter_by(
                    gm_idEvent=event_id,
                    gm_result_A=0,
                    gm_result_B=0
                ).count()
                
                if remaining_zero_games == 0:
                    # Delete completed games with 0-0 results (if any exist)
                    Game.query.filter_by(
                        gm_idEvent=event_id,
                        gm_result_A=0,
                        gm_result_B=0
                    ).delete()
                    db.session.commit()
                    
                    # Generate next round
                    success, message = func_createEventMexicanRound(event_id)
                    if success:
                        flash(translate('Results submitted and next round created: {}').format(message), 'success')
                    else:
                        # Check if this is because tournament is complete
                        total_players = EventRegistration.query.filter_by(
                            er_event_id=event_id,
                            er_is_substitute=False
                        ).count()
                        
                        if total_players > 0:
                            # Update event status to completed
                            event.ev_status = 'event_ended'
                            db.session.commit()
                            flash(translate('Tournament completed! Final results are available.'), 'success')
                        else:
                            flash(translate('Cannot create next round: {}').format(message), 'warning')
                else:
                    flash(translate('Results submitted successfully!'), 'success')
            else:
                flash(translate('Results submitted successfully!'), 'success')
                
        except Exception as e:
            db.session.rollback()
            flash(translate('Error submitting results: {}').format(str(e)), 'error')
            
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # GET request - return to event detail page
    return redirect(url_for('views.detail_event', event_id=event_id))


@views.route('/create_mexican_config/<int:event_id>', methods=['GET', 'POST'])
@login_required
def create_mexican_config(event_id):
    """Configure Mexican format settings for an event"""
    from .models import MexicanConfig
    
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to configure this event'), 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
    
    if not event.is_mexicano:
        flash(translate('Configuration only available for Mexican format events'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # Check if config already exists
    existing_config = MexicanConfig.query.filter_by(mc_event_id=event_id).first()
    if existing_config:
        flash(translate('Mexican configuration already exists for this event'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    if request.method == 'POST':
        try:
            # Create Mexican configuration
            config = MexicanConfig(
                mc_event_id=event_id,
                mc_draws_allowed=request.form.get('draws_allowed') == 'on',
                mc_max_points_per_game=request.form.get('max_points', '16'),
                mc_draw_points=int(request.form.get('draw_points', 1)),
                mc_win_points=int(request.form.get('win_points', 3)),
                mc_loss_points=int(request.form.get('loss_points', 0))
            )
            
            db.session.add(config)
            db.session.commit()
            
            flash(translate('Mexican configuration saved successfully'), 'success')
            return redirect(url_for('views.detail_event', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(translate('Error saving configuration: {}').format(str(e)), 'error')
    
    return render_template('create_mexican_config.html', event=event)


@views.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
@login_required  
def edit_event(event_id):
    """Step 1: Edit basic event information"""
    return edit_event_step1(event_id)

@views.route('/edit_event_step1/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event_step1(event_id):
    """Step 1: Edit basic event information"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization (superuser or club authorization)
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    # Get authorized clubs for the dropdown
    if current_user.us_is_superuser == 1:
        authorized_clubs = Club.query.filter_by(cl_active=True).all()
    else:
        authorized_clubs = db.session.query(Club).join(
            ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id
        ).filter(
            ClubAuthorization.ca_user_id == current_user.us_id,
            Club.cl_active == True
        ).all()

    if request.method == 'POST':
        try:
            # Update basic event information
            event.ev_title = request.form['title']
            event.ev_description = request.form.get('description', '')
            event.ev_location = request.form['location']
            event.ev_club_id = request.form['club_id']
            
            # Parse dates and times
            event.ev_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            event.ev_start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
            
            end_time_str = request.form.get('end_time')
            if end_time_str:
                event.ev_end_time = datetime.strptime(end_time_str, '%H:%M').time()
            else:
                event.ev_end_time = None
                
            # Parse registration dates
            reg_start_str = request.form.get('registration_start')
            if reg_start_str:
                event.ev_registration_start = datetime.strptime(reg_start_str, '%Y-%m-%d').date()
            
            reg_end_str = request.form.get('registration_end')
            if reg_end_str:
                event.ev_registration_end = datetime.strptime(reg_end_str, '%Y-%m-%d').date()
            
            event.ev_status = request.form['status']
            
            db.session.commit()
            flash(translate('Basic event information updated!'), 'success')
            return redirect(url_for('views.edit_event_step2', event_id=event_id))

        except ValueError as e:
            flash(translate('Invalid date/time format!'), 'error')
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating event: {}').format(str(e)), 'error')

    return render_template("edit_event_step1.html", user=current_user, event=event, clubs=authorized_clubs)

@views.route('/edit_event_step2/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event_step2(event_id):
    """Step 2: Edit court configuration and pairing type"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    # Get club courts for this event
    club = Club.query.get_or_404(event.ev_club_id)
    all_courts = Court.query.filter_by(ct_club_id=club.cl_id).all()
    
    # Get existing event courts
    existing_event_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
    
    if request.method == 'POST':
        try:
            # Update event type and pairing
            event_type_id = request.form.get('event_type_id')
            if event_type_id:
                # Validate event type exists and is active
                event_type = EventType.query.filter_by(et_id=int(event_type_id), et_is_active=True).first()
                if not event_type:
                    flash(translate('Invalid event type selected!'), 'error')
                    return render_template("edit_event_step2.html", user=current_user, event=event, 
                                          club=club, courts=all_courts, existing_event_courts=existing_event_courts,
                                          event_types=EventType.query.filter(EventType.et_is_active == True).all())
                event.ev_type_id = int(event_type_id)
                
            event.ev_pairing_type = request.form['pairing_type']
            event.ev_max_players = int(request.form['max_players'])
            
            # Clear existing event courts
            EventCourts.query.filter_by(evc_event_id=event_id).delete()
            
            # Add selected courts
            court_count = int(request.form.get('court_count', 1))
            for i in range(court_count):
                court_id = request.form.get(f'court_{i}')
                
                if court_id:
                    event_court = EventCourts(
                        evc_event_id=event_id,
                        evc_court_id=court_id
                    )
                    db.session.add(event_court)
            
            db.session.commit()
            flash(translate('Court configuration updated!'), 'success')
            return redirect(url_for('views.edit_event_step3', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating court configuration: {}').format(str(e)), 'error')
    
    # Get available event types for the form
    event_types = EventType.query.filter(EventType.et_is_active == True).order_by(EventType.et_order).all()
    
    return render_template("edit_event_step2.html", user=current_user, event=event, 
                          club=club, courts=all_courts, existing_event_courts=existing_event_courts,
                          event_types=event_types)


def update_event_players(event_id):
    """Update event players with user creation and registration logic"""
    from .models import EventPlayerNames
    
    event = Event.query.get_or_404(event_id)
    
    try:
        # Clear existing player names and registrations for this event
        EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).delete()
        EventRegistration.query.filter_by(er_event_id=event.ev_id).delete()
        
        pairing_type = event.ev_pairing_type or 'Random'
        max_players = event.ev_max_players
        players_registered = 0
        
        def get_or_create_user(player_name):
            """Get existing user or create new player user"""
            if not player_name or not player_name.strip():
                return None
                
            # Try to find existing user by name (case insensitive)
            user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
            
            if not user:
                # Create new user as player
                user = Users(
                    us_name=player_name.strip(),
                    us_email=f"{player_name.strip().lower().replace(' ', '.')}@temp.event",
                    us_telephone=f"temp_{player_name.strip().lower().replace(' ', '')}",
                    us_is_player=True,
                    us_is_active=True
                )
                db.session.add(user)
                db.session.flush()  # Get the user ID
            
            return user
        
        if pairing_type == 'Random':
            for i in range(max_players):
                player_name = request.form.get(f'player_{i}')
                if player_name and player_name.strip():
                    # Create/get user
                    user = get_or_create_user(player_name.strip())
                    if user:
                        # Store player name
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=player_name.strip(),
                            epn_position_type='random',
                            epn_position_index=i,
                            epn_created_by_id=current_user.us_id
                        )
                        db.session.add(player_record)
                        
                        # Create event registration
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                        
        elif pairing_type == 'Manual':
            teams_needed = max_players // 2
            for team_idx in range(teams_needed):
                team_letter = chr(65 + team_idx)  # A, B, C...
                player1_name = request.form.get(f'team_{team_letter}_player1')
                player2_name = request.form.get(f'team_{team_letter}_player2')
                
                for pos, player_name in enumerate([player1_name, player2_name], 1):
                    if player_name and player_name.strip():
                        user = get_or_create_user(player_name.strip())
                        if user:
                            player_record = EventPlayerNames(
                                epn_event_id=event.ev_id,
                                epn_player_name=player_name.strip(),
                                epn_position_type='team',
                                epn_position_index=team_idx,
                                epn_team_identifier=team_letter,
                                epn_team_position=pos,
                                epn_created_by_id=current_user.us_id
                            )
                            db.session.add(player_record)
                            
                            registration = EventRegistration(
                                er_event_id=event.ev_id,
                                er_player_id=user.us_id,
                                er_registered_by_id=current_user.us_id,
                                er_is_substitute=False
                            )
                            db.session.add(registration)
                            players_registered += 1
                            
        elif pairing_type == 'L&R Random':
            left_players = max_players // 2
            right_players = max_players // 2
            
            for i in range(left_players):
                left_player = request.form.get(f'left_player_{i}')
                if left_player and left_player.strip():
                    user = get_or_create_user(left_player.strip())
                    if user:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=left_player.strip(),
                            epn_position_type='left',
                            epn_position_index=i,
                            epn_created_by_id=current_user.us_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                        
            for i in range(right_players):
                right_player = request.form.get(f'right_player_{i}')
                if right_player and right_player.strip():
                    user = get_or_create_user(right_player.strip())
                    if user:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=right_player.strip(),
                            epn_position_type='right',
                            epn_position_index=i,
                            epn_created_by_id=current_user.us_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
        
        db.session.commit()
        flash(translate('Event players updated successfully! {} players registered.').format(players_registered), 'success')
        return redirect(url_for('views.detail_event', event_id=event_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error updating event players: {}').format(str(e)), 'error')
        return redirect(url_for('views.edit_event_step3', event_id=event_id))

# Delete/Hide League Routes
def can_delete_league(league_id):
    """
    Check if a league can be safely deleted by verifying no dependencies exist.
    Returns (can_delete: bool, message: str)
    """
    try:
        from flask import has_request_context
        
        # Check for GameDays
        gamedays = GameDay.query.filter_by(gd_idLeague=league_id).count()
        if gamedays > 0:
            message = 'Cannot delete league: {} game days exist'.format(gamedays)
            return False, translate(message) if has_request_context() else message
        
        message = 'League can be safely deleted'
        return True, translate(message) if has_request_context() else message
        
    except Exception as e:
        message = 'Error checking league dependencies: {}'.format(str(e))
        return False, translate(message) if has_request_context() else message


@views.route('/edit_event_step3/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event_step3(event_id):
    """Step 3: Edit player registration"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    # Get existing player data for pre-population
    from .models import EventPlayerNames
    existing_players = EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).all()
    
    # Organize player data by position type
    player_data = {
        'random': [],
        'team': {},
        'left': [],
        'right': []
    }
    
    for player in existing_players:
        if player.epn_position_type == 'random':
            # Ensure list is long enough
            while len(player_data['random']) <= player.epn_position_index:
                player_data['random'].append('')
            player_data['random'][player.epn_position_index] = player.epn_player_name
            
        elif player.epn_position_type == 'team':
            team_id = player.epn_team_identifier
            if team_id not in player_data['team']:
                player_data['team'][team_id] = {'player1': '', 'player2': ''}
            
            if player.epn_team_position == 1:
                player_data['team'][team_id]['player1'] = player.epn_player_name
            elif player.epn_team_position == 2:
                player_data['team'][team_id]['player2'] = player.epn_player_name
                
        elif player.epn_position_type == 'left':
            while len(player_data['left']) <= player.epn_position_index:
                player_data['left'].append('')
            player_data['left'][player.epn_position_index] = player.epn_player_name
            
        elif player.epn_position_type == 'right':
            while len(player_data['right']) <= player.epn_position_index:
                player_data['right'].append('')
            player_data['right'][player.epn_position_index] = player.epn_player_name
    
    if request.method == 'POST':
        # Process using the existing complete_event_creation logic but for editing
        return update_event_players(event_id)
    
    return render_template("edit_event_step3.html", user=current_user, event=event, 
                          player_data=player_data)


@views.route('/edit_event_players/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event_players(event_id):
    """Edit player list for an event with existing games (substitute players)"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    # Check if event has games and if they haven't been played yet
    event_games = Game.query.filter_by(gm_idEvent=event_id).all()
    if not event_games:
        flash(translate('No games exist for this event yet'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # Check if any games have been played (have scores)
    games_played = any(game.gm_result_A is not None or game.gm_result_B is not None for game in event_games)
    if games_played:
        flash(translate('Cannot substitute players - some games have already been played'), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))
    
    # Get current registered players
    current_players_data = []
    
    # Get from EventPlayerNames table if it exists (from step 3 creation)
    existing_players = EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).all()
    
    if existing_players:
        # Build player data from EventPlayerNames
        for player in existing_players:
            player_info = {'name': player.epn_player_name}
            if player.epn_position_type == 'team':
                player_info['team'] = player.epn_team_identifier
                player_info['position'] = player.epn_team_position
            elif player.epn_position_type in ['left', 'right']:
                player_info['lr_preference'] = player.epn_position_type
            current_players_data.append(player_info)
    else:
        # Fallback: Get from EventRegistration table
        registrations = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=False).all()
        for reg in registrations:
            current_players_data.append({'name': reg.player.us_name})
    
    if request.method == 'POST':
        # Handle the form submission to update players and recreate games
        try:
            # Get form data
            player_count = int(request.form.get('player_count'))
            pairing_type = request.form.get('pairing_type')
            
            # Validate player count
            if player_count < 4 or player_count > event.ev_max_players:
                flash(translate('Invalid number of players'), 'error')
                return redirect(url_for('views.edit_event_players', event_id=event_id))
            
            # Get player names
            player_names = []
            for i in range(player_count):
                name = request.form.get(f'player_{i}', '').strip()
                if not name:
                    flash(translate('All player names are required'), 'error')
                    return redirect(url_for('views.edit_event_players', event_id=event_id))
                player_names.append(name)
            
            # Update event pairing type if changed
            event.ev_pairing_type = pairing_type
            
            # Delete existing games
            Game.query.filter_by(gm_idEvent=event_id).delete()
            
            # Delete existing EventPlayerNames (but keep EventRegistration records)
            EventPlayerNames.query.filter_by(epn_event_id=event_id).delete()
            
            # Create new player records based on pairing type
            if pairing_type == 'Manual':
                # Handle manual team assignments
                for i, name in enumerate(player_names):
                    team = request.form.get(f'team_{i}')
                    position = int(request.form.get(f'position_{i}'))
                    
                    player_name = EventPlayerNames(
                        epn_event_id=event_id,
                        epn_player_name=name,
                        epn_position_type='team',
                        epn_position_index=i,
                        epn_team_identifier=team,
                        epn_team_position=position,
                        epn_created_by_id=current_user.us_id
                    )
                    db.session.add(player_name)
                    
            elif pairing_type == 'L&R Random':
                # Handle L&R preferences
                for i, name in enumerate(player_names):
                    lr_preference = request.form.get(f'lr_{i}')
                    
                    player_name = EventPlayerNames(
                        epn_event_id=event_id,
                        epn_player_name=name,
                        epn_position_type=lr_preference,  # 'left' or 'right'
                        epn_position_index=len([p for p in player_names[:i] if request.form.get(f'lr_{player_names.index(p)}') == lr_preference]),
                        epn_created_by_id=current_user.us_id
                    )
                    db.session.add(player_name)
                    
            else:  # Random
                # Handle random pairing
                for i, name in enumerate(player_names):
                    player_name = EventPlayerNames(
                        epn_event_id=event_id,
                        epn_player_name=name,
                        epn_position_type='random',
                        epn_position_index=i,
                        epn_created_by_id=current_user.us_id
                    )
                    db.session.add(player_name)
            
            # Commit the changes
            db.session.commit()
            
            # Recreate games using existing logic
            # Get event courts
            event_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
            if not event_courts:
                flash(translate('No courts assigned to this event'), 'error')
                return redirect(url_for('views.edit_event_players', event_id=event_id))
            
            # Calculate number of games (4 players per game for Mexicano)
            num_games = event.ev_max_players // 4
            
            if len(event_courts) < num_games:
                flash(translate('Not enough courts for games. Need {} courts, have {}').format(
                    num_games, len(event_courts)), 'error')
                return redirect(url_for('views.edit_event_players', event_id=event_id))
            
            # Get EventPlayerNames in position order for game creation
            # These are now sorted by position_index which is the correct order for games
            event_player_names = EventPlayerNames.query.filter_by(epn_event_id=event_id).order_by(EventPlayerNames.epn_position_index).all()
            
            # Create games based on EventPlayerNames order (4 players per game)
            games_created = 0
            for i in range(num_games):
                game_start_idx = i * 4
                if game_start_idx + 3 < len(event_player_names):
                    # Get court for this game
                    court = event_courts[i].court
                    
                    # Calculate game times
                    start_time = event.ev_start_time
                    from datetime import datetime, timedelta
                    end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=20)).time()
                    
                    # Get players for this game from EventPlayerNames (4 consecutive players)
                    game_players = event_player_names[game_start_idx:game_start_idx + 4]
                    
                    # Try to find real user IDs for players, or use None
                    player_ids = []
                    for player_name_record in game_players:
                        user = Users.query.filter(Users.us_name.ilike(player_name_record.epn_player_name.strip())).first()
                        player_ids.append(user.us_id if user else None)
                    
                    # Create game with correct player assignment
                    game = Game(
                        gm_idEvent=event_id,
                        gm_idLeague=None,  
                        gm_idGameDay=None,  
                        gm_date=event.ev_date,
                        gm_timeStart=start_time,
                        gm_timeEnd=end_time,
                        gm_court=court.ct_id,
                        gm_idPlayer_A1=player_ids[0],  # First player
                        gm_idPlayer_A2=player_ids[1],  # Second player
                        gm_idPlayer_B1=player_ids[2],  # Third player
                        gm_idPlayer_B2=player_ids[3],  # Fourth player
                        gm_teamA=f"Team A{i+1}",
                        gm_teamB=f"Team B{i+1}"
                    )
                    
                    db.session.add(game)
                    games_created += 1
            
            # Commit all changes
            db.session.commit()
            
            flash(translate('Player list updated and {} games recreated successfully').format(games_created), 'success')
            
            return redirect(url_for('views.detail_event', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f"{translate('Error updating players')}: {str(e)}", 'error')
            return redirect(url_for('views.edit_event_players', event_id=event_id))
    
    return render_template("edit_event_players.html", user=current_user, event=event, 
                          current_players=current_players_data)


def can_delete_league(league_id):
    """
    Check if a league can be safely deleted by verifying no dependencies exist.
    Returns (can_delete: bool, message: str)
    """
    try:
        from flask import has_request_context
        
        # Check for GameDays
        gamedays = GameDay.query.filter_by(gd_idLeague=league_id).count()
        if gamedays > 0:
            message = 'Cannot delete league: {} game days exist'.format(gamedays)
            return False, translate(message) if has_request_context() else message
        
        # Check for Games
        games = Game.query.join(GameDay).filter(GameDay.gd_idLeague == league_id).count()
        if games > 0:
            message = 'Cannot delete league: {} games exist'.format(games)
            return False, translate(message) if has_request_context() else message
        
        # Check for LeagueCourts
        league_courts = LeagueCourts.query.filter_by(lc_league_id=league_id).count()
        if league_courts > 0:
            message = 'Cannot delete league: {} court assignments exist'.format(league_courts)
            return False, translate(message) if has_request_context() else message
        
        # Check for GameDayPlayers
        gameday_players = GameDayPlayer.query.filter_by(gp_idLeague=league_id).count()
        if gameday_players > 0:
            message = 'Cannot delete league: {} player registrations exist'.format(gameday_players)
            return False, translate(message) if has_request_context() else message
        
        # Check for LeagueClassifications
        classifications = LeagueClassification.query.filter_by(lc_idLeague=league_id).count()
        if classifications > 0:
            message = 'Cannot delete league: {} classifications exist'.format(classifications)
            return False, translate(message) if has_request_context() else message
        
        # Check for LeaguePlayers
        league_players = LeaguePlayers.query.filter_by(lp_league_id=league_id).count()
        if league_players > 0:
            message = 'Cannot delete league: {} registered players exist'.format(league_players)
            return False, translate(message) if has_request_context() else message
        
        # Check for GameDayRegistrations
        registrations = GameDayRegistration.query.join(GameDay).filter(GameDay.gd_idLeague == league_id).count()
        if registrations > 0:
            message = 'Cannot delete league: {} gameday registrations exist'.format(registrations)
            return False, translate(message) if has_request_context() else message
        
        message = 'League can be safely deleted'
        return True, translate(message) if has_request_context() else message
        
    except Exception as e:
        message = 'Error checking league dependencies: {}'.format(str(e))
        return False, translate(message) if has_request_context() else message


@views.route('/league/<int:league_id>/delete', methods=['POST'])
@login_required
def delete_league(league_id):
    """Delete a league if no dependencies exist"""
    try:
        league = League.query.get_or_404(league_id)
        
        # Check authorization
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=league.lg_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to delete this league'), 'error')
            return redirect(url_for('views.edit_league', league_id=league_id))
        
        # Check if league can be deleted
        can_delete, message = can_delete_league(league_id)
        
        if not can_delete:
            flash(message, 'error')
            return redirect(url_for('views.edit_league', league_id=league_id))
        
        # Delete the league
        db.session.delete(league)
        db.session.commit()
        
        flash(translate('League deleted successfully'), 'success')
        return redirect(url_for('views.managementLeagues'))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error deleting league: {}').format(str(e)), 'error')
        return redirect(url_for('views.edit_league', league_id=league_id))


@views.route('/league/<int:league_id>/hide', methods=['POST'])
@login_required
def hide_league(league_id):
    """Hide/show a league by toggling its status"""
    try:
        league = League.query.get_or_404(league_id)
        
        # Check authorization
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=league.lg_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to modify this league'), 'error')
            return redirect(url_for('views.edit_league', league_id=league_id))
        
        # Toggle league visibility
        if league.lg_status == 'canceled':
            league.lg_status = 'active'
            flash(translate('League is now visible to users'), 'success')
        else:
            league.lg_status = 'canceled'
            flash(translate('League has been hidden from users'), 'success')
        
        db.session.commit()
        return redirect(url_for('views.edit_league', league_id=league_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error updating league status: {}').format(str(e)), 'error')
        return redirect(url_for('views.edit_league', league_id=league_id))


# Delete/Hide Event Routes
def can_delete_event(event_id):
    """
    Check if an event can be safely deleted by verifying no dependencies exist.
    Returns (can_delete: bool, message: str)
    """
    try:
        from flask import has_request_context
        
        # Check for EventRegistrations
        registrations = EventRegistration.query.filter_by(er_event_id=event_id).count()
        if registrations > 0:
            message = 'Cannot delete event: {} player registrations exist'.format(registrations)
            return False, translate(message) if has_request_context() else message
        
        # Check for EventGames (now in unified Game table)
        # Handle missing gm_idEvent column gracefully
        try:
            games = Game.query.filter_by(gm_idEvent=event_id).count()
        except Exception:
            # If gm_idEvent column doesn't exist, assume no games
            games = 0
        if games > 0:
            message = 'Cannot delete event: {} games exist'.format(games)
            return False, translate(message) if has_request_context() else message
        
        # Check for EventClassifications
        classifications = EventClassification.query.filter_by(ec_event_id=event_id).count()
        if classifications > 0:
            message = 'Cannot delete event: {} classifications exist'.format(classifications)
            return False, translate(message) if has_request_context() else message
        
        # Check for EventCourts
        courts = EventCourts.query.filter_by(evc_event_id=event_id).count()
        if courts > 0:
            message = 'Cannot delete event: {} court assignments exist'.format(courts)
            return False, translate(message) if has_request_context() else message
        
        message = 'Event can be safely deleted'
        return True, translate(message) if has_request_context() else message
        
    except Exception as e:
        message = 'Error checking event dependencies: {}'.format(str(e))
        return False, translate(message) if has_request_context() else message


@views.route('/event/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    """Delete an event if no dependencies exist"""
    try:
        event = Event.query.get_or_404(event_id)
        
        # Check authorization
        if current_user.us_is_superuser != 1:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                flash(translate('You are not authorized to delete this event'), 'error')
                return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Check if event can be deleted
        can_delete, message = can_delete_event(event_id)
        
        if not can_delete:
            flash(message, 'error')
            return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Delete the event
        db.session.delete(event)
        db.session.commit()
        
        flash(translate('Event deleted successfully'), 'success')
        return redirect(url_for('views.managementEvents'))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error deleting event: {}').format(str(e)), 'error')
        return redirect(url_for('views.managementEvents'))


@views.route('/event/<int:event_id>/hide', methods=['POST'])
@login_required
def hide_event(event_id):
    """Toggle hide/unhide event by changing canceled status"""
    try:
        event = Event.query.get_or_404(event_id)
        
        # Check authorization (superuser or club authorization)
        if current_user.us_is_superuser != 1:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                flash(translate('You are not authorized to modify this event'), 'error')
                return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Toggle hide/unhide
        if event.ev_status == 'canceled':
            # Unhide: restore to announced status
            event.ev_status = 'announced'
            flash(translate('Event has been unhidden and is now visible to users'), 'success')
        else:
            # Hide: mark as canceled
            event.ev_status = 'canceled'
            flash(translate('Event has been hidden from users'), 'success')
        
        db.session.commit()
        return redirect(url_for('views.detail_event', event_id=event_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error toggling event visibility: {}').format(str(e)), 'error')
        return redirect(url_for('views.detail_event', event_id=event_id))


@views.route('/update_game_score/<int:game_id>', methods=['POST'])
@login_required
def update_game_score(game_id):
    """Update the score for a specific game"""
    try:
        from .models import Game, Event, ClubAuthorization
        
        game = Game.query.get_or_404(game_id)
        
        # Get the event this game belongs to
        if not game.gm_idEvent:
            flash(translate('Can only update scores for event games'), 'error')
            return redirect(request.referrer or url_for('views.Events'))
        
        event = Event.query.get(game.gm_idEvent)
        if not event:
            flash(translate('Event not found'), 'error')
            return redirect(request.referrer or url_for('views.Events'))
        
        # Check authorization - user must be superuser or have club authorization
        if current_user.us_is_superuser != 1:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                flash(translate('You are not authorized to update scores for this event'), 'error')
                return redirect(url_for('views.detail_event', event_id=event.ev_id))
        
        # Get scores from form
        score_A = request.form.get('score_A')
        score_B = request.form.get('score_B')
        
        # Validate scores
        if score_A == '' or score_B == '':
            # Empty scores mean clearing the result
            game.gm_result_A = None
            game.gm_result_B = None
            flash(translate('Game score cleared successfully'), 'success')
        else:
            try:
                score_A = int(score_A)
                score_B = int(score_B)
                
                if score_A < 0 or score_B < 0:
                    flash(translate('Scores cannot be negative'), 'error')
                    return redirect(url_for('views.detail_event', event_id=event.ev_id))
                
                game.gm_result_A = score_A
                game.gm_result_B = score_B
                flash(translate('Game score updated successfully'), 'success')
                
            except ValueError:
                flash(translate('Invalid score format'), 'error')
                return redirect(url_for('views.detail_event', event_id=event.ev_id))
        
        db.session.commit()
        
        return redirect(url_for('views.detail_event', event_id=event.ev_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error updating game score: {}').format(str(e)), 'error')
        return redirect(request.referrer or url_for('views.Events'))


@views.route('/clear_game_score/<int:game_id>', methods=['POST'])
@login_required
def clear_game_score(game_id):
    """Clear the score for a specific game (set to NULL)"""
    try:
        from .models import Game, Event, ClubAuthorization
        
        game = Game.query.get_or_404(game_id)
        
        # Get the event this game belongs to
        if not game.gm_idEvent:
            flash(translate('Can only clear scores for event games'), 'error')
            return redirect(request.referrer or url_for('views.Events'))
        
        event = Event.query.get(game.gm_idEvent)
        if not event:
            flash(translate('Event not found'), 'error')
            return redirect(request.referrer or url_for('views.Events'))
        
        # Check authorization - user must be superuser or have club authorization
        if current_user.us_is_superuser != 1:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                flash(translate('You are not authorized to clear scores for this event'), 'error')
                return redirect(url_for('views.detail_event', event_id=event.ev_id))
        
        # Clear the scores
        game.gm_result_A = None
        game.gm_result_B = None
        
        db.session.commit()
        flash(translate('Game score cleared successfully'), 'success')
        
        return redirect(url_for('views.detail_event', event_id=event.ev_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error clearing game score: {}').format(str(e)), 'error')
        return redirect(request.referrer or url_for('views.Events'))


@views.route('/update_all_game_scores/<int:event_id>', methods=['POST'])
@login_required
def update_all_game_scores(event_id):
    """Update scores for all games in an event at once"""
    try:
        from .models import Game, Event, ClubAuthorization
        
        event = Event.query.get_or_404(event_id)
        
        # Check authorization - user must be superuser or have club authorization
        if current_user.us_is_superuser != 1:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                flash(translate('You are not authorized to update scores for this event'), 'error')
                return redirect(url_for('views.detail_event', event_id=event_id))
        
        # Parse scores from form data
        updated_count = 0
        cleared_count = 0
        
        # Get all games for this event
        event_games = Game.query.filter_by(gm_idEvent=event_id).all()
        
        for game in event_games:
            # Look for score inputs for this game
            score_a_key = f'scores[{game.gm_id}][A]'
            score_b_key = f'scores[{game.gm_id}][B]'
            
            score_a = request.form.get(score_a_key, '').strip()
            score_b = request.form.get(score_b_key, '').strip()
            
            # Skip if both scores are empty and game already has no scores
            if not score_a and not score_b and game.gm_result_A is None and game.gm_result_B is None:
                continue
            
            # Clear scores if both inputs are empty
            if not score_a and not score_b:
                if game.gm_result_A is not None or game.gm_result_B is not None:
                    game.gm_result_A = None
                    game.gm_result_B = None
                    cleared_count += 1
                continue
            
            # Validate and set scores if both are provided
            if score_a and score_b:
                try:
                    score_a_int = int(score_a)
                    score_b_int = int(score_b)
                    
                    if score_a_int < 0 or score_b_int < 0:
                        flash(translate('Scores cannot be negative for Game {}').format(game.gm_id), 'error')
                        continue
                    
                    # Only update if scores have changed
                    if game.gm_result_A != score_a_int or game.gm_result_B != score_b_int:
                        game.gm_result_A = score_a_int
                        game.gm_result_B = score_b_int
                        updated_count += 1
                        
                except ValueError:
                    flash(translate('Invalid score format for Game {}').format(game.gm_id), 'error')
                    continue
            else:
                # One score is empty, one is not - invalid state
                flash(translate('Both scores must be provided for Game {} or leave both empty to clear').format(game.gm_id), 'warning')
                continue
        
        # Commit all changes
        db.session.commit()
        
        # Provide feedback
        if updated_count > 0 and cleared_count > 0:
            flash(translate('Updated {} game scores and cleared {} game scores').format(updated_count, cleared_count), 'success')
        elif updated_count > 0:
            flash(translate('Updated {} game scores successfully').format(updated_count), 'success')
        elif cleared_count > 0:
            flash(translate('Cleared {} game scores successfully').format(cleared_count), 'success')
        else:
            flash(translate('No changes were made to game scores'), 'info')
        
        return redirect(url_for('views.detail_event', event_id=event_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error updating game scores: {}').format(str(e)), 'error')
        return redirect(request.referrer or url_for('views.Events'))