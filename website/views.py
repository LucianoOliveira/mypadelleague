from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Flask, session, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import (Users, UserRequests, Messages, League, Club, ClubAuthorization,
                    Court, GameDay, LeagueCourts, Game, GameDayPlayer, GameDayClassification,
                    LeagueClassification, ELOranking, ELOrankingHist, LeaguePlayers, GameDayRegistration,
                    Event, EventRegistration, EventClassification, EventCourts, EventPlayerNames,
                    EventType, MexicanConfig, PlayerClubNickname, slugify)
from . import db
import json, os, threading, hashlib
from datetime import datetime, date, timedelta, timezone
from functools import wraps
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

def _slug_to_id(slug):
    """Extract trailing numeric ID from a name-ID slug like 'Title-5' → 5."""
    try:
        return int(slug.rsplit('-', 1)[1])
    except (ValueError, IndexError, AttributeError):
        abort(404)


def _generate_unique_club_slug(name, exclude_id=None):
    """Generate a unique slug for a club, appending a counter on collisions."""
    base = slugify(name)
    slug = base
    counter = 2
    while True:
        q = Club.query.filter_by(cl_slug=slug)
        if exclude_id:
            q = q.filter(Club.cl_id != exclude_id)
        if not q.first():
            return slug
        slug = f"{base}_{counter}"
        counter += 1


def login_or_access_code_required(f):
    """Decorator that allows access either with login OR with valid access code for public events"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Support both new slug-based routes and legacy int routes
        slug_or_id = kwargs.get('slug') or kwargs.get('event_id')
        if isinstance(slug_or_id, str):
            event_id = _slug_to_id(slug_or_id)
        else:
            event_id = slug_or_id

        # Check if user is logged in
        if current_user.is_authenticated:
            return f(*args, **kwargs)

        # Check for access code in query params or session
        provided_code = request.args.get('code', '').strip()
        if not provided_code:
            provided_code = session.get(f'event_{event_id}_access_code', '').strip()

        if provided_code:
            # Verify access code
            event = Event.query.get(event_id)
            if event:
                date_str = event.ev_date.strftime('%Y%m%d')
                access_code_data = f"{event_id}-{event.ev_created_by_id}-{date_str}"
                expected_code = hashlib.md5(access_code_data.encode()).hexdigest()[:6].upper()

                if provided_code.upper() == expected_code:
                    # Store in session for subsequent requests
                    session[f'event_{event_id}_access_code'] = provided_code.upper()
                    return f(*args, **kwargs)

        # No valid authentication
        flash(translate('Please log in or provide a valid access code to edit this event'), 'error')
        event = Event.query.get(event_id)
        if event:
            return redirect(url_for('views.public_event_detail', slug=event.ev_slug))
        return redirect(url_for('views.home'))

    return decorated_function

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
    return_url = request.args.get('return_url') or url_for('views.edit_league', slug=league.lg_slug)
    
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
    result_data = Users.query.order_by(Users.us_name.asc()).all()
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
    
    # Convert empty string to None for birthday field
    if user_birthday == '':
        user_birthday = None
    
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
    user_Telephone = request.form.get('user_telephone')
    user_birthday = request.form.get('user_birthday')

    if user_Telephone:
        user_Telephone = user_Telephone.strip()

    if not user_Telephone:
        flash(translate('Telephone number is required.'), 'error')
        return render_template("user_info.html", user=current_user, p_user=pass_user)

    existing_phone = Users.query.filter(
        Users.us_telephone == user_Telephone,
        Users.us_id != userID
    ).first()
    if existing_phone:
        flash(translate('A user with this telephone number already exists!'), 'error')
        return render_template("user_info.html", user=current_user, p_user=pass_user)
    
    # Convert empty string to None for birthday field
    if user_birthday == '':
        user_birthday = None
    
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
        text(f"UPDATE tb_users SET us_name=:user_Name, us_email=:user_Email, us_telephone=:user_telephone, us_birthday=:user_birthday, us_is_active=:user_is_active, us_is_player=:user_is_player, us_is_manager=:user_is_manager, us_is_admin=:user_is_admin, us_is_superuser=:user_is_superuser WHERE us_id=:user_id"),
            {"user_Name": user_Name, "user_Email": user_Email, "user_telephone": user_Telephone, "user_id": user_id, "user_birthday": user_birthday, "user_is_active": user_is_active, "user_is_player": user_is_player, "user_is_manager": user_is_manager, "user_is_admin": user_is_admin, "user_is_superuser": user_is_superuser}
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

    # Load all clubs and existing nicknames for this user
    all_clubs = Club.query.order_by(Club.cl_name).all()
    user_nicknames = {n.pcn_club_id: n for n in PlayerClubNickname.query.filter_by(pcn_user_id=user_id).all()}
    
    return render_template('user_info.html', user=current_user, p_user=p_user, has_games=has_games,
                           all_clubs=all_clubs, user_nicknames=user_nicknames)

@views.route('/saveNickname/<int:user_id>', methods=['POST'])
@login_required
def saveNickname(user_id):
    if not current_user.us_is_superuser and current_user.us_id != user_id:
        flash(translate('You do not have permission to edit this user.'), 'error')
        return redirect(url_for('views.home'))
    club_id = request.form.get('club_id', type=int)
    nickname = request.form.get('nickname', '').strip()
    if not club_id or not nickname:
        flash(translate('Club and nickname are required.'), 'error')
        return redirect(url_for('views.editUser', user_id=user_id))
    existing = PlayerClubNickname.query.filter_by(pcn_user_id=user_id, pcn_club_id=club_id).first()
    if existing:
        existing.pcn_nickname = nickname
    else:
        db.session.add(PlayerClubNickname(pcn_user_id=user_id, pcn_club_id=club_id, pcn_nickname=nickname))
    db.session.commit()
    flash(translate('Nickname saved.'), 'success')
    return redirect(url_for('views.editUser', user_id=user_id))

@views.route('/deleteNickname/<int:user_id>/<int:club_id>', methods=['POST'])
@login_required
def deleteNickname(user_id, club_id):
    if not current_user.us_is_superuser and current_user.us_id != user_id:
        flash(translate('You do not have permission to edit this user.'), 'error')
        return redirect(url_for('views.home'))
    PlayerClubNickname.query.filter_by(pcn_user_id=user_id, pcn_club_id=club_id).delete()
    db.session.commit()
    flash(translate('Nickname deleted.'), 'success')
    return redirect(url_for('views.editUser', user_id=user_id))

@views.route('/toggle_user_elo/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_elo(user_id):
    """Superuser-only: hide or show a user in ELO rankings."""
    if not current_user.us_is_superuser:
        flash(translate('Not authorized'), 'error')
        return redirect(url_for('views.editUser', user_id=user_id))
    target = Users.query.get_or_404(user_id)
    target.us_hide_from_elo = not bool(target.us_hide_from_elo)
    db.session.commit()
    state = translate('hidden from') if target.us_hide_from_elo else translate('visible in')
    flash(translate('User {} ELO ranking.').format(state), 'success')
    return redirect(url_for('views.editUser', user_id=user_id))


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
        ELOrankingHist.query.filter_by(el_pl_id=userID).delete()
        
        # Delete user's gameday player records
        GameDayPlayer.query.filter_by(gp_idPlayer=userID).delete()
        
        # Delete user's event registrations and classifications
        EventRegistration.query.filter_by(er_player_id=userID).delete()
        EventClassification.query.filter_by(ec_player_id=userID).delete()
        
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
        new_club.cl_slug = _generate_unique_club_slug(name)
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

@views.route('/edit_club/<club_slug>', methods=['GET', 'POST'])
@login_required
def edit_club(club_slug):
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_slug == club_slug,
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
        # Regenerate slug when name changes
        club.cl_slug = _generate_unique_club_slug(club.cl_name, exclude_id=club.cl_id)
        
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
        return redirect(url_for('views.edit_club', club_slug=club.cl_slug))
    
    return render_template('edit_club.html', club=club, user=current_user)

@views.route('/club/<int:club_id>/activate', methods=['POST'])
@login_required
def activate_club(club_id):
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()

    if not current_user.us_is_manager and not current_user.us_is_admin and not current_user.us_is_superuser:
        flash(translate('Unauthorized'), 'error')
        return redirect(url_for('views.edit_club', club_slug=club.cl_slug) if club else url_for('views.management_clubs'))
    
    if not club:
        flash(translate('Club not found'), 'error')
        return redirect(url_for('views.management_clubs'))
    
    club.cl_active = True
    db.session.commit()
    flash(translate('Club activated successfully'), 'success')
    return redirect(url_for('views.edit_club', club_slug=club.cl_slug))

@views.route('/club/<int:club_id>/deactivate', methods=['POST'])
@login_required
def deactivate_club(club_id):
    club = Club.query.join(ClubAuthorization).filter(
        Club.cl_id == club_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()

    if not current_user.us_is_manager and not current_user.us_is_admin and not current_user.us_is_superuser:
        flash(translate('Unauthorized'), 'error')
        return redirect(url_for('views.edit_club', club_slug=club.cl_slug) if club else url_for('views.management_clubs'))
    
    if not club:
        flash(translate('Club not found'), 'error')
        return redirect(url_for('views.management_clubs'))
    
    club.cl_active = False
    db.session.commit()
    flash(translate('Club deactivated successfully'), 'success')
    return redirect(url_for('views.edit_club', club_slug=club.cl_slug))

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
    return redirect(url_for('views.edit_club', club_slug=club.cl_slug))

@views.route('/court/<int:court_id>/delete', methods=['POST'])
@login_required
def delete_court(court_id):
    court = Court.query.join(Club).join(ClubAuthorization).filter(
        Court.ct_id == court_id,
        ClubAuthorization.ca_user_id == current_user.us_id
    ).first()
    
    if not court:
        return jsonify({'error': translate('Unauthorized')}), 403
    
    club_slug = court.club.cl_slug  # Use relationship to get slug
    db.session.delete(court)
    db.session.commit()
    
    flash(translate('Court deleted successfully'), 'success')
    return redirect(url_for('views.edit_club', club_slug=club_slug))

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
        return redirect(url_for('views.edit_club', club_slug=club.cl_slug))
    
    existing_auth = ClubAuthorization.query.filter_by(
        ca_user_id=user.us_id,
        ca_club_id=club_id
    ).first()
    
    if existing_auth:
        flash(translate('User already has access to this club'), 'error')
        return redirect(url_for('views.edit_club', club_slug=club.cl_slug))
    
    auth = ClubAuthorization(
        ca_user_id=user.us_id,
        ca_club_id=club_id
    )
    db.session.add(auth)
    db.session.commit()
    
    flash(translate('User added successfully'), 'success')
    return redirect(url_for('views.edit_club', club_slug=club.cl_slug))

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
        club_err = Club.query.get(auth_to_delete.ca_club_id)
        return redirect(url_for('views.edit_club', club_slug=club_err.cl_slug) if club_err else url_for('views.management_clubs'))
    
    # Check if current user has authorization for the same club
    user_has_auth = ClubAuthorization.query.filter(
        ClubAuthorization.ca_user_id == current_user.us_id,
        ClubAuthorization.ca_club_id == auth_to_delete.ca_club_id
    ).first() is not None
    
    # Only allow if user has authorization for this club
    if not user_has_auth:
        flash(translate('Unauthorized'), 'error')
        return redirect(url_for('views.home'))
    
    club_to_redirect = Club.query.get(auth_to_delete.ca_club_id)  # Save before deleting
    
    db.session.delete(auth_to_delete)
    db.session.commit()
    
    flash(translate('User authorization removed successfully'), 'success')
    return redirect(url_for('views.edit_club', club_slug=club_to_redirect.cl_slug) if club_to_redirect else url_for('views.management_clubs'))


@views.route('/edit_league/<slug>', methods=['GET', 'POST'])
@login_required
def edit_league(slug):
    league_id = _slug_to_id(slug)
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
        return redirect(url_for('views.edit_league', slug=league.lg_slug) + '#court-details')

    return render_template('edit_league.html', 
                           user=current_user, 
                           league=league,
                           club=club,
                           courts=courts,
                           gamedays=gamedays,
                           registered_users=users_data,
                           now=datetime.utcnow())

# Event management routes
def generate_event_access_code(event_id, user_id, date_str):
    """Generate access code for public events"""
    import hashlib
    access_code_data = f"{event_id}-{user_id}-{date_str}"
    return hashlib.md5(access_code_data.encode()).hexdigest()[:6].upper()

def verify_event_access_code(event_id, provided_code):
    """Verify if provided access code is valid for event"""
    event = Event.query.get(event_id)
    if not event:
        return False
    
    # Generate expected code
    date_str = event.ev_date.strftime('%Y%m%d')
    expected_code = generate_event_access_code(event_id, event.ev_created_by_id, date_str)
    
    return provided_code.upper() == expected_code

@views.route('/event/<slug>', methods=['GET'])
def public_event_detail(slug):
    """Public event detail page"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    
    # Check if access code is provided for editing
    provided_code = request.args.get('code', '').strip()
    can_edit = False
    
    if provided_code:
        can_edit = verify_event_access_code(event_id, provided_code)
    elif current_user.is_authenticated:
        # Allow editing if user is the creator or has club authorization
        if event.ev_created_by_id == current_user.us_id:
            can_edit = True
        elif event.ev_club_id:
            club_auth = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id,
                ca_club_id=event.ev_club_id
            ).first()
            can_edit = club_auth is not None
    
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
    
    # Get event games and registrations  
    games = Game.query.filter_by(gm_idEvent=event_id).all()
    registrations = EventRegistration.query.filter_by(er_event_id=event_id).all()
    
    return render_template('event_detail_public.html', 
                         event=event,
                         club=club,
                         user=current_user,
                         is_registered=is_registered,
                         can_edit=can_edit,
                         games=games,
                         registrations=registrations,
                         access_code=provided_code if can_edit else None)

@views.route('/detail_event_tv/<slug>', methods=['GET'])  
def detail_event_tv(slug):
    """TV-optimized view for event details"""
    from .models import EventClassification
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized to manage this event
    user_is_authorized = False
    if current_user.is_authenticated:
        if current_user.us_is_superuser == 1:
            user_is_authorized = True
        else:
            # Check club authorization for non-public events
            is_public_event = event.ev_club_id == 2
            if not is_public_event:
                authorization = ClubAuthorization.query.filter_by(
                    ca_user_id=current_user.us_id, 
                    ca_club_id=event.ev_club_id
                ).first()
                user_is_authorized = authorization is not None
    
    # Get event games and player info
    event_games = Game.query.filter_by(gm_idEvent=event_id).order_by(Game.gm_timeStart, Game.gm_id).all()
    regular_players = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=False).all()
    substitute_players = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=True).all()
    
    # Get game player names for fallback display
    game_player_names = {}
    player_names = EventPlayerNames.query.filter_by(epn_event_id=event_id).all()

    # Build nickname map: {user_id: nickname} for the event's club
    nickname_map = {}
    if event.ev_club_id:
        nicknames = PlayerClubNickname.query.filter_by(pcn_club_id=event.ev_club_id).all()
        nickname_map = {n.pcn_user_id: n.pcn_nickname for n in nicknames}
    
    # Get event classifications with proper sorting (same as regular page)
    classifications = EventClassification.query.filter_by(ec_event_id=event_id).order_by(
        EventClassification.ec_points.desc(),
        EventClassification.ec_games_diff.desc()
    ).all()
    
    # Re-sort with tiebreaker logic
    # For Mexicano events with Ranking pairing: use club ELO as tiebreaker, then alphabetical
    is_mexican_ranking = (
        event.event_type and event.event_type.et_name == 'Mexicano'
        and event.ev_pairing_type == 'Ranking'
    )
    if is_mexican_ranking:
        club_elo = func_calculate_ELO_by_club(event.ev_club_id) if event.ev_club_id else []
        elo_map = {entry['player'].us_id: entry['rankingNow'] for entry in club_elo}
        classifications = sorted(classifications, key=lambda c: (
            -c.ec_points,
            -c.ec_games_diff,
            -(elo_map.get(c.ec_player_id, 0)),
            c.player.us_name.lower()
        ))
    else:
        classifications = sorted(classifications, key=lambda c: (
            -c.ec_points,
            -c.ec_games_diff,
            c.player.us_name.lower()
        ))
    
    return render_template('event_detail_tv.html', 
                         event=event, 
                         event_games=event_games,
                         game_player_names=game_player_names,
                         regular_players=regular_players,
                         substitute_players=substitute_players,
                         classifications=classifications,
                         user_is_authorized=user_is_authorized,
                         user=current_user,
                         nickname_map=nickname_map)

@views.route('/toggle_event_elo/<int:event_id>', methods=['POST'])
@login_required
def toggle_event_elo(event_id):
    """Superuser-only: toggle whether an event is excluded from ELO calculations."""
    event = Event.query.get_or_404(event_id)
    if current_user.us_is_superuser != 1:
        flash(translate('Not authorized'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    event.ev_exclude_from_elo = not bool(event.ev_exclude_from_elo)
    db.session.commit()
    state = translate('excluded from') if event.ev_exclude_from_elo else translate('included in')
    flash(translate('Event {} ELO ranking.').format(state), 'success')
    return redirect(url_for('views.detail_event', slug=event.ev_slug))


@views.route('/close_event/<int:event_id>', methods=['POST'])
@login_required
def close_event(event_id):
    """Close an event - delete rounds with all 0-0, lock event, mark as closed"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    user_is_authorized = False
    if current_user.us_is_superuser == 1:
        user_is_authorized = True
    else:
        is_public_event = event.ev_club_id == 2
        if not is_public_event:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            user_is_authorized = authorization is not None
    
    if not user_is_authorized:
        flash(translate('You are not authorized to close this event'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    try:
        # Get all games for this event
        all_games = Game.query.filter_by(gm_idEvent=event_id).order_by(Game.gm_timeStart.desc()).all()
        
        if not all_games:
            flash(translate('No games found for this event'), 'warning')
            return redirect(url_for('views.detail_event', slug=event.ev_slug))
        
        # Find and delete rounds where ALL games are 0-0
        deleted_rounds = 0
        
        # Group games by start time (rounds)
        from collections import defaultdict
        rounds = defaultdict(list)
        for game in all_games:
            rounds[game.gm_timeStart].append(game)
        
        # Check each round
        for start_time, round_games in rounds.items():
            should_delete = False
            
            # Get games with results and games without results
            games_with_results = [g for g in round_games if g.gm_result_A is not None and g.gm_result_B is not None]
            games_without_results = [g for g in round_games if g.gm_result_A is None or g.gm_result_B is None]
            
            # Case 1: All games in round have no results (null-null) - delete this round
            if len(games_without_results) == len(round_games):
                should_delete = True
            # Case 2: All games with results are 0-0 - delete this round
            elif games_with_results and all(game.gm_result_A == 0 and game.gm_result_B == 0 for game in games_with_results):
                should_delete = True
            
            # Delete the entire round if criteria met
            if should_delete:
                for game in round_games:
                    db.session.delete(game)
                deleted_rounds += 1
        
        # Recalculate classifications after deleting rounds
        if deleted_rounds > 0:
            from website.views import calculate_event_classifications
            calculate_event_classifications(event_id)
        
        # Mark event as closed
        event.ev_status = 'event_ended'
        
        db.session.commit()
        
        if deleted_rounds > 0:
            flash(translate('Event closed successfully! Deleted {} round(s) with all 0-0 scores.').format(deleted_rounds), 'success')
        else:
            flash(translate('Event closed successfully!'), 'success')
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(translate('Error closing event: {}').format(str(e)), 'error')
    
    return redirect(url_for('views.detail_event', slug=event.ev_slug))

@views.route('/close_mexicano/<int:event_id>', methods=['POST'])
@login_required
def close_mexicano(event_id):
    """Close a Mexicano event - delete games without results, mark as completed"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    user_is_authorized = False
    if current_user.us_is_superuser == 1:
        user_is_authorized = True
    else:
        is_public_event = event.ev_club_id == 2
        if not is_public_event:
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            user_is_authorized = authorization is not None
    
    if not user_is_authorized:
        flash(translate('You are not authorized to close this event'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    try:
        # Delete all games without results (either score is null)
        games_without_results = Game.query.filter_by(gm_idEvent=event_id).filter(
            db.or_(Game.gm_result_A == None, Game.gm_result_B == None)
        ).all()
        
        deleted_count = len(games_without_results)
        for game in games_without_results:
            db.session.delete(game)
        
        # Recalculate classifications after deleting games
        if deleted_count > 0:
            calculate_event_classifications(event_id)
        
        # Mark event as completed
        event.ev_status = 'event_ended'
        
        db.session.commit()
        
        if deleted_count > 0:
            flash(translate('Mexicano closed successfully! {} unplayed game(s) removed.').format(deleted_count), 'success')
        else:
            flash(translate('Mexicano closed successfully!'), 'success')
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(translate('Error closing Mexicano: {}').format(str(e)), 'error')
    
    return redirect(url_for('views.detail_event', slug=event.ev_slug))

@views.route('/detail_event/<slug>', methods=['GET'])  
def detail_event(slug):
    """Event detail page with full functionality for authenticated users"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized to manage this event
    user_is_authorized = False
    can_delete = False
    delete_message = ""
    can_close_event = False
    
    if current_user.is_authenticated:
        if current_user.us_is_superuser == 1:
            user_is_authorized = True
        else:
            # Check club authorization for non-public events
            is_public_event = event.ev_club_id == 2
            if not is_public_event:
                authorization = ClubAuthorization.query.filter_by(
                    ca_user_id=current_user.us_id, 
                    ca_club_id=event.ev_club_id
                ).first()
                user_is_authorized = authorization is not None
    
    # Check if event can be deleted (no games played yet)
    if user_is_authorized:
        event_games = Game.query.filter_by(gm_idEvent=event_id).all()
        games_with_results = [g for g in event_games if g.gm_result_A is not None or g.gm_result_B is not None]
        if not games_with_results:
            can_delete = True
        else:
            delete_message = translate('Cannot delete event with completed games')
        
        # Check if event can be closed (has games and not already closed)
        if event_games and event.ev_status != 'event_ended':
            can_close_event = True
    
    # Get event games and player info
    event_games = Game.query.filter_by(gm_idEvent=event_id).all()
    regular_players = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=False).all()
    substitute_players = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=True).all()
    
    # Get club info
    club = Club.query.get(event.ev_club_id) if event.ev_club_id else None
    
    # Get event classifications with proper sorting
    classifications = EventClassification.query.filter_by(ec_event_id=event_id).order_by(
        EventClassification.ec_points.desc(),
        EventClassification.ec_games_diff.desc()
    ).all()
    
    # Re-sort with tiebreaker logic
    # For Mexicano events with Ranking pairing: use club ELO as tiebreaker, then alphabetical
    is_mexican_ranking = (
        event.event_type and event.event_type.et_name == 'Mexicano'
        and event.ev_pairing_type == 'Ranking'
    )
    if is_mexican_ranking:
        club_elo = func_calculate_ELO_by_club(event.ev_club_id) if event.ev_club_id else []
        elo_map = {entry['player'].us_id: entry['rankingNow'] for entry in club_elo}
        classifications = sorted(classifications, key=lambda c: (
            -c.ec_points,
            -c.ec_games_diff,
            -(elo_map.get(c.ec_player_id, 0)),
            c.player.us_name.lower()
        ))
    else:
        classifications = sorted(classifications, key=lambda c: (
            -c.ec_points,
            -c.ec_games_diff,
            c.player.us_name.lower()
        ))
    
    # Check if user is registered
    user_registration = None
    if current_user.is_authenticated:
        user_registration = EventRegistration.query.filter_by(
            er_event_id=event_id,
            er_player_id=current_user.us_id
        ).first()
    
    # Check if user can register
    can_register = False
    if current_user.is_authenticated and not user_registration:
        # Add registration logic here if needed
        pass
    
    # Get game player names for display (in case some games use names instead of user IDs)
    game_player_names = {}
    player_names = EventPlayerNames.query.filter_by(epn_event_id=event_id).all()

    # Build nickname map: {user_id: nickname} for the event's club
    nickname_map = {}
    if event.ev_club_id:
        nicknames = PlayerClubNickname.query.filter_by(pcn_club_id=event.ev_club_id).all()
        nickname_map = {n.pcn_user_id: n.pcn_nickname for n in nicknames}
    
    return render_template('event_detail.html', 
                         event=event,
                         club=club,
                         user=current_user,
                         user_is_authorized=user_is_authorized,
                         can_delete=can_delete,
                         delete_message=delete_message,
                         can_close_event=can_close_event,
                         event_games=event_games,
                         regular_players=regular_players,
                         substitute_players=substitute_players,
                         classifications=classifications,
                         user_registration=user_registration,
                         can_register=can_register,
                         game_player_names=game_player_names,
                         nickname_map=nickname_map)

# Events public page
@views.route('/Events', methods=['GET'])
@views.route('/events', methods=['GET'])
def events():
    """Public page to display all events"""
    # Get active events (exclude canceled and ended events)
    active_events = Event.query\
        .outerjoin(Club, Event.ev_club_id == Club.cl_id)\
        .filter(Event.ev_status.notin_(['canceled', 'event_ended']))\
        .filter(or_(Event.ev_club_id.is_(None), Club.cl_active == True))\
        .order_by(Event.ev_date.desc())\
        .all()
    
    # Get past events (ended events)
    past_events = Event.query\
        .outerjoin(Club, Event.ev_club_id == Club.cl_id)\
        .filter(Event.ev_status == 'event_ended')\
        .filter(or_(Event.ev_club_id.is_(None), Club.cl_active == True))\
        .order_by(Event.ev_date.desc())\
        .limit(20)\
        .all()
    
    return render_template("events.html", user=current_user, events_data=active_events, past_events=past_events)

@views.route('/managementEvents', methods=['GET'])
@login_required
def managementEvents():
    """Events management page for authorized users"""
    # Get events from clubs the user is authorized for AND public events created by user
    club_events = Event.query\
        .join(Club, Event.ev_club_id == Club.cl_id)\
        .join(ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id)\
        .filter(ClubAuthorization.ca_user_id == current_user.us_id)\
        .all()
    
    # Get public events created by this user (no club association)
    public_events = Event.query\
        .filter(Event.ev_club_id.is_(None))\
        .filter(Event.ev_created_by_id == current_user.us_id)\
        .all()
    
    # Combine both types of events
    all_events = club_events + public_events
    all_events.sort(key=lambda x: x.ev_date, reverse=True)
    
    return render_template("managementEvents.html", user=current_user, result=all_events)

@views.route('/display_event_main_image/<int:eventID>/<int:packageID>', methods=['GET'])
def display_event_main_image(eventID, packageID):
    """Display the main image for an event package"""
    try:
        # Construct the path to the image
        image_path = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), 
            'static', 'photos', 'events', str(eventID), str(packageID), 'main.jpg'
        )
        
        # Check if the image exists
        if os.path.exists(image_path):
            return send_file(image_path, mimetype='image/jpeg')
        else:
            # Return a default image or 404
            default_image_path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)), 
                'static', 'images', 'default_event.jpg'
            )
            if os.path.exists(default_image_path):
                return send_file(default_image_path, mimetype='image/jpeg')
            else:
                return "Image not found", 404
                
    except Exception as e:
        print(f"Error displaying image: {e}")
        return "Error loading image", 500

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

    # Pre-select club if user manages only one club
    selected_club_id = None
    if len(authorized_clubs) == 1:
        selected_club_id = authorized_clubs[0].cl_id
    
    return render_template("create_event.html", user=current_user, clubs=authorized_clubs, event_types=event_types, selected_club_id=selected_club_id)

@views.route('/create_event_public', methods=['GET'])
def create_event_public():
    """Public event creation - show event type selection cards"""
    # Get the 3 main event types that we want to show as cards
    event_types = EventType.query.filter(
        EventType.et_is_active == True,
        EventType.et_name.in_(['Mexicano', 'Americano', 'NonStop'])
    ).order_by(EventType.et_order).all()
    
    return render_template("create_event_public.html", event_types=event_types, user=current_user)

@views.route('/create_event_public_form/<int:event_type_id>', methods=['GET', 'POST'])
def create_event_public_form(event_type_id):
    """Public event creation form for selected event type - Step 1: Basic info (simplified)"""
    # Validate event type exists and is active
    event_type = EventType.query.filter_by(et_id=event_type_id, et_is_active=True).first()
    if not event_type:
        flash(translate('Invalid event type selected!'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    if request.method == 'POST':
        # Get form data
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time') or '18:00'  # Default to 6 PM
        event_title = request.form.get('event_title')
        
        # Validation - only require date
        if not event_date:
            flash(translate('Event date is required!'), 'error')
            return render_template("create_event_public_form_simple.html", event_type=event_type, user=current_user)
        
        # Auto-generate event title if not provided
        if not event_title or event_title.strip() == '':
            from datetime import datetime
            date_obj = datetime.strptime(event_date, '%Y-%m-%d')
            event_title = f"{event_type.et_name} Tournament - {date_obj.strftime('%B %d, %Y')}"
        
        # Store minimal session data for multi-step process
        session['public_event'] = {
            'event_type_id': event_type_id,
            'event_date': event_date,
            'event_time': event_time,
            'event_title': event_title.strip(),
            'step': 1
        }
        
        # For Mexican tournaments, go to player setup
        if event_type.et_name == 'Mexicano':
            return redirect(url_for('views.create_event_step_players'))
        else:
            # For other event types, implement later
            flash(translate('This event type is not yet implemented for public creation.'), 'info')
            return redirect(url_for('views.create_event_public'))
    
    return render_template("create_event_public_form_simple.html", event_type=event_type, user=current_user)

@views.route('/create_event_step_players', methods=['GET', 'POST'])
def create_event_step_players():
    """Step 2: Configure number of players for Mexican tournament"""
    # Check if we have event data in session
    if 'public_event' not in session:
        flash(translate('Session expired. Please start again.'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_type_id = session['public_event']['event_type_id']
    event_type = EventType.query.filter_by(et_id=event_type_id, et_is_active=True).first()
    if not event_type:
        flash(translate('Invalid event type selected!'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    if request.method == 'POST':
        max_players = request.form.get('max_players')
        
        # Validate player count
        if not max_players or int(max_players) < 8 or int(max_players) % 4 != 0:
            flash(translate('Number of players must be at least 8 and a multiple of 4!'), 'error')
            return render_template("create_event_step_players.html", event_type=event_type, user=current_user)
        
        # Store player count in session
        session['public_event']['max_players'] = int(max_players)
        session['public_event']['step'] = 2
        session.modified = True
        
        # Redirect to pairing method selection
        return redirect(url_for('views.create_event_step_pairing'))
    
    
    return render_template("create_event_step_players.html", event_type=event_type, user=current_user)

@views.route('/create_event_step_pairing', methods=['GET', 'POST'])
def create_event_step_pairing():
    """Step 3: Select pairing method for Mexican tournament"""
    # Check if we have event data in session
    if 'public_event' not in session or 'max_players' not in session['public_event']:
        flash(translate('Session expired. Please start again.'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_type_id = session['public_event']['event_type_id']
    event_type = EventType.query.filter_by(et_id=event_type_id, et_is_active=True).first()
    if not event_type:
        flash(translate('Invalid event type selected!'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    if request.method == 'POST':
        pairing_method = request.form.get('pairing_method')
        
        if pairing_method not in ['Random', 'Manual', 'Ranking']:
            flash(translate('Please select a valid pairing method!'), 'error')
            return render_template("create_event_step_pairing.html", event_type=event_type, user=current_user)
        
        # Store pairing method in session
        session['public_event']['pairing_method'] = pairing_method
        session['public_event']['step'] = 3
        session.modified = True
        
        # Redirect to court setup
        return redirect(url_for('views.create_event_step_courts'))
    
    return render_template("create_event_step_pairing.html", event_type=event_type, user=current_user)

@views.route('/create_event_step_courts', methods=['GET', 'POST'])
def create_event_step_courts():
    """Step 4: Configure court names for Mexican tournament"""
    # Check if we have event data in session
    if 'public_event' not in session or 'pairing_method' not in session['public_event']:
        flash(translate('Session expired. Please start again.'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_type_id = session['public_event']['event_type_id']
    event_type = EventType.query.filter_by(et_id=event_type_id, et_is_active=True).first()
    if not event_type:
        flash(translate('Invalid event type selected!'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_data = session['public_event']
    num_courts = event_data['max_players'] // 4
    
    if request.method == 'POST':
        court_names = []
        for i in range(num_courts):
            court_name = request.form.get(f'court_{i}', f'Court {i+1}')
            court_names.append(court_name)
        
        # Store court names in session
        session['public_event']['court_names'] = court_names
        session['public_event']['step'] = 4
        session.modified = True
        
        # Redirect to player registration
        return redirect(url_for('views.create_event_step_register_players'))
    
    # Generate default court names
    default_courts = [f'Court {i+1}' for i in range(num_courts)]
    
    return render_template("create_event_step_courts.html", 
                          event_type=event_type, 
                          user=current_user,
                          num_courts=num_courts,
                          default_courts=default_courts)

@views.route('/create_event_step_register_players', methods=['GET', 'POST'])
def create_event_step_register_players():
    """Step 5: Register players for Mexican tournament"""
    # Check if we have event data in session
    if 'public_event' not in session or 'court_names' not in session['public_event']:
        flash(translate('Session expired. Please start again.'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_type_id = session['public_event']['event_type_id']
    event_type = EventType.query.filter_by(et_id=event_type_id, et_is_active=True).first()
    if not event_type:
        flash(translate('Invalid event type selected!'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_data = session['public_event']
    max_players = event_data['max_players']
    pairing_method = event_data['pairing_method']
    
    if request.method == 'POST':
        # Collect all player names from unified 2-column layout
        players = []
        locked_pairs = []

        for i in range(max_players):
            player_name = request.form.get(f'player_{i}')
            if player_name and player_name.strip():
                players.append(player_name.strip())

        # Collect locked pairs (works for any pairing method)
        for pair_index in range(max_players // 2):
            is_locked = request.form.get(f'pair_{pair_index}_locked', 'false') == 'true'
            if is_locked:
                player1_index = pair_index * 2
                player2_index = player1_index + 1
                locked_pairs.append((player1_index, player2_index))
        
        # Validate all players are filled
        if len(players) != max_players:
            flash(translate('Please fill all player names before creating the event!'), 'error')
            return render_template("create_event_step_register_players.html", 
                                  event_type=event_type, 
                                  user=current_user,
                                  event_data=event_data,
                                  pairing_method=pairing_method,
                                  max_players=max_players)
        
        # Store players in session
        session['public_event']['players'] = players
        session['public_event']['locked_pairs'] = locked_pairs
        session['public_event']['step'] = 5
        session.modified = True
        
        # Finally create the event
        return redirect(url_for('views.create_event_final'))
    
    return render_template("create_event_step_register_players.html", 
                          event_type=event_type, 
                          user=current_user,
                          event_data=event_data,
                          pairing_method=pairing_method,
                          max_players=max_players)

@views.route('/create_event_final', methods=['GET', 'POST'])
def create_event_final():
    """Final step: Create the event and first round games"""
    import random
    import string
    
    # Check if we have event data in session
    if 'public_event' not in session:
        flash(translate('Session expired. Please start again.'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_type_id = session['public_event']['event_type_id']
    event_type = EventType.query.filter_by(et_id=event_type_id, et_is_active=True).first()
    if not event_type:
        flash(translate('Invalid event type selected!'), 'error')
        return redirect(url_for('views.create_event_public'))
    
    event_data = session['public_event']
    
    try:
        # Parse dates
        event_date_parsed = datetime.strptime(event_data['event_date'], "%Y-%m-%d").date()
        event_time_parsed = datetime.strptime(event_data['event_time'], "%H:%M").time()
        
        # Use system user and public events club for public events
        # Try to use system user ID 2, but fallback if it doesn't exist
        system_user = Users.query.get(2)
        if system_user:
            system_user_id = 2
        else:
            # Fallback: find first admin/superuser
            admin_user = Users.query.filter(
                (Users.us_is_admin == True) | (Users.us_is_superuser == True)
            ).first()
            system_user_id = admin_user.us_id if admin_user else 1
        
        public_club_id = 2
        
        # Create the event with minimal required fields
        new_event = Event(
            ev_title=event_data['event_title'],
            ev_club_id=public_club_id,  # Use Public Events club
            ev_location='Public Event',  # Use a default location
            ev_date=event_date_parsed,
            ev_start_time=event_time_parsed,
            ev_type_id=event_type_id,
            ev_max_players=event_data.get('max_players', 8),
            ev_status='announced',
            ev_created_by_id=system_user_id
        )
        
        db.session.add(new_event)
        db.session.commit()
        
        # Generate access code using the helper function
        date_str = event_date_parsed.strftime('%Y%m%d')
        access_code = generate_event_access_code(new_event.ev_id, system_user_id, date_str)
        
        # For Mexican tournaments, create players and first round games
        if event_type.et_name == 'Mexicano' and 'players' in event_data:
            # Create or find users for players and register them
            player_users = []
            for player_name in event_data['players']:
                user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
                if not user:
                    # Try word-by-word match (e.g. "Luciano Oliveira" matches "Luciano \"Fugi\" Oliveira")
                    words = [w for w in player_name.strip().split() if w]
                    if words:
                        q = Users.query
                        for word in words:
                            q = q.filter(Users.us_name.ilike(f'%{word}%'))
                        user = q.first()
                if not user:
                    user = Users(
                        us_name=player_name.strip(),
                        us_email=f"{player_name.lower().replace(' ', '.')}@temp.event",
                        us_telephone=f"temp_{player_name.lower().replace(' ', '')}",
                        us_is_player=True,
                        us_is_active=True,
                        us_birthday=datetime.strptime('1990-01-01', '%Y-%m-%d').date(),
                        us_pwd=generate_password_hash('temp123', method='pbkdf2:sha256')
                    )
                    db.session.add(user)
                    db.session.flush()
                
                # Register player for event
                registration = EventRegistration(
                    er_event_id=new_event.ev_id,
                    er_player_id=user.us_id,
                    er_registered_by_id=system_user_id
                )
                db.session.add(registration)
                player_users.append(user)
            
            db.session.commit()
            
            # Clear session data
            session.pop('public_event', None)
            
            flash(translate('Event created successfully! Access Code: {}. Save this code to manage your event.').format(access_code), 'success')
            return redirect(url_for('views.public_event_detail', slug=new_event.ev_slug, code=access_code))
        
        else:
            # For other event types, just create the basic event
            session.pop('public_event', None)
            flash(translate('Event created successfully! Access Code: {}').format(access_code), 'success')
            return redirect(url_for('views.public_event_detail', slug=new_event.ev_slug))
    
    except Exception as e:
        db.session.rollback()
        flash(translate('Error creating event: {}').format(str(e)), 'error')
        return redirect(url_for('views.create_event_public'))

# ============================================
# PUBLIC EVENT EDITING ROUTES (mirrors creation flow)
# ============================================

@views.route('/edit_event_public/<slug>', methods=['GET'])
@login_or_access_code_required
def edit_event_public(slug):
    """Entry point for editing public events - redirects to first step"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    
    # Only allow for public events
    if event.ev_club_id != 2:
        flash(translate('This editing flow is only for public events'), 'error')
        return redirect(url_for('views.edit_event_step1', event_id=event_id))
    
    # Store access code for the session
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    # Redirect to first edit step
    return redirect(url_for('views.edit_event_public_step_basic', slug=event.ev_slug, code=access_code))

@views.route('/edit_event_public_step_basic/<slug>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_public_step_basic(slug):
    """Step 1: Edit basic info (date, time, name)"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    if request.method == 'POST':
        try:
            # Update basic information
            event.ev_date = datetime.strptime(request.form['event_date'], "%Y-%m-%d").date()
            event.ev_start_time = datetime.strptime(request.form['event_time'], "%H:%M").time()
            event_title = request.form.get('event_title', '').strip()
            event.ev_title = event_title if event_title else f"Mexicano {event.ev_date.strftime('%B %d')}"
            
            db.session.commit()
            return redirect(url_for('views.edit_event_public_step_players', slug=event.ev_slug, code=access_code))
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating event: {}').format(str(e)), 'error')
    
    # Pre-populate data
    event_data = {
        'event_date': event.ev_date.strftime('%Y-%m-%d'),
        'event_time': event.ev_start_time.strftime('%H:%M'),
        'event_title': event.ev_title
    }
    
    return render_template("create_event_public_form_simple.html", 
                         event_type=event.event_type, 
                         user=current_user,
                         event_data=event_data,
                         is_edit=True,
                         event_id=event_id,
                         event_slug=event.ev_slug,
                         access_code=access_code)

@views.route('/edit_event_public_step_players/<slug>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_public_step_players(slug):
    """Step 2: Edit number of players"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    if request.method == 'POST':
        try:
            max_players = int(request.form.get('max_players'))
            
            # Validate
            if max_players < 8 or max_players % 4 != 0:
                flash(translate('Number of players must be at least 8 and a multiple of 4!'), 'error')
            else:
                event.ev_max_players = max_players
                db.session.commit()
                return redirect(url_for('views.edit_event_public_step_pairing', slug=event.ev_slug, code=access_code))
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating players: {}').format(str(e)), 'error')
    
    return render_template("create_event_step_players.html", 
                         event_type=event.event_type,
                         user=current_user,
                         current_max_players=event.ev_max_players,
                         is_edit=True,
                         event_id=event_id,
                         event_slug=event.ev_slug,
                         access_code=access_code)

@views.route('/edit_event_public_step_pairing/<slug>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_public_step_pairing(slug):
    """Step 3: Edit pairing method"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    if request.method == 'POST':
        try:
            pairing_type = request.form.get('pairing_type')
            if pairing_type in ['Random', 'Manual', 'L&R Random', 'Ranking']:
                event.ev_pairing_type = pairing_type
                db.session.commit()
                return redirect(url_for('views.edit_event_public_step_courts', slug=event.ev_slug, code=access_code))
            else:
                flash(translate('Invalid pairing type'), 'error')
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating pairing: {}').format(str(e)), 'error')
    
    return render_template("create_event_step_pairing.html",
                         event_type=event.event_type,
                         user=current_user,
                         max_players=event.ev_max_players,
                         current_pairing=event.ev_pairing_type,
                         is_edit=True,
                         event_id=event_id,
                         event_slug=event.ev_slug,
                         access_code=access_code)

@views.route('/edit_event_public_step_courts/<slug>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_public_step_courts(slug):
    """Step 4: Edit courts"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    # Get public club courts
    public_club = Club.query.get(2)
    courts = Court.query.filter_by(ct_club_id=2).all() if public_club else []
    
    # Get current event courts
    current_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
    current_court_ids = [ec.evc_court_id for ec in current_courts]
    
    if request.method == 'POST':
        try:
            court_count = int(request.form.get('court_count', 1))
            
            # Clear existing courts
            EventCourts.query.filter_by(evc_event_id=event_id).delete()
            
            # Add selected courts
            for i in range(court_count):
                court_id = request.form.get(f'court_{i}')
                if court_id:
                    event_court = EventCourts(evc_event_id=event_id, evc_court_id=court_id)
                    db.session.add(event_court)
            
            db.session.commit()
            return redirect(url_for('views.edit_event_public_step_register', slug=event.ev_slug, code=access_code))
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating courts: {}').format(str(e)), 'error')
    
    return render_template("create_event_step_courts.html",
                         event_type=event.event_type,
                         user=current_user,
                         courts=courts,
                         current_courts=current_court_ids,
                         is_edit=True,
                         event_id=event_id,
                         event_slug=event.ev_slug,
                         access_code=access_code)

@views.route('/edit_event_public_step_register/<slug>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_public_step_register(slug):
    """Step 5: Edit player names"""
    event_id = _slug_to_id(slug)
    event = Event.query.get_or_404(event_id)
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    # Get existing player names
    existing_players = EventPlayerNames.query.filter_by(epn_event_id=event_id).all()
    
    # Organize by pairing type
    player_data = {'random': [], 'team': {}, 'left': [], 'right': []}
    for player in existing_players:
        if player.epn_position_type == 'random':
            while len(player_data['random']) <= player.epn_position_index:
                player_data['random'].append('')
            player_data['random'][player.epn_position_index] = player.epn_player_name
        elif player.epn_position_type == 'team':
            team = player.epn_team_identifier
            if team not in player_data['team']:
                player_data['team'][team] = ['', '']
            player_data['team'][team][player.epn_team_position - 1] = player.epn_player_name
        elif player.epn_position_type == 'left':
            while len(player_data['left']) <= player.epn_position_index:
                player_data['left'].append('')
            player_data['left'][player.epn_position_index] = player.epn_player_name
        elif player.epn_position_type == 'right':
            while len(player_data['right']) <= player.epn_position_index:
                player_data['right'].append('')
            player_data['right'][player.epn_position_index] = player.epn_player_name
    
    if request.method == 'POST':
        try:
            # Clear existing player data
            EventPlayerNames.query.filter_by(epn_event_id=event_id).delete()
            EventRegistration.query.filter_by(er_event_id=event_id).delete()
            
            # Ensure we have a valid creator user ID
            creator_user_id = event.ev_created_by_id
            if not creator_user_id:
                # Fallback to current user or first admin
                if current_user.is_authenticated:
                    creator_user_id = current_user.us_id
                else:
                    admin_user = Users.query.filter(
                        (Users.us_is_admin == True) | (Users.us_is_superuser == True)
                    ).first()
                    creator_user_id = admin_user.us_id if admin_user else 1
            
            # Re-create players using the update_event_players logic
            # This is handled by calling the existing update function
            # which will read from request.form
            
            # We'll redirect to a processing route that calls update_event_players
            session[f'edit_event_{event_id}_processing'] = True
            session.modified = True
            
            # Process the form submission like create_event_final does
            pairing_type = event.ev_pairing_type
            max_players = event.ev_max_players
            
            def get_or_create_user(player_name):
                if not player_name or not player_name.strip():
                    return None
                user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
                if not user:
                    # Try word-by-word match (e.g. "Luciano Oliveira" matches "Luciano \"Fugi\" Oliveira")
                    words = [w for w in player_name.strip().split() if w]
                    if words:
                        q = Users.query
                        for word in words:
                            q = q.filter(Users.us_name.ilike(f'%{word}%'))
                        user = q.first()
                if not user:
                    user = Users(
                        us_name=player_name.strip(),
                        us_email=f"{player_name.strip().lower().replace(' ', '.')}@temp.event",
                        us_telephone=f"temp_{player_name.strip().lower().replace(' ', '')}",
                        us_is_player=True,
                        us_is_active=True
                    )
                    db.session.add(user)
                    db.session.flush()
                return user
            
            # Process based on pairing type (same logic as create_event_final)
            if pairing_type in ('Random', 'Ranking'):
                for i in range(max_players):
                    player_name = request.form.get(f'player_{i}')
                    if player_name and player_name.strip():
                        user = get_or_create_user(player_name.strip())
                        if user:
                            record = EventPlayerNames(
                                epn_event_id=event_id,
                                epn_player_name=player_name.strip(),
                                epn_position_type='random',
                                epn_position_index=i,
                                epn_created_by_id=creator_user_id
                            )
                            db.session.add(record)
                            registration = EventRegistration(
                                er_event_id=event_id,
                                er_player_id=user.us_id,
                                er_registered_by_id=creator_user_id,
                                er_is_substitute=False
                            )
                            db.session.add(registration)
                            
            elif pairing_type == 'Manual':
                teams_needed = max_players // 2
                for team_idx in range(teams_needed):
                    team_letter = chr(65 + team_idx)
                    player1_name = request.form.get(f'team_{team_letter}_player1')
                    player2_name = request.form.get(f'team_{team_letter}_player2')
                    
                    for pos, player_name in enumerate([player1_name, player2_name], 1):
                        if player_name and player_name.strip():
                            user = get_or_create_user(player_name.strip())
                            if user:
                                record = EventPlayerNames(
                                    epn_event_id=event_id,
                                    epn_player_name=player_name.strip(),
                                    epn_position_type='team',
                                    epn_position_index=team_idx,
                                    epn_team_identifier=team_letter,
                                    epn_team_position=pos,
                                    epn_created_by_id=creator_user_id
                                )
                                db.session.add(record)
                                registration = EventRegistration(
                                    er_event_id=event_id,
                                    er_player_id=user.us_id,
                                    er_registered_by_id=creator_user_id,
                                    er_is_substitute=False
                                )
                                db.session.add(registration)
                                
            elif pairing_type == 'L&R Random':
                left_players = max_players // 2
                right_players = max_players // 2
                
                for i in range(left_players):
                    left_player = request.form.get(f'left_player_{i}')
                    if left_player and left_player.strip():
                        user = get_or_create_user(left_player.strip())
                        if user:
                            record = EventPlayerNames(
                                epn_event_id=event_id,
                                epn_player_name=left_player.strip(),
                                epn_position_type='left',
                                epn_position_index=i,
                                epn_created_by_id=creator_user_id
                            )
                            db.session.add(record)
                            registration = EventRegistration(
                                er_event_id=event_id,
                                er_player_id=user.us_id,
                                er_registered_by_id=creator_user_id,
                                er_is_substitute=False
                            )
                            db.session.add(registration)
                            
                for i in range(right_players):
                    right_player = request.form.get(f'right_player_{i}')
                    if right_player and right_player.strip():
                        user = get_or_create_user(right_player.strip())
                        if user:
                            record = EventPlayerNames(
                                epn_event_id=event_id,
                                epn_player_name=right_player.strip(),
                                epn_position_type='right',
                                epn_position_index=i,
                                epn_created_by_id=creator_user_id
                            )
                            db.session.add(record)
                            registration = EventRegistration(
                                er_event_id=event_id,
                                er_player_id=user.us_id,
                                er_registered_by_id=creator_user_id,
                                er_is_substitute=False
                            )
                            db.session.add(registration)
            
            db.session.commit()
            flash(translate('Event updated successfully!'), 'success')
            return redirect(url_for('views.public_event_detail', slug=event.ev_slug, code=access_code))
            
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating players: {}').format(str(e)), 'error')
    
    return render_template("create_event_step_register_players.html",
                         event_type=event.event_type,
                         user=current_user,
                         max_players=event.ev_max_players,
                         pairing_method=event.ev_pairing_type,
                         player_data=player_data,
                         is_edit=True,
                         event_id=event_id,
                         event_slug=event.ev_slug,
                         access_code=access_code)

# ============================================
# CLUB EVENT EDITING ROUTES (traditional admin interface)
# ============================================

@views.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
@login_required  
def edit_event(event_id):
    """Unified edit event page with tabs"""
    event = Event.query.get_or_404(event_id)
    
    # Prevent editing closed events
    if event.ev_status == 'event_ended':
        flash(translate('Cannot edit a closed event'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Check authorization (superuser or club authorization)
    if current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))

    # Get data needed for the template
    if current_user.us_is_superuser == 1:
        authorized_clubs = Club.query.filter_by(cl_active=True).all()
    else:
        authorized_clubs = db.session.query(Club).join(
            ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id
        ).filter(
            ClubAuthorization.ca_user_id == current_user.us_id,
            Club.cl_active == True
        ).all()

    # Get club courts for this event
    club = Club.query.get_or_404(event.ev_club_id)
    all_courts = Court.query.filter_by(ct_club_id=club.cl_id).all()
    
    # Get existing event courts
    existing_event_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
    
    # Get available event types
    event_types = EventType.query.filter(EventType.et_is_active == True).order_by(EventType.et_order).all()
    
    # Get existing player data
    from .models import EventPlayerNames
    existing_players = EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).all()
    
    # Organize player data by position type
    player_data = {
        'random': [],
        'team': {},
        'left': [],
        'right': [],
        'locked_pairs': []
    }
    
    for player in existing_players:
        if player.epn_position_type == 'random':
            # Ensure list is long enough
            while len(player_data['random']) <= player.epn_position_index:
                player_data['random'].append('')
            player_data['random'][player.epn_position_index] = player.epn_player_name
            
            # Track locked pairs
            if hasattr(player, 'epn_is_locked') and player.epn_is_locked:
                pair_index = player.epn_position_index // 2
                if pair_index not in player_data['locked_pairs']:
                    player_data['locked_pairs'].append(pair_index)
            
        elif player.epn_position_type == 'team':
            team_id = player.epn_team_identifier
            if team_id not in player_data['team']:
                player_data['team'][team_id] = {'player1': '', 'player2': ''}
            
            if player.epn_team_position == 1:
                player_data['team'][team_id]['player1'] = player.epn_player_name
            elif player.epn_team_position == 2:
                player_data['team'][team_id]['player2'] = player.epn_player_name
                
            # Track locked pairs for manual pairing
            if hasattr(player, 'epn_is_locked') and player.epn_is_locked:
                pair_index = ord(team_id) - ord('A')
                if pair_index not in player_data['locked_pairs']:
                    player_data['locked_pairs'].append(pair_index)
                
        elif player.epn_position_type == 'left':
            while len(player_data['left']) <= player.epn_position_index:
                player_data['left'].append('')
            player_data['left'][player.epn_position_index] = player.epn_player_name
            
        elif player.epn_position_type == 'right':
            while len(player_data['right']) <= player.epn_position_index:
                player_data['right'].append('')
            player_data['right'][player.epn_position_index] = player.epn_player_name

    if request.method == 'POST':
        tab = request.form.get('tab', 'players')
        
        try:
            if tab == 'players':
                # Handle player registration update with pair locking
                return update_event_players_with_locking(event_id)
                
            elif tab == 'basic':
                # Handle basic information update
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
                
            elif tab == 'courts':
                # Handle courts and settings update
                event_type_id = request.form.get('event_type_id')
                if event_type_id:
                    # Validate event type exists and is active
                    event_type = EventType.query.filter_by(et_id=int(event_type_id), et_is_active=True).first()
                    if not event_type:
                        flash(translate('Invalid event type selected!'), 'error')
                    else:
                        event.ev_type_id = int(event_type_id)
                        
                event.ev_max_players = int(request.form['max_players'])
                
                # Clear existing event courts
                EventCourts.query.filter_by(evc_event_id=event_id).delete()

                # Determine fallback court (first available for this club)
                fallback_court_id = all_courts[0].ct_id if all_courts else None

                # Add selected courts
                court_count = int(request.form.get('court_count', 1))
                for i in range(court_count):
                    court_id = request.form.get(f'court_{i}') or fallback_court_id
                    
                    if court_id:
                        event_court = EventCourts(
                            evc_event_id=event_id,
                            evc_court_id=court_id
                        )
                        db.session.add(event_court)
                
                db.session.commit()
                flash(translate('Courts and settings updated!'), 'success')

        except ValueError as e:
            flash(translate('Invalid date/time format!'), 'error')
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating event: {}').format(str(e)), 'error')

    return render_template("edit_event.html", 
                         user=current_user, 
                         event=event, 
                         clubs=authorized_clubs,
                         courts=all_courts,
                         existing_event_courts=existing_event_courts,
                         event_types=event_types,
                         player_data=player_data)

def update_event_players_with_locking(event_id):
    """Update event players with pair locking functionality"""
    from .models import EventPlayerNames
    
    event = Event.query.get_or_404(event_id)
    
    try:
        # Clear existing player names and registrations for this event
        EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).delete()
        EventRegistration.query.filter_by(er_event_id=event.ev_id).delete()
        
        pairing_type = request.form.get('pairing_type') or event.ev_pairing_type or 'Random'
        max_players = event.ev_max_players
        players_registered = 0
        
        # Update pairing type if changed
        event.ev_pairing_type = pairing_type
        
        # Get locked pairs
        locked_pairs_str = request.form.get('locked_pairs', '')
        locked_pairs = set()
        if locked_pairs_str:
            try:
                locked_pairs = set(int(x) for x in locked_pairs_str.split(',') if x.strip())
            except:
                pass
        
        def get_or_create_user(player_name):
            """Get existing user or create new player user"""
            if not player_name or not player_name.strip():
                return None
                
            # Try to find existing user by name (case insensitive)
            user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
            if not user:
                # Try word-by-word match (e.g. "Luciano Oliveira" matches "Luciano \"Fugi\" Oliveira")
                words = [w for w in player_name.strip().split() if w]
                if words:
                    q = Users.query
                    for word in words:
                        q = q.filter(Users.us_name.ilike(f'%{word}%'))
                    user = q.first()
            
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
        
        if pairing_type in ('Random', 'Ranking', 'Manual'):
            # Handle pair-based input
            max_pairs = max_players // 2
            for pair_idx in range(max_pairs):
                player1_name = request.form.get(f'pair_{pair_idx}_player1')
                player2_name = request.form.get(f'pair_{pair_idx}_player2')
                
                # Process player 1
                if player1_name and player1_name.strip():
                    user1 = get_or_create_user(player1_name.strip())
                    if user1:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=player1_name.strip(),
                            epn_position_type='team' if pairing_type == 'Manual' else 'random',
                            epn_position_index=pair_idx,
                            epn_team_identifier=chr(65 + pair_idx) if pairing_type == 'Manual' else None,
                            epn_team_position=1 if pairing_type == 'Manual' else None,
                            epn_created_by_id=current_user.us_id,
                            epn_is_locked=pair_idx in locked_pairs
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user1.us_id,
                            er_registered_by_id=current_user.us_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                
                # Process player 2
                if player2_name and player2_name.strip():
                    user2 = get_or_create_user(player2_name.strip())
                    if user2:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=player2_name.strip(),
                            epn_position_type='team' if pairing_type == 'Manual' else 'random',
                            epn_position_index=pair_idx,
                            epn_team_identifier=chr(65 + pair_idx) if pairing_type == 'Manual' else None,
                            epn_team_position=2 if pairing_type == 'Manual' else None,
                            epn_created_by_id=current_user.us_id,
                            epn_is_locked=pair_idx in locked_pairs
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user2.us_id,
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
        return redirect(url_for('views.edit_event', event_id=event_id))
        
    except Exception as e:
        db.session.rollback()
        flash(translate('Error updating event players: {}').format(str(e)), 'error')
        return redirect(url_for('views.edit_event', event_id=event_id))

@views.route('/edit_event_step1/<int:event_id>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_step1(event_id):
    """Step 1: Edit basic event information"""
    event = Event.query.get_or_404(event_id)
    
    # Prevent editing closed events
    if event.ev_status == 'event_ended':
        flash(translate('Cannot edit a closed event'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Check authorization (superuser, club authorization, or public event with access code)
    is_public_event = event.ev_club_id == 2  # Public Events club ID
    
    if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    # Get authorized clubs for the dropdown (only for authenticated users)
    if current_user.is_authenticated:
        if current_user.us_is_superuser == 1:
            authorized_clubs = Club.query.filter_by(cl_active=True).all()
        else:
            authorized_clubs = db.session.query(Club).join(
                ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id
            ).filter(
                ClubAuthorization.ca_user_id == current_user.us_id,
                Club.cl_active == True
            ).all()
    else:
        # For public events, only show the Public Events club
        authorized_clubs = [Club.query.get(2)]

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
            #flash(translate('Basic event information updated!'), 'success')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.edit_event_step2', event_id=event_id, code=access_code) if access_code else url_for('views.edit_event_step2', event_id=event_id))

        except ValueError as e:
            flash(translate('Invalid date/time format!'), 'error')
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating event: {}').format(str(e)), 'error')

    # Get access code from session if editing public event
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    return render_template("edit_event_step1.html", user=current_user, event=event, clubs=authorized_clubs, access_code=access_code)

@views.route('/delete_event/<int:event_id>', methods=['POST'])
@login_or_access_code_required
def delete_event(event_id):
    """Delete an event and all its related data (admin/superuser only)"""
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authenticated and has admin/superuser permissions
    if not current_user.is_authenticated or (not current_user.us_is_superuser and not current_user.us_is_admin):
        flash(translate('You do not have permission to delete events.'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Double-check authorization for regular admins if event is not from public club
    if not current_user.us_is_superuser and event.ev_club_id != 2:  # Not superuser and not public event
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to delete this event'), 'error')
            return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    event_title = event.ev_title
    
    try:
        # Delete all event-related data in correct order (most dependent first)
        
        # 1. Delete ELO ranking history for games related to this event
        event_games = Game.query.filter_by(gm_idEvent=event_id).all()
        for game in event_games:
            ELOrankingHist.query.filter_by(el_gm_id=game.gm_id).delete()
        
        # 2. Delete games related to this event
        Game.query.filter_by(gm_idEvent=event_id).delete()
        
        # 3. Delete event classifications
        EventClassification.query.filter_by(ec_event_id=event_id).delete()
        
        # 4. Delete event registrations
        EventRegistration.query.filter_by(er_event_id=event_id).delete()
        
        # 5. Delete event courts
        EventCourts.query.filter_by(evc_event_id=event_id).delete()
        
        # 6. Delete event player names
        EventPlayerNames.query.filter_by(epn_event_id=event_id).delete()
        
        # 7. Delete Mexican configuration if it exists
        MexicanConfig.query.filter_by(mc_event_id=event_id).delete()
        
        # 8. Finally delete the event itself
        db.session.delete(event)
        
        # Commit all changes
        db.session.commit()
        
        flash(translate('Event "{}" and all its data have been deleted successfully.').format(event_title), 'success')
        return redirect(url_for('views.managementEvents'))
        
    except Exception as e:
        # Rollback on any error
        db.session.rollback()
        flash(translate('An error occurred while deleting the event: {}').format(str(e)), 'error')
        return redirect(url_for('views.edit_event_step1', event_id=event_id))

@views.route('/edit_event_step2/<int:event_id>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_step2(event_id):
    """Step 2: Edit court configuration and pairing type"""
    event = Event.query.get_or_404(event_id)
    
    # Prevent editing closed events
    if event.ev_status == 'event_ended':
        flash(translate('Cannot edit a closed event'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Check authorization (superuser, club authorization, or public event with access code)
    is_public_event = event.ev_club_id == 2  # Public Events club ID
    
    if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
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
            # Check if pairing type or max players are changing
            old_pairing_type = event.ev_pairing_type
            old_max_players = event.ev_max_players
            new_pairing_type = request.form['pairing_type']
            new_max_players = int(request.form['max_players'])
            
            pairing_changed = old_pairing_type != new_pairing_type
            players_changed = old_max_players != new_max_players
            
            # If pairing or player count changed, check for existing games
            if pairing_changed or players_changed:
                existing_games = Game.query.filter_by(gm_idEvent=event_id).all()
                if existing_games:
                    # Check if all games are unplayed
                    all_unplayed = all(
                        (game.gm_result_A is None or game.gm_result_A == 0) and 
                        (game.gm_result_B is None or game.gm_result_B == 0)
                        for game in existing_games
                    )
                    
                    if all_unplayed:
                        # Delete all unplayed games so they can be recreated
                        for game in existing_games:
                            db.session.delete(game)
                        flash(translate('Existing games deleted. New games will be created with updated settings.'), 'info')
                    else:
                        # Some games have been played, don't allow changes
                        flash(translate('Cannot change pairing or player count - some games have already been played.'), 'error')
                        access_code = session.get(f'event_{event_id}_access_code', '')
                        return render_template("edit_event_step2.html", user=current_user, event=event, 
                                              club=club, courts=all_courts, existing_event_courts=existing_event_courts,
                                              event_types=EventType.query.filter(EventType.et_is_active == True).all(),
                                              access_code=access_code)
            
            # Update event type and pairing
            event_type_id = request.form.get('event_type_id')
            if event_type_id:
                # Validate event type exists and is active
                event_type = EventType.query.filter_by(et_id=int(event_type_id), et_is_active=True).first()
                if not event_type:
                    flash(translate('Invalid event type selected!'), 'error')
                    access_code = session.get(f'event_{event_id}_access_code', '')
                    return render_template("edit_event_step2.html", user=current_user, event=event, 
                                          club=club, courts=all_courts, existing_event_courts=existing_event_courts,
                                          event_types=EventType.query.filter(EventType.et_is_active == True).all(),
                                          access_code=access_code)
                event.ev_type_id = int(event_type_id)
                
            event.ev_pairing_type = request.form['pairing_type']
            event.ev_max_players = int(request.form['max_players'])
            
            # Collect court IDs from form
            fallback_court_id = all_courts[0].ct_id if all_courts else None
            court_count = int(request.form.get('court_count', 2))
            selected_court_ids = []
            for i in range(court_count):
                court_id = request.form.get(f'court_{i}') or str(fallback_court_id)
                if court_id:
                    selected_court_ids.append(court_id)

            # Server-side duplicate guard
            if len(selected_court_ids) != len(set(selected_court_ids)):
                flash(translate('Each court must be different. Please select a unique court for each slot.'), 'error')
                access_code = session.get(f'event_{event_id}_access_code', '')
                return render_template("edit_event_step2.html", user=current_user, event=event,
                                      club=club, courts=all_courts, existing_event_courts=existing_event_courts,
                                      event_types=EventType.query.filter(EventType.et_is_active == True).all(),
                                      access_code=access_code)

            # Clear existing event courts and save new ones
            EventCourts.query.filter_by(evc_event_id=event_id).delete()
            for court_id in selected_court_ids:
                db.session.add(EventCourts(evc_event_id=event_id, evc_court_id=court_id))
            
            db.session.commit()
            # flash(translate('Court configuration updated!'), 'success')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.edit_event_step3', event_id=event_id, code=access_code))
            
        except Exception as e:
            db.session.rollback()
            flash(translate('Error updating court configuration: {}').format(str(e)), 'error')
    
    # Get available event types for the form
    event_types = EventType.query.filter(EventType.et_is_active == True).order_by(EventType.et_order).all()
    
    # Get access code from session if editing public event
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    return render_template("edit_event_step2.html", user=current_user, event=event, 
                          club=club, courts=all_courts, existing_event_courts=existing_event_courts,
                          event_types=event_types, access_code=access_code)

def update_event_players(event_id):
    """Update event players with user creation and registration logic"""
    from .models import EventPlayerNames
    
    event = Event.query.get_or_404(event_id)
    
    # Determine the user ID to use for created_by and registered_by
    if current_user.is_authenticated:
        creator_user_id = current_user.us_id
    else:
        # For public events, use system user ID (2) or fallback to first admin user
        system_user = Users.query.get(2)
        if system_user:
            creator_user_id = 2
        else:
            # Fallback: find first admin/superuser
            admin_user = Users.query.filter(
                (Users.us_is_admin == True) | (Users.us_is_superuser == True)
            ).first()
            creator_user_id = admin_user.us_id if admin_user else 1
    
    try:
        # Collect all player names first for validation
        all_player_names = []
        pairing_type = event.ev_pairing_type or 'Random'
        max_players = event.ev_max_players
        if pairing_type in ('Random', 'Ranking'):
            for i in range(max_players):
                player_name = request.form.get(f'player_{i}')
                if player_name and player_name.strip():
                    all_player_names.append(player_name.strip())
                    
        elif pairing_type == 'Manual':
            teams_needed = max_players // 2
            for team_idx in range(teams_needed):
                team_letter = chr(65 + team_idx)  # A, B, C...
                player1_name = request.form.get(f'team_{team_letter}_player1')
                player2_name = request.form.get(f'team_{team_letter}_player2')
                
                if player1_name and player1_name.strip():
                    all_player_names.append(player1_name.strip())
                if player2_name and player2_name.strip():
                    all_player_names.append(player2_name.strip())
                    
        elif pairing_type == 'L&R Random':
            left_players = max_players // 2
            right_players = max_players // 2
            
            for i in range(left_players):
                left_player = request.form.get(f'left_player_{i}')
                if left_player and left_player.strip():
                    all_player_names.append(left_player.strip())
                    
            for i in range(right_players):
                right_player = request.form.get(f'right_player_{i}')
                if right_player and right_player.strip():
                    all_player_names.append(right_player.strip())
        
        # Check if all player names are empty (user wants to delete all players)
        if len(all_player_names) == 0:
            # User has cleared all player names - delete all registrations
            EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).delete()
            EventRegistration.query.filter_by(er_event_id=event.ev_id).delete()
            db.session.commit()
            
            # Clear cached form data
            session.pop(f'event_{event_id}_form_data', None)
            
            flash(translate('All players have been removed from this event.'), 'success')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.edit_event_step3', event_id=event_id, code=access_code) if access_code else url_for('views.edit_event_step3', event_id=event_id))
        
        # Validation 1: Check for duplicate names (case insensitive)
        names_lower = [name.lower() for name in all_player_names]
        if len(names_lower) != len(set(names_lower)):
            # Store form data in session to preserve it after redirect
            session[f'event_{event_id}_form_data'] = dict(request.form)
            flash(translate('Duplicate player names found. Each player must have a unique name.'), 'error')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.edit_event_step3', event_id=event_id, code=access_code) if access_code else url_for('views.edit_event_step3', event_id=event_id))
        
        # Validation 2: Check if we have the expected number of players for game creation
        if len(all_player_names) == max_players and event.event_type and event.event_type.et_name == 'Mexicano':
            # All players are present for a Mexicano tournament - validate completeness
            pass  # Validation passed, proceed with saving
        
        # Step 1: Always update player registrations first (delete old, insert new).
        # Games/classification logic comes AFTER.
        EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).delete()
        EventRegistration.query.filter_by(er_event_id=event.ev_id).delete()

        # Determine game state for post-save logic
        existing_games = Game.query.filter_by(gm_idEvent=event.ev_id).all()
        games_with_results = [
            g for g in existing_games
            if not ((g.gm_result_A is None or g.gm_result_A == 0) and
                    (g.gm_result_B is None or g.gm_result_B == 0))
        ] if existing_games else []

        players_registered = 0
        
        def get_or_create_user(player_name):
            """Get existing user or create new player user"""
            if not player_name or not player_name.strip():
                return None
                
            # Try to find existing user by name (case insensitive)
            user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
            if not user:
                # Try word-by-word match (e.g. "Luciano Oliveira" matches "Luciano \"Fugi\" Oliveira")
                words = [w for w in player_name.strip().split() if w]
                if words:
                    q = Users.query
                    for word in words:
                        q = q.filter(Users.us_name.ilike(f'%{word}%'))
                    user = q.first()
            
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
        
        if pairing_type in ('Random', 'Ranking'):
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
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        # Create event registration
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
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
                                epn_created_by_id=creator_user_id
                            )
                            db.session.add(player_record)
                            
                            registration = EventRegistration(
                                er_event_id=event.ev_id,
                                er_player_id=user.us_id,
                                er_registered_by_id=creator_user_id,
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
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
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
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
        
        # PHASE 1 COMMIT: persist player registrations immediately.
        # This is committed before any game logic so a failure in game management
        # never rolls back the player data.
        db.session.commit()
        session.pop(f'event_{event_id}_form_data', None)
        flash(translate('Event players updated successfully! {} players registered.').format(players_registered), 'success')

    except Exception as e:
        db.session.rollback()
        import traceback; traceback.print_exc()
        # Preserve form data so the user doesn't lose their input
        session[f'event_{event_id}_form_data'] = dict(request.form)
        flash(translate('Error saving players: {}').format(str(e)), 'error')
        access_code = session.get(f'event_{event_id}_access_code', '')
        return redirect(url_for('views.edit_event_step3', event_id=event_id, code=access_code) if access_code else url_for('views.edit_event_step3', event_id=event_id))

    # ---- PHASE 2: Handle games (separate transaction – players already saved) ----
    access_code = session.get(f'event_{event_id}_access_code', '')
    if players_registered == event.ev_max_players and event.event_type and event.event_type.et_name in ['Mexicano', 'NonStop', 'Americano']:
        try:
            if games_with_results:
                flash(translate('Player names updated. Existing played games were kept unchanged.'), 'info')
            else:
                if existing_games:
                    gameday_id = existing_games[0].gm_idGameDay
                    Game.query.filter_by(gm_idEvent=event_id).delete()
                    GameDayPlayer.query.filter_by(gp_idGameDay=gameday_id).delete()
                    GameDayClassification.query.filter_by(gc_idGameDay=gameday_id).delete()
                    EventClassification.query.filter_by(ec_event_id=event_id).delete()
                    GameDay.query.filter_by(gd_id=gameday_id).delete()
                    db.session.commit()
                    existing_games = []
                num_games = create_games_for_event(event_id)
                db.session.commit()
                flash(translate('All players registered! {} games have been automatically created.').format(num_games), 'success')
        except Exception as e:
            db.session.rollback()
            import traceback; traceback.print_exc()
            flash(translate('Players saved but could not manage games: {}').format(str(e)), 'warning')

    return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

def generate_round_robin_schedule(num_teams):
    """Generate a round-robin schedule where each team plays every other team exactly once.
    
    Args:
        num_teams: Number of teams (must be even)
    
    Returns:
        List of rounds, where each round is a list of matchups (team_index_a, team_index_b)
    """
    if num_teams % 2 != 0:
        raise ValueError("Number of teams must be even for round-robin scheduling")
    
    # Using circle method for round-robin scheduling
    # Fix team 0, rotate all others
    teams = list(range(num_teams))
    rounds = []
    num_rounds = num_teams - 1
    
    for round_num in range(num_rounds):
        round_matchups = []
        # First matchup: team 0 vs last team in current rotation
        round_matchups.append((teams[0], teams[-1]))
        
        # Remaining matchups: pair teams from opposite ends moving inward
        for i in range(1, num_teams // 2):
            round_matchups.append((teams[i], teams[num_teams - i - 1]))
        
        rounds.append(round_matchups)
        
        # Rotate teams (keep team 0 fixed, rotate others clockwise)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    
    return rounds

def create_games_for_event(event_id):
    """Helper function to create games for an event"""
    import random
    from datetime import datetime, date, time, timedelta
    
    event = Event.query.get_or_404(event_id)
    
    # Validation 1: Check that we have all player names needed
    registrations = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=False).all()
    
    if len(registrations) != event.ev_max_players:
        raise Exception(translate('Need exactly {} players to create games. Currently have {} players.').format(event.ev_max_players, len(registrations)))
    
    # Validation 2: Check for duplicate names
    player_names_list = [reg.player.us_name.strip().lower() for reg in registrations]
    if len(player_names_list) != len(set(player_names_list)):
        raise Exception(translate('Duplicate player names found. Each player must have a unique name.'))
    
    # Get event courts
    event_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
    if not event_courts:
        raise Exception(translate('No courts configured for this event'))
    
    # Create a dummy GameDay for events (required by Game model)
    # Check if we already have a dummy league for events
    dummy_league = League.query.filter_by(lg_name='Event System').first()
    if not dummy_league:
        # Create a dummy league for events
        dummy_league = League(
            lg_name='Event System',
            lg_club_id=1,  # System club
            lg_startDate=date.today(),
            lg_endDate=date.today() + timedelta(days=365),
            lg_status='active',
            lg_nbrDays=1,
            lg_max_players=100
        )
        db.session.add(dummy_league)
        db.session.flush()
    
    dummy_gameday = GameDay(
        gd_idLeague=dummy_league.lg_id,
        gd_date=event.ev_date,
        gd_gameDayName=f"Event {event.ev_title} - Games",
        gd_status='active'
    )
    db.session.add(dummy_gameday)
    db.session.flush()  # Get the gameday ID
    
    # Register all players for this gameday
    for registration in registrations:
        gameday_player = GameDayPlayer(
            gp_idLeague=dummy_league.lg_id,
            gp_idGameDay=dummy_gameday.gd_id,
            gp_idPlayer=registration.er_player_id
        )
        db.session.add(gameday_player)
    
    # Get event type
    event_type = EventType.query.get(event.ev_type_id)
    event_type_name = event_type.et_name if event_type else 'Unknown'
    print(f"DEBUG create_games_for_event: Event type ID={event.ev_type_id}, Event type name='{event_type_name}'")
    is_nonstop = event_type_name == 'NonStop'
    print(f"DEBUG create_games_for_event: is_nonstop={is_nonstop}, checking against 'NonStop'")
    
    # Get player assignment based on pairing type
    pairing_type = event.ev_pairing_type
    
    if pairing_type == 'Manual':
        # For Manual pairing, respect the team assignments
        # Get EventPlayerNames ordered by team and position
        player_names = EventPlayerNames.query.filter_by(
            epn_event_id=event_id
        ).order_by(
            EventPlayerNames.epn_position_index,
            EventPlayerNames.epn_team_position
        ).all()
        
        # Build ordered list: Team A player 1, Team A player 2, Team B player 1, Team B player 2, etc.
        player_ids = []
        for player_name_record in player_names:
            # Find the user with this name
            user = Users.query.filter(Users.us_name.ilike(player_name_record.epn_player_name.strip())).first()
            if user:
                player_ids.append(user.us_id)
    
    elif pairing_type == 'L&R Random':
        # For L&R Random, get left players and right players separately, then randomize within each group
        left_players = EventPlayerNames.query.filter_by(
            epn_event_id=event_id,
            epn_position_type='left'
        ).order_by(EventPlayerNames.epn_position_index).all()
        
        right_players = EventPlayerNames.query.filter_by(
            epn_event_id=event_id,
            epn_position_type='right'
        ).order_by(EventPlayerNames.epn_position_index).all()
        
        # Get user IDs
        left_ids = []
        for player_name_record in left_players:
            user = Users.query.filter(Users.us_name.ilike(player_name_record.epn_player_name.strip())).first()
            if user:
                left_ids.append(user.us_id)
        
        right_ids = []
        for player_name_record in right_players:
            user = Users.query.filter(Users.us_name.ilike(player_name_record.epn_player_name.strip())).first()
            if user:
                right_ids.append(user.us_id)
        
        # Shuffle within each group
        random.shuffle(left_ids)
        random.shuffle(right_ids)
        
        # Pair them up: left[0] with right[0], left[1] with right[1], etc.
        player_ids = []
        for i in range(min(len(left_ids), len(right_ids))):
            player_ids.extend([left_ids[i], right_ids[i]])
    
    elif pairing_type == 'Ranking':
        # Sort players by ELO ranking for this club (desc), then alphabetically for ties.
        # Players not found in club rankings start at 1000.
        club_id = event.ev_club_id
        elo_map = {}
        if club_id:
            club_elo = func_calculate_ELO_by_club(club_id)
            elo_map = {entry['player'].us_id: entry['rankingNow'] for entry in club_elo}

        players_with_elo = []
        for reg in registrations:
            pid = reg.er_player_id
            elo = elo_map.get(pid, 1000.0)
            name = reg.player.us_name.lower()
            players_with_elo.append((pid, elo, name))

        # Sort: highest ELO first, alphabetical on tie
        players_with_elo.sort(key=lambda x: (-x[1], x[2]))
        sorted_ids = [p[0] for p in players_with_elo]

        # Reorder into game groups so A=[rank0+rank3] vs B=[rank1+rank2] per court.
        # player_ids positions map to: A1=[0], A2=[1], B1=[2], B2=[3]
        # To get A=[rank0,rank3] we interleave as [rank0, rank3, rank1, rank2] per group.
        player_ids = []
        for i in range(0, len(sorted_ids), 4):
            group = sorted_ids[i:i+4]
            if len(group) == 4:
                player_ids.extend([group[0], group[3], group[1], group[2]])

    else:  # 'Random' or default
        # For Random pairing, shuffle all players
        player_ids = [reg.player.us_id for reg in registrations]
        random.shuffle(player_ids)
    
    # For NonStop events, create teams (pairs) that will stay fixed throughout
    if is_nonstop:
        print(f"DEBUG create_games_for_event: ENTERING NONSTOP CODE PATH - Creating all rounds")
        # Group players into fixed teams (pairs)
        teams = []
        for i in range(0, len(player_ids), 2):
            teams.append((player_ids[i], player_ids[i+1]))
        
        num_teams = len(teams)
        
        # Calculate timing based on player count
        if event.ev_max_players == 8:
            # 8 players: Start after 5min warmup, 25min rounds, 5min intervals
            # Total: 5 + 25 + 5 + 25 + 5 + 25 = 90 minutes
            warmup_minutes = 5
            round_duration = 25
            interval_minutes = 5
            num_rounds = 3
        elif event.ev_max_players == 12:
            # 12 players: Start after 5min warmup, 20min rounds, 3.75min intervals (use 4)
            # Total: 5 + 20 + 4 + 20 + 4 + 20 + 4 + 20 + 4 + 20 = 5 + 100 + 16 = 121 minutes
            # Adjust to 3min intervals: 5 + 100 + 12 = 117 minutes
            warmup_minutes = 5
            round_duration = 20
            interval_minutes = 3
            num_rounds = 5
        elif event.ev_max_players == 16:
            # 16 players: Start immediately, 15min rounds, 2.5min intervals
            # Total: 0 + 15*7 + 2.5*6 = 105 + 15 = 120 minutes
            warmup_minutes = 0
            round_duration = 15
            interval_minutes = 2
            num_rounds = 7
        else:
            # Default for other player counts
            warmup_minutes = 5
            round_duration = 20
            interval_minutes = 5
            num_rounds = event.ev_max_players // 2 - 1
        
        # Generate round-robin schedule
        round_robin_schedule = generate_round_robin_schedule(num_teams)
        
        # Create games for all rounds
        event_time = event.ev_start_time if event.ev_start_time else time(9, 0)
        
        total_games_created = 0
        for round_idx, round_matchups in enumerate(round_robin_schedule):
            # Calculate round start time
            if round_idx == 0:
                # First round starts after warmup
                round_start_minutes = warmup_minutes
            else:
                # Subsequent rounds: warmup + (round_duration + interval) * round_idx
                round_start_minutes = warmup_minutes + (round_duration + interval_minutes) * round_idx
            
            # Convert to time object
            total_minutes = event_time.hour * 60 + event_time.minute + round_start_minutes
            round_start_hour = (total_minutes // 60) % 24
            round_start_minute = total_minutes % 60
            round_start_time = time(round_start_hour, round_start_minute)
            
            # Calculate round end time
            total_end_minutes = total_minutes + round_duration
            round_end_hour = (total_end_minutes // 60) % 24
            round_end_minute = total_end_minutes % 60
            round_end_time = time(round_end_hour, round_end_minute)
            
            # Create games for this round
            for game_idx, (team_a_idx, team_b_idx) in enumerate(round_matchups):
                court_index = game_idx % len(event_courts)
                court_id = event_courts[court_index].evc_court_id
                
                team_a = teams[team_a_idx]
                team_b = teams[team_b_idx]
                
                game = Game(
                    gm_idLeague=dummy_league.lg_id,
                    gm_idGameDay=dummy_gameday.gd_id,
                    gm_idEvent=event_id,
                    gm_date=event.ev_date,
                    gm_timeStart=round_start_time,
                    gm_timeEnd=round_end_time,
                    gm_court=court_id,
                    gm_idPlayer_A1=team_a[0],
                    gm_idPlayer_A2=team_a[1],
                    gm_idPlayer_B1=team_b[0],
                    gm_idPlayer_B2=team_b[1],
                    gm_teamA='A',
                    gm_teamB='B'
                )
                db.session.add(game)
                total_games_created += 1
        
        num_games = total_games_created
        print(f"DEBUG create_games_for_event: NonStop - Created {num_games} games total")
    
    else:
        print(f"DEBUG create_games_for_event: ENTERING MEXICANO/AMERICANO CODE PATH - Creating only first round")
        # For Mexicano/Americano: Create only first round (subsequent rounds created after scoring)
        num_games = len(player_ids) // 4
        
        # Create games
        game_time_start = time(9, 0)  # 09:00
        game_time_end = time(9, 13)   # 09:13 (13 minute duration)
        
        for i in range(num_games):
            court_index = i % len(event_courts)
            court_id = event_courts[court_index].evc_court_id
            
            # Get 4 players for this game
            players_for_game = player_ids[i*4:(i+1)*4]
            
            game = Game(
                gm_idLeague=dummy_league.lg_id,
                gm_idGameDay=dummy_gameday.gd_id,
                gm_idEvent=event_id,
                gm_date=event.ev_date,
                gm_timeStart=game_time_start,
                gm_timeEnd=game_time_end,
                gm_court=court_id,
                gm_idPlayer_A1=players_for_game[0],
                gm_idPlayer_A2=players_for_game[1],
                gm_idPlayer_B1=players_for_game[2],
                gm_idPlayer_B2=players_for_game[3],
                gm_teamA='A',
                gm_teamB='B'
            )
            db.session.add(game)
    
    # Create initial classification records for all players (0 points)
    # Always wipe existing ones first to avoid UNIQUE constraint violations on re-creation
    EventClassification.query.filter_by(ec_event_id=event_id).delete()
    GameDayClassification.query.filter_by(gc_idGameDay=dummy_gameday.gd_id).delete()

    for registration in registrations:
        # Create EventClassification for overall event results
        event_classification = EventClassification(
            ec_event_id=event_id,
            ec_player_id=registration.er_player_id,
            ec_points=0,
            ec_wins=0,
            ec_losses=0,
            ec_games_favor=0,
            ec_games_against=0,
            ec_games_diff=0,
            ec_ranking=0.0
        )
        db.session.add(event_classification)
        
        # Create GameDayClassification for this specific gameday
        gameday_classification = GameDayClassification(
            gc_idLeague=dummy_league.lg_id,
            gc_idGameDay=dummy_gameday.gd_id,
            gc_idPlayer=registration.er_player_id,
            gc_points=0,
            gc_wins=0,
            gc_losses=0,
            gc_gamesFavor=0,
            gc_gamesAgainst=0,
            gc_gamesDiff=0,
            gc_ranking=0.0
        )
        db.session.add(gameday_classification)
    
    # Note: Don't commit here - let the calling function handle the commit
    return num_games

@views.route('/clear_event_round/<int:event_id>/<start_time>', methods=['POST'])
@login_or_access_code_required
def clear_event_round(event_id, start_time):
    """Clear an entire round of games - behavior depends on event type"""
    print(f"DEBUG clear_event_round: Called with event_id={event_id}, start_time={start_time}")
    
    try:
        event = Event.query.get_or_404(event_id)
        print(f"DEBUG clear_event_round: Found event {event.ev_id}")
    
        # Check authorization (superuser, club authorization, or public event with access code)
        is_public_event = event.ev_club_id == 2  # Public Events club ID
        print(f"DEBUG clear_event_round: is_public_event={is_public_event}")
    
        if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
            print(f"DEBUG clear_event_round: Checking authorization for user {current_user.us_id}")
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                print(f"DEBUG clear_event_round: Not authorized")
                flash(translate('You are not authorized to delete rounds for this event'), 'error')
                access_code = session.get(f'event_{event_id}_access_code', '')
                return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

        print(f"DEBUG clear_event_round: Authorization passed, parsing time")
        from datetime import datetime, time
        
        # Parse the start_time from URL parameter (format: HH:MM)
        target_hour, target_minute = map(int, start_time.split(':'))
        target_time = time(target_hour, target_minute)
        
        # Check if this is a NonStop event
        is_nonstop = event.event_type and event.event_type.et_name == 'NonStop'
        print(f"DEBUG: Event type: {event.event_type.et_name if event.event_type else 'None'}, is_nonstop: {is_nonstop}")
        
        # Get all games for this event
        all_games = Game.query.filter_by(gm_idEvent=event_id).order_by(Game.gm_timeStart).all()
        
        if not all_games:
            flash(translate('No games found for this event'), 'warning')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))
        
        # For NonStop events, validate sequential clearing
        if is_nonstop:
            # Find the latest round with results
            latest_round_with_results = None
            unique_times = set()
            
            for game in all_games:
                if hasattr(game.gm_timeStart, 'time'):
                    game_time = game.gm_timeStart.time()
                else:
                    game_time = game.gm_timeStart
                unique_times.add((game_time.hour, game_time.minute))
                
                # Check if this game has results
                if game.gm_result_A is not None or game.gm_result_B is not None:
                    if latest_round_with_results is None or (game_time.hour, game_time.minute) > latest_round_with_results:
                        latest_round_with_results = (game_time.hour, game_time.minute)
            
            # Check if the requested round is the latest one with results
            target_tuple = (target_time.hour, target_time.minute)
            if latest_round_with_results and target_tuple != latest_round_with_results:
                flash(translate('For NonStop events, you can only clear the latest round with results. Please clear round {}:{:02d} first.').format(
                    latest_round_with_results[0], latest_round_with_results[1]), 'error')
                access_code = session.get(f'event_{event_id}_access_code', '')
                return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))
        
        # Find games in the target round and all games that start after it
        target_round_games = []
        games_to_delete = []
        
        print(f"DEBUG: Searching for games with hour={target_time.hour} and minute={target_time.minute}")
        
        for game in all_games:
            # Handle both datetime and time objects  
            if hasattr(game.gm_timeStart, 'time'):
                game_time = game.gm_timeStart.time()  # It's a datetime object
            else:
                game_time = game.gm_timeStart  # It's already a time object
            
            print(f"DEBUG: Checking game {game.gm_id}: {game_time} -> hour={game_time.hour}, minute={game_time.minute}")
            
            # If this is the target round, reset scores to None (match hour and minute only)
            if game_time.hour == target_time.hour and game_time.minute == target_time.minute:
                print(f"DEBUG: Match found! Adding game {game.gm_id} to target_round_games")
                target_round_games.append(game)
            # If this game starts after the target round, mark for deletion (except for NonStop)
            elif not is_nonstop and (game_time.hour > target_time.hour or 
                  (game_time.hour == target_time.hour and game_time.minute > target_time.minute)):
                print(f"DEBUG: Game {game.gm_id} is after target round, marking for deletion")
                games_to_delete.append(game)
        
        print(f"DEBUG: Found {len(target_round_games)} games in target round, {len(games_to_delete)} games to delete")
        
        if not target_round_games:
            flash(translate('No games found for the specified round time'), 'warning')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))
        
        # Reset scores for the target round
        for game in target_round_games:
            game.gm_result_A = None
            game.gm_result_B = None
        
        # Delete subsequent rounds (except for NonStop events)
        if not is_nonstop:
            for game in games_to_delete:
                db.session.delete(game)
        
        db.session.commit()
        
        # Recalculate event classifications after the changes
        calculate_event_classifications(event_id)
        db.session.commit()
        
        if is_nonstop:
            success_msg = translate('Round at {} cleared successfully! Scores reset to zero.').format(start_time)
        else:
            success_msg = translate('Round at {} cleared successfully!').format(start_time)
            if games_to_delete:
                success_msg += ' ' + translate('{} subsequent games were deleted.').format(len(games_to_delete))
        
        flash(success_msg, 'success')
        
    except ValueError:
        flash(translate('Invalid time format provided'), 'error')
    except Exception as e:
        print(f"DEBUG clear_event_round: Exception occurred: {str(e)}")
        db.session.rollback()
        flash(translate('Error clearing round: {}').format(str(e)), 'error')
    
    access_code = session.get(f'event_{event_id}_access_code', '')
    return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

@views.route('/get_round_deletion_info/<int:event_id>/<start_time>', methods=['GET'])
@login_or_access_code_required
def get_round_deletion_info(event_id, start_time):
    """Get information about what will be affected when clearing a round"""
    print(f"DEBUG get_round_deletion_info: Called with event_id={event_id}, start_time={start_time}")
    
    try:
        event = Event.query.get_or_404(event_id)
        print(f"DEBUG get_round_deletion_info: Found event {event.ev_id}")
    
        # Check authorization (superuser, club authorization, or public event with access code)
        is_public_event = event.ev_club_id == 2  # Public Events club ID
        print(f"DEBUG get_round_deletion_info: is_public_event={is_public_event}")
    
        if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
            print(f"DEBUG get_round_deletion_info: Checking authorization for user {current_user.us_id}")
            authorization = ClubAuthorization.query.filter_by(
                ca_user_id=current_user.us_id, 
                ca_club_id=event.ev_club_id
            ).first()
            
            if not authorization:
                print(f"DEBUG get_round_deletion_info: Not authorized")
                return jsonify({'error': 'Not authorized'}), 403

        print(f"DEBUG get_round_deletion_info: Authorization passed, parsing time")
        from datetime import datetime, time
        
        # Parse the start_time from URL parameter (format: HH:MM)
        target_hour, target_minute = map(int, start_time.split(':'))
        target_time = time(target_hour, target_minute)
        print(f"DEBUG get_round_deletion_info: Parsed time as {target_time}")
        
        # Check if this is a NonStop event
        is_nonstop = event.event_type and event.event_type.et_name == 'NonStop'
        print(f"DEBUG: Event type: {event.event_type.et_name if event.event_type else 'None'}, is_nonstop: {is_nonstop}")
        
        # Get all games for this event
        all_games = Game.query.filter_by(gm_idEvent=event_id).order_by(Game.gm_timeStart).all()
        print(f"DEBUG get_round_deletion_info: Found {len(all_games)} games")
        
        target_games = 0
        future_games = 0
        
        # For NonStop events, check sequential clearing logic
        if is_nonstop:
            # Find the latest round with results
            latest_round_with_results = None
            rounds_with_results = set()
            
            for game in all_games:
                if hasattr(game.gm_timeStart, 'time'):
                    game_time = game.gm_timeStart.time()
                else:
                    game_time = game.gm_timeStart
                
                # Check if this game has results
                if game.gm_result_A is not None or game.gm_result_B is not None:
                    time_tuple = (game_time.hour, game_time.minute)
                    rounds_with_results.add(time_tuple)
                    if latest_round_with_results is None or time_tuple > latest_round_with_results:
                        latest_round_with_results = time_tuple
            
            target_tuple = (target_time.hour, target_time.minute)
            
            # Check if user can clear this round
            if latest_round_with_results and target_tuple != latest_round_with_results:
                return jsonify({
                    'error': 'sequential_only',
                    'latest_round': f"{latest_round_with_results[0]:02d}:{latest_round_with_results[1]:02d}",
                    'requested_round': f"{target_time.hour:02d}:{target_time.minute:02d}"
                }), 400
        
        for game in all_games:
            # Handle both datetime and time objects
            if hasattr(game.gm_timeStart, 'time'):
                game_time = game.gm_timeStart.time()  # It's a datetime object
            else:
                game_time = game.gm_timeStart  # It's already a time object
            
            print(f"DEBUG get_round_deletion_info: Game {game.gm_id} time: {game_time}")
            
            # Count games in the target round
            if game_time.hour == target_time.hour and game_time.minute == target_time.minute:
                target_games += 1
                print(f"DEBUG get_round_deletion_info: Found target game {game.gm_id}")
            # Count games that start after the target round (only for non-NonStop)
            elif not is_nonstop and (game_time.hour > target_time.hour or 
                  (game_time.hour == target_time.hour and game_time.minute > target_time.minute)):
                future_games += 1
                print(f"DEBUG get_round_deletion_info: Found future game {game.gm_id}")
        
        return jsonify({
            'target_games': target_games,
            'future_games': future_games,
            'round_time': start_time,
            'is_nonstop': is_nonstop
        })
        
    except ValueError:
        print(f"DEBUG get_round_deletion_info: ValueError occurred")
        return jsonify({'error': 'Invalid time format'}), 400
    except Exception as e:
        print(f"DEBUG get_round_deletion_info: Exception occurred: {str(e)}")
        return jsonify({'error': str(e)}), 500

@views.route('/create_event_games/<int:event_id>', methods=['POST'])
@login_or_access_code_required 
def create_event_games(event_id):
    """Create first round games for a Mexicano event"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization (superuser, club authorization, or public event with access code)
    is_public_event = event.ev_club_id == 2  # Public Events club ID
    
    if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to create games for this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    try:
        num_games = create_games_for_event(event_id)
        flash(translate('Successfully created {} games! You can now enter results.').format(num_games), 'success')
        
    except Exception as e:
        flash(translate('Error creating games: {}').format(str(e)), 'error')
    
    # Redirect to event detail page to show games and allow result entry
    access_code = session.get(f'event_{event_id}_access_code', '')
    return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

@views.route('/update_all_game_scores/<int:event_id>', methods=['POST'])
@login_or_access_code_required
def update_all_game_scores(event_id):
    """Update all game scores for a Mexicano event and create next round"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization (superuser, club authorization, or public event with access code)
    is_public_event = event.ev_club_id == 2  # Public Events club ID
    
    if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to update scores for this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    try:
        # Get all submitted scores from form
        scores_data = {}
        all_zero_scores = True
        any_scores_submitted = False
        
        for key, value in request.form.items():
            if key.startswith('scores[') and value.strip():
                # Parse scores[game_id][A] or scores[game_id][B] format
                import re
                match = re.match(r'scores\[(\d+)\]\[([AB])\]', key)
                if match:
                    game_id = int(match.group(1))
                    team = match.group(2)
                    score = int(value.strip()) if value.strip().isdigit() else 0
                    
                    if game_id not in scores_data:
                        scores_data[game_id] = {}
                    scores_data[game_id][team] = score
                    
                    any_scores_submitted = True
                    if score != 0:
                        all_zero_scores = False
        
        if not any_scores_submitted:
            flash(translate('No scores were submitted'), 'warning')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))
        
        # Check if all submitted scores are 0-0 (special case - delete round and recalculate)
        if all_zero_scores:
            return handle_zero_scores_case(event_id)
        
        # Update games with scores
        games_updated = 0
        
        for game_id, game_scores in scores_data.items():
            game = Game.query.get(game_id)
            if game and game.gm_idEvent == event_id:
                if 'A' in game_scores and 'B' in game_scores:
                    game.gm_result_A = game_scores['A']
                    game.gm_result_B = game_scores['B']
                    games_updated += 1
        
        if games_updated == 0:
            flash(translate('No valid game scores were updated'), 'warning')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

        # Flush so the updates are visible in queries below
        db.session.flush()

        # ------------------------------------------------------------------
        # Determine whether the current round is fully complete.
        # A "round" = all games sharing the same gm_timeStart.
        # We work with the LATEST round that has at least one result.
        # ------------------------------------------------------------------
        all_event_games = Game.query.filter_by(gm_idEvent=event_id).all()

        # Group games by start time
        rounds_by_time = {}
        for g in all_event_games:
            rounds_by_time.setdefault(g.gm_timeStart, []).append(g)

        # Find the latest round with at least one result
        latest_round_time = None
        for t in sorted(rounds_by_time.keys(), reverse=True):
            if any(g.gm_result_A is not None for g in rounds_by_time[t]):
                latest_round_time = t
                break

        if latest_round_time is None:
            # Nothing has a result yet — just commit and return
            db.session.commit()
            flash(translate('{} game score(s) saved.').format(games_updated), 'success')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

        current_round_games = rounds_by_time[latest_round_time]
        round_complete = all(
            g.gm_result_A is not None and g.gm_result_B is not None
            for g in current_round_games
        )

        if not round_complete:
            # Round is still in progress — save scores but do not touch classifications
            db.session.commit()
            remaining = sum(1 for g in current_round_games if g.gm_result_A is None or g.gm_result_B is None)
            flash(translate('{} score(s) saved. {} game(s) still pending in this round.').format(games_updated, remaining), 'success')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

        # Round is fully complete — recalculate classifications
        calculate_event_classifications(event_id)

        # Check if next round should be created (no incomplete games left anywhere)
        incomplete_games = [g for g in all_event_games if g.gm_result_A is None or g.gm_result_B is None]

        if not incomplete_games:
            # Get classifications for next round (final sort happens inside create_next_round_games)
            classifications = EventClassification.query.filter_by(ec_event_id=event_id).order_by(
                EventClassification.ec_points.desc(),
                EventClassification.ec_games_diff.desc()
            ).all()
            
            # Calculate current round number
            current_round = len([g for g in all_event_games if g.gm_result_A is not None]) // (event.ev_max_players // 4)
            
            # Get event type name
            event_type_name = event.event_type.et_name if event.event_type else None
            
            # Check if we should create next round based on event type
            should_create_next_round = False
            
            if event_type_name in ['Mexicano', 'Americano']:
                # Mexicano and Americano have unlimited rounds - always create next round
                should_create_next_round = True
            elif event_type_name == 'NonStop':
                # NonStop rounds are all created upfront - never create new rounds dynamically
                should_create_next_round = False
            
            if should_create_next_round:
                next_round_games = create_next_round_games(event_id, classifications, current_round + 1)
                flash(translate('Scores updated! Round {} completed. {} games created for next round.').format(current_round, next_round_games), 'success')
            else:
                flash(translate('Tournament completed! Final results are now available.'), 'success')
        else:
            flash(translate('{} game scores updated successfully!').format(games_updated), 'success')
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(translate('Error updating scores: {}').format(str(e)), 'error')
    
    access_code = session.get(f'event_{event_id}_access_code', '')
    return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

def handle_zero_scores_case(event_id):
    """Handle the special case where all scores are 0-0 - delete round and recalculate"""
    try:
        # Get the latest round games (games without results or games just submitted with 0-0)
        all_games = Game.query.filter_by(gm_idEvent=event_id).order_by(Game.gm_timeStart.desc()).all()
        
        if not all_games:
            flash(translate('No games found to reset'), 'warning')
            access_code = session.get(f'event_{event_id}_access_code', '')
            return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))
        
        # Find the latest round (games with same start time)
        latest_start_time = all_games[0].gm_timeStart
        latest_round_games = [g for g in all_games if g.gm_timeStart == latest_start_time]
        
        # Delete the latest round games
        for game in latest_round_games:
            db.session.delete(game)
        
        # Recalculate classifications from remaining games
        calculate_event_classifications(event_id)
        
        # Create new round with recalculated rankings
        classifications = EventClassification.query.filter_by(ec_event_id=event_id).order_by(
            EventClassification.ec_points.desc(),
            EventClassification.ec_games_diff.desc()
        ).all()
        
        # Determine round number
        remaining_games = Game.query.filter_by(gm_idEvent=event_id).count()
        round_number = (remaining_games // (len(classifications) // 4)) + 1
        
        new_games = create_next_round_games(event_id, classifications, round_number)
        
        db.session.commit()
        flash(translate('Round reset due to all 0-0 scores. Classifications recalculated and {} new games created.').format(new_games), 'success')
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(translate('Error resetting round: {}').format(str(e)), 'error')
    
    access_code = session.get(f'event_{event_id}_access_code', '')
    return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))

def calculate_event_classifications(event_id):
    """Calculate classifications for all players in an event"""
    from .models import EventPlayerNames
    
    # Get all players in the event
    registrations = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=False).all()
    
    # Clear existing classifications
    EventClassification.query.filter_by(ec_event_id=event_id).delete()
    
    # Calculate stats for each player
    for registration in registrations:
        player_id = registration.er_player_id
        
        # Get all games involving this player
        games = Game.query.filter(
            Game.gm_idEvent == event_id,
            (Game.gm_idPlayer_A1 == player_id) | 
            (Game.gm_idPlayer_A2 == player_id) |
            (Game.gm_idPlayer_B1 == player_id) | 
            (Game.gm_idPlayer_B2 == player_id)
        ).filter(
            Game.gm_result_A.isnot(None),
            Game.gm_result_B.isnot(None)
        ).all()
        
        wins = 0
        losses = 0
        games_favor = 0
        games_against = 0
        
        for game in games:
            # Determine if player is on team A or B
            if player_id in [game.gm_idPlayer_A1, game.gm_idPlayer_A2]:
                # Player is on team A
                games_favor += game.gm_result_A
                games_against += game.gm_result_B
                if game.gm_result_A > game.gm_result_B:
                    wins += 1
                else:
                    losses += 1
            else:
                # Player is on team B
                games_favor += game.gm_result_B
                games_against += game.gm_result_A
                if game.gm_result_B > game.gm_result_A:
                    wins += 1
                else:
                    losses += 1
        
        # Calculate points (3 points per win)
        points = wins * 3
        games_diff = games_favor - games_against
        
        # Create classification record
        classification = EventClassification(
            ec_event_id=event_id,
            ec_player_id=player_id,
            ec_points=points,
            ec_wins=wins,
            ec_losses=losses,
            ec_games_favor=games_favor,
            ec_games_against=games_against,
            ec_games_diff=games_diff,
            ec_ranking=0.0  # Will be calculated after all players are processed
        )
        db.session.add(classification)

def create_next_round_games(event_id, classifications, round_number):
    """Create games for the next round based on current classifications"""
    from datetime import datetime, time, timedelta
    
    event = Event.query.get_or_404(event_id)
    
    # Get event courts
    event_courts = EventCourts.query.filter_by(evc_event_id=event_id).all()
    if not event_courts:
        raise Exception(translate('No courts configured for this event'))
    
    # Sort classifications: for Mexicano+Ranking events use club ELO as tiebreaker
    is_mexican_ranking = (
        event.event_type and event.event_type.et_name == 'Mexicano'
        and event.ev_pairing_type == 'Ranking'
    )
    if is_mexican_ranking:
        club_elo = func_calculate_ELO_by_club(event.ev_club_id) if event.ev_club_id else []
        elo_map = {entry['player'].us_id: entry['rankingNow'] for entry in club_elo}
        sorted_classifications = sorted(classifications, key=lambda c: (
            -c.ec_points,
            -c.ec_games_diff,
            -(elo_map.get(c.ec_player_id, 0)),
            c.player.us_name.lower()
        ))
    else:
        sorted_classifications = sorted(classifications, key=lambda c: (
            -c.ec_points,
            -c.ec_games_diff,
            c.player.us_name.lower()
        ))
    
    if len(sorted_classifications) not in (8, 12, 16):
        raise Exception(translate('Mexicano tournament requires 8, 12, or 16 players'))

    num_players = len(sorted_classifications)

    # Mexicano pairing rules: on each court, (rank1 & rank4) vs (rank2 & rank3)
    # within each group of 4 consecutive players in the ranking.
    # 8 players  → 2 courts
    # 12 players → 3 courts
    # 16 players → 4 courts
    pairings = []
    for group in range(num_players // 4):
        base = group * 4
        pairings.append((base + 0, base + 3, base + 1, base + 2))

    # Get the start time for new games (14 minutes after the last round)
    courts_per_round = num_players // 4
    last_games = Game.query.filter_by(gm_idEvent=event_id).order_by(Game.gm_timeStart.desc()).limit(courts_per_round).all()
    if last_games:
        last_start_time = last_games[0].gm_timeStart
        # Convert to datetime, add 14 minutes, convert back to time
        from datetime import datetime, timedelta
        base_datetime = datetime.combine(event.ev_date, last_start_time)
        new_start_datetime = base_datetime + timedelta(minutes=14)
        new_start_time = new_start_datetime.time()
        new_end_datetime = new_start_datetime + timedelta(minutes=13)  # 13-minute duration
        new_end_time = new_end_datetime.time()
    else:
        # First round, use event start time
        new_start_time = event.ev_start_time
        base_datetime = datetime.combine(event.ev_date, new_start_time)
        new_end_datetime = base_datetime + timedelta(minutes=13)
        new_end_time = new_end_datetime.time()
    
    # Get gameday for this event (find it through existing games)
    existing_game = Game.query.filter_by(gm_idEvent=event_id).first()
    if not existing_game:
        raise Exception(translate('No existing games found for this event'))
    
    gameday = GameDay.query.get(existing_game.gm_idGameDay)
    if not gameday:
        raise Exception(translate('No gameday found for this event'))
    
    games_created = 0
    
    for court_idx, (a1_idx, a2_idx, b1_idx, b2_idx) in enumerate(pairings):
        if court_idx < len(event_courts):
            court = event_courts[court_idx]
            
            # Get player IDs from sorted classifications
            player_a1_id = sorted_classifications[a1_idx].ec_player_id
            player_a2_id = sorted_classifications[a2_idx].ec_player_id
            player_b1_id = sorted_classifications[b1_idx].ec_player_id
            player_b2_id = sorted_classifications[b2_idx].ec_player_id
            
            # Create game
            game = Game(
                gm_idLeague=gameday.gd_idLeague,
                gm_idGameDay=gameday.gd_id,
                gm_idEvent=event_id,
                gm_date=event.ev_date,
                gm_timeStart=new_start_time,
                gm_timeEnd=new_end_time,
                gm_court=court.evc_court_id,
                gm_idPlayer_A1=player_a1_id,
                gm_idPlayer_A2=player_a2_id,
                gm_idPlayer_B1=player_b1_id,
                gm_idPlayer_B2=player_b2_id,
                gm_result_A=None,
                gm_result_B=None
            )
            db.session.add(game)
            games_created += 1
    
    return games_created

@views.route('/edit_event_step3/<int:event_id>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_step3(event_id):
    """Step 3: Edit player registration"""
    event = Event.query.get_or_404(event_id)
    
    # Prevent editing closed events
    if event.ev_status == 'event_ended':
        flash(translate('Cannot edit a closed event'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Check authorization (superuser, club authorization, or public event with access code)
    is_public_event = event.ev_club_id == 2  # Public Events club ID
    
    if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
        authorization = ClubAuthorization.query.filter_by(
            ca_user_id=current_user.us_id, 
            ca_club_id=event.ev_club_id
        ).first()
        
        if not authorization:
            flash(translate('You are not authorized to edit this event'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    # Check if we have saved form data from validation error
    form_data = session.pop(f'event_{event_id}_form_data', None)
    
    if form_data:
        # Use form data to repopulate the form (preserves user's last input)
        player_data = {
            'random': [],
            'team': {},
            'left': [],
            'right': []
        }
        
        # Repopulate based on pairing type
        pairing_type = event.ev_pairing_type or 'Random'
        if pairing_type == 'Random':
            for i in range(event.ev_max_players):
                while len(player_data['random']) <= i:
                    player_data['random'].append('')
                player_data['random'][i] = form_data.get(f'player_{i}', '')
                
        elif pairing_type == 'Manual':
            teams_needed = event.ev_max_players // 2
            for team_idx in range(teams_needed):
                team_letter = chr(65 + team_idx)  # A, B, C...
                if team_letter not in player_data['team']:
                    player_data['team'][team_letter] = {'player1': '', 'player2': ''}
                player_data['team'][team_letter]['player1'] = form_data.get(f'team_{team_letter}_player1', '')
                player_data['team'][team_letter]['player2'] = form_data.get(f'team_{team_letter}_player2', '')
                
        elif pairing_type == 'L&R Random':
            left_players = event.ev_max_players // 2
            right_players = event.ev_max_players // 2
            
            for i in range(left_players):
                while len(player_data['left']) <= i:
                    player_data['left'].append('')
                player_data['left'][i] = form_data.get(f'left_player_{i}', '')
                    
            for i in range(right_players):
                while len(player_data['right']) <= i:
                    player_data['right'].append('')
                player_data['right'][i] = form_data.get(f'right_player_{i}', '')
    else:
        # Get existing player data for pre-population from database
        from .models import EventPlayerNames
        existing_players = EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).all()
        
        # Organize player data by position type
        player_data = {
            'random': [],
            'team': {},
            'left': [],
            'right': []
        }
        
        # If no EventPlayerNames exist, try loading from EventRegistration instead
        if not existing_players:
            from .models import EventRegistration, Users
            registrations = EventRegistration.query.filter_by(
                er_event_id=event.ev_id, 
                er_is_substitute=False
            ).order_by(EventRegistration.er_id).all()
            
            if registrations:
                # Load player names from registrations
                # Since we don't know the original pairing type, assume Random
                for idx, reg in enumerate(registrations):
                    player = Users.query.get(reg.er_player_id)
                    if player:
                        player_name = player.us_name
                        # Always use random pairing when loading from registrations
                        while len(player_data['random']) <= idx:
                            player_data['random'].append('')
                        player_data['random'][idx] = player_name
        else:
            # Load from EventPlayerNames
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
    
    # Get access code from session if editing public event
    access_code = session.get(f'event_{event_id}_access_code', '')

    # Build display data: a flat ordered list of (name, user_object) tuples, one per slot.
    from .models import EventPlayerNames as EPNModel, EventRegistration as ERModel, Users as UsersModel

    max_players = event.ev_max_players
    pairing_type = event.ev_pairing_type or 'Random'
    player_slots = []

    # Priority 1: if redirected after a failed save, restore from the submitted form values.
    if form_data is not None:
        def _get_fd(key):
            val = form_data.get(key)
            if isinstance(val, list):
                return val[0].strip() if val else ''
            return (val or '').strip()

        if pairing_type == 'Manual':
            half = max_players // 2
            for ti in range(half):
                tl = chr(65 + ti)
                for pos, suffix in enumerate(('player1', 'player2'), 1):
                    nm = _get_fd(f'team_{tl}_{suffix}')
                    player_slots.append({'slot': len(player_slots), 'name': nm, 'player': None,
                                         'field': f'team_{tl}_{suffix}', 'label': f'Team {tl} – P{pos}',
                                         'team_letter': tl, 'team_pos': pos})
        elif pairing_type == 'L&R Random':
            half = max_players // 2
            for i in range(half):
                nm = _get_fd(f'left_player_{i}')
                player_slots.append({'slot': i, 'name': nm, 'player': None,
                                     'field': f'left_player_{i}', 'label': f'Left {i+1}', 'side': 'left'})
            for i in range(half):
                nm = _get_fd(f'right_player_{i}')
                player_slots.append({'slot': half + i, 'name': nm, 'player': None,
                                     'field': f'right_player_{i}', 'label': f'Right {i+1}', 'side': 'right'})
        else:
            for i in range(max_players):
                nm = _get_fd(f'player_{i}')
                player_slots.append({'slot': i, 'name': nm, 'player': None,
                                     'field': f'player_{i}', 'label': f'Player {i+1}'})

    # Priority 2: load from DB (normal page load, or when form_data produced nothing).
    if not player_slots:
        epn_records = EPNModel.query.filter_by(epn_event_id=event.ev_id).all()
        er_records  = ERModel.query.filter_by(
            er_event_id=event.ev_id, er_is_substitute=False
        ).order_by(ERModel.er_id).all()

        random_names = {}
        team_names   = {}
        left_names   = {}
        right_names  = {}

        for p in epn_records:
            if p.epn_position_type == 'random':
                random_names[p.epn_position_index] = p.epn_player_name
            elif p.epn_position_type == 'team' and p.epn_team_identifier:
                tl = p.epn_team_identifier
                if tl not in team_names:
                    team_names[tl] = {}
                team_names[tl][p.epn_team_position] = p.epn_player_name
            elif p.epn_position_type == 'left':
                left_names[p.epn_position_index] = p.epn_player_name
            elif p.epn_position_type == 'right':
                right_names[p.epn_position_index] = p.epn_player_name

        if pairing_type == 'Random' and not random_names:
            for idx, reg in enumerate(er_records):
                u = UsersModel.query.get(reg.er_player_id)
                if u:
                    random_names[idx] = u.us_name

        reg_by_name = {}
        for reg in er_records:
            u = UsersModel.query.get(reg.er_player_id)
            if u:
                reg_by_name[u.us_name.lower()] = u

        if pairing_type == 'Manual':
            half = max_players // 2
            for ti in range(half):
                tl = chr(65 + ti)
                td = team_names.get(tl, {})
                for pos in (1, 2):
                    nm = td.get(pos, '')
                    player_slots.append({
                        'slot': len(player_slots),
                        'name': nm,
                        'player': reg_by_name.get(nm.lower()) if nm else None,
                        'field': f'team_{tl}_player{pos}',
                        'label': f'Team {tl} – P{pos}',
                        'team_letter': tl,
                        'team_pos': pos,
                    })
        elif pairing_type == 'L&R Random':
            half = max_players // 2
            for i in range(half):
                nm = left_names.get(i, '')
                player_slots.append({
                    'slot': i,
                    'name': nm,
                    'player': reg_by_name.get(nm.lower()) if nm else None,
                    'field': f'left_player_{i}',
                    'label': f'Left {i+1}',
                    'side': 'left',
                })
            for i in range(half):
                nm = right_names.get(i, '')
                player_slots.append({
                    'slot': half + i,
                    'name': nm,
                    'player': reg_by_name.get(nm.lower()) if nm else None,
                    'field': f'right_player_{i}',
                    'label': f'Right {i+1}',
                    'side': 'right',
                })
        else:  # Random (default)
            for i in range(max_players):
                nm = random_names.get(i, '')
                player_slots.append({
                    'slot': i,
                    'name': nm,
                    'player': reg_by_name.get(nm.lower()) if nm else None,
                    'field': f'player_{i}',
                    'label': f'Player {i+1}',
                })

    # Determine if any game for this event already has a result recorded
    has_results = db.session.query(Game).filter(
        Game.gm_idEvent == event.ev_id,
        db.or_(
            db.and_(Game.gm_result_A != None, Game.gm_result_A != 0),
            db.and_(Game.gm_result_B != None, Game.gm_result_B != 0),
        )
    ).first() is not None

    return render_template("edit_event_step3.html", user=current_user, event=event,
                          player_data=player_data, access_code=access_code,
                          player_slots=player_slots, pairing_type=pairing_type,
                          has_results=has_results)

@views.route('/edit_event_players/<int:event_id>', methods=['GET', 'POST'])
@login_or_access_code_required
def edit_event_players(event_id):
    """Edit player list for an event with existing games (substitute players)"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization (superuser, club authorization, or public event with access code)
    is_public_event = event.ev_club_id == 2  # Public Events club ID
    
    if current_user.is_authenticated and not is_public_event and current_user.us_is_superuser != 1:
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
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Check if any games have been played (have scores)
    games_played = any(game.gm_result_A is not None or game.gm_result_B is not None for game in event_games)
    if games_played:
        flash(translate('Cannot substitute players - some games have already been played'), 'error')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
    
    # Get current registered players
    current_registrations = EventRegistration.query.filter_by(er_event_id=event_id, er_is_substitute=False).all()
    
    if request.method == 'POST':
        # Handle player substitution logic
        flash(translate('Player substitution functionality will be implemented'), 'info')
        access_code = session.get(f'event_{event_id}_access_code', '')
        return redirect(url_for('views.detail_event', slug=event.ev_slug, code=access_code) if access_code else url_for('views.detail_event', slug=event.ev_slug))
    
    # Get access code from session if editing public event
    access_code = session.get(f'event_{event_id}_access_code', '')
    
    return render_template("edit_event_players.html", user=current_user, event=event, 
                          registrations=current_registrations, access_code=access_code)

@views.route('/hide_event/<int:event_id>', methods=['POST'])
@login_required
def hide_event(event_id):
    """Hide/Unhide an event (toggle between canceled and announced status)"""
    from .models import Event, Club, ClubAuthorization
    
    # Get event and verify user has permission
    event = Event.query\
        .join(Club, Event.ev_club_id == Club.cl_id)\
        .join(ClubAuthorization, Club.cl_id == ClubAuthorization.ca_club_id)\
        .filter(Event.ev_id == event_id, ClubAuthorization.ca_user_id == current_user.us_id)\
        .first()
    
    if not event:
        flash(translate('Event not found or access denied'), category='error')
        return redirect(url_for('views.managementEvents'))
    
    try:
        # Toggle between canceled and announced status
        if event.ev_status == 'canceled':
            event.ev_status = 'announced'
            flash(translate('Event is now visible to players'), category='success')
        else:
            event.ev_status = 'canceled'
            flash(translate('Event has been hidden from players'), category='success')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(translate('Error updating event status'), category='error')
    
    return redirect(url_for('views.edit_event', event_id=event_id))

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

    return redirect(url_for('views.edit_league', slug=league.lg_slug) + '#basic-info')

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
        return redirect(url_for('views.edit_league', slug=league.lg_slug) + '#court-details')
    
    # Validate selected courts
    selected_courts = request.form.getlist('selected_courts')
    required_courts = (league.lg_nbrTeams + 1) // 2
    
    if len(selected_courts) != required_courts:
        flash(translate(f'You must select exactly {required_courts} courts for {league.lg_nbrTeams} teams.'), 'error')
        return redirect(url_for('views.edit_league', slug=league.lg_slug) + '#court-details')
    
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
        return redirect(url_for('views.edit_league', slug=league.lg_slug) + '#court-details')
    
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
    return redirect(url_for('views.edit_league', slug=league.lg_slug) + '#court-details')

@views.route('/create_and_add_league_player/<int:league_id>', methods=['GET', 'POST'])
@login_required
def create_and_add_league_player(league_id):
    league = League.query.get_or_404(league_id)
    return_url = request.args.get('return_url') or url_for('views.edit_league', slug=league.lg_slug)
    
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
        return redirect(url_for('views.edit_league', slug=league.lg_slug))
    
    league_player = LeaguePlayers.query.filter_by(lp_league_id=league_id, lp_player_id=user_id).first()
    if league_player:
        db.session.delete(league_player)
        db.session.commit()
        flash(translate('Player successfully removed from the league.'), 'success')
    else:
        flash(translate('Player not found in this league.'), 'error')
    
    return redirect(url_for('views.edit_league', slug=league.lg_slug))

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

    # Build nickname map: {user_id: nickname} for this club
    nicknames = PlayerClubNickname.query.filter_by(pcn_club_id=club.cl_id).all()
    nickname_map = {n.pcn_user_id: n.pcn_nickname for n in nicknames}

    return render_template('gameday_detail.html', 
                         user=current_user, 
                         gameday=gameday,
                         league=league,
                         club=club,
                         is_registered=is_registered,
                         is_league_player=is_league_player,
                         registration_start=registration_start,
                         registration_end=registration_end,
                         now=lambda: datetime.now(timezone.utc),
                         nickname_map=nickname_map)

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

@views.route('/search', methods=['GET'])
def search():
    """Global search across users, events and clubs with fuzzy matching."""
    import difflib

    query = request.args.get('query', '').strip()
    referrer = request.referrer or url_for('views.home')

    if not query:
        return redirect(referrer)

    query_lower = query.lower()

    def score(name):
        """Return a match score: 1.0 for substring, difflib ratio otherwise."""
        name_lower = name.lower()
        if query_lower in name_lower:
            # Prefer shorter names (closer to query length) for substring matches
            return 1.0 - (len(name_lower) - len(query_lower)) * 0.001
        return difflib.SequenceMatcher(None, query_lower, name_lower).ratio()

    MIN_SCORE = 0.35
    best_score = 0
    best_type = None
    best_obj = None

    # --- Search events (available to all users) ---
    events = Event.query.filter(Event.ev_status != 'canceled').all()
    for ev in events:
        s = score(ev.ev_title)
        if s > best_score:
            best_score = s
            best_type = 'event'
            best_obj = ev

    # --- Search users/players (available to all users including anonymous) ---
    users = Users.query.filter(Users.us_is_active == True).all()
    for u in users:
        s = score(u.us_name)
        if s > best_score:
            best_score = s
            best_type = 'user'
            best_obj = u

    # --- Search clubs (available to all users including anonymous) ---
    clubs = Club.query.filter(Club.cl_active == True).all()
    for cl in clubs:
        s = score(cl.cl_name)
        if s > best_score:
            best_score = s
            best_type = 'club'
            best_obj = cl

    if best_score < MIN_SCORE or best_obj is None:
        flash(translate('No results found for "{}".').format(query), 'warning')
        return redirect(referrer)

    is_superuser = current_user.is_authenticated and current_user.us_is_superuser

    if best_type == 'event':
        return redirect(url_for('views.detail_event', slug=best_obj.ev_slug))

    if best_type == 'user':
        if is_superuser:
            return redirect(url_for('views.editUser', user_id=best_obj.us_id))
        return redirect(url_for('views.player_profile', user_id=best_obj.us_id))

    if best_type == 'club':
        if is_superuser:
            return redirect(url_for('views.edit_club', club_slug=best_obj.cl_slug))
        return redirect(url_for('views.club_detail', club_slug=best_obj.cl_slug))

    return redirect(referrer)


@views.route('/club_detail/<club_slug>', methods=['GET'])
def club_detail(club_slug):
    """Public read-only view of a club's information."""
    club = Club.query.filter_by(cl_slug=club_slug).first_or_404()
    active_events = Event.query.filter_by(ev_club_id=club_id).filter(
        Event.ev_status.notin_(['canceled', 'event_ended'])
    ).order_by(Event.ev_date.desc()).all()
    past_events = Event.query.filter_by(ev_club_id=club_id).filter(
        Event.ev_status == 'event_ended'
    ).order_by(Event.ev_date.desc()).all()
    courts = club.courts
    return render_template('club_detail.html',
                           user=current_user,
                           club=club,
                           active_events=active_events,
                           past_events=past_events,
                           courts=courts)


@views.route('/player_profile/<int:user_id>', methods=['GET'])
def player_profile(user_id):
    """Public read-only player profile with basic info and game history."""
    p_user = Users.query.get_or_404(user_id)

    # Fetch all games involving this player with results, newest first
    games_raw = Game.query.filter(
        db.or_(
            Game.gm_idPlayer_A1 == user_id,
            Game.gm_idPlayer_A2 == user_id,
            Game.gm_idPlayer_B1 == user_id,
            Game.gm_idPlayer_B2 == user_id,
        ),
        Game.gm_result_A != None,
        Game.gm_result_B != None,
    ).order_by(Game.gm_date.desc(), Game.gm_timeStart.desc()).all()

    def pname(u):
        return u.us_name if u else '?'

    def pid(u):
        return u.us_id if u else None

    games = []
    total = 0
    wins = 0
    for g in games_raw:
        on_team_a = g.gm_idPlayer_A1 == user_id or g.gm_idPlayer_A2 == user_id
        won = (g.gm_result_A > g.gm_result_B) if on_team_a else (g.gm_result_B > g.gm_result_A)
        draw = g.gm_result_A == g.gm_result_B
        total += 1
        if won:
            wins += 1

        games.append({
            'date': g.gm_date,
            'time_start': g.gm_timeStart,
            'time_end': g.gm_timeEnd,
            'event_id': g.gm_idEvent,
            'event_slug': g.event.ev_slug if g.event else None,
            'court': g.court.ct_name if g.court else None,
            'won': won,
            'draw': draw,
            'team_a': {
                'players': [
                    {'id': pid(g.player_A1), 'name': pname(g.player_A1)},
                    {'id': pid(g.player_A2), 'name': pname(g.player_A2)},
                ],
                'score': g.gm_result_A,
                'is_mine': on_team_a,
            },
            'team_b': {
                'players': [
                    {'id': pid(g.player_B1), 'name': pname(g.player_B1)},
                    {'id': pid(g.player_B2), 'name': pname(g.player_B2)},
                ],
                'score': g.gm_result_B,
                'is_mine': not on_team_a,
            },
        })

    losses = total - wins
    win_rate = round(wins * 100 / total) if total else 0

    return render_template('player_profile.html',
                           user=current_user,
                           p_user=p_user,
                           games=games,
                           total=total,
                           wins=wins,
                           losses=losses,
                           win_rate=win_rate)


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


@views.route('/elo_ranking', methods=['GET'])
def elo_ranking():
    """Show clubs that have at least one completed event game with rankings."""
    clubs_with_games = (
        db.session.query(Club)
        .join(Event, Event.ev_club_id == Club.cl_id)
        .join(Game, Game.gm_idEvent == Event.ev_id)
        .filter(
            Event.ev_exclude_from_elo != True,
            Game.gm_result_A != None,
            Game.gm_idPlayer_A1 != None,
        )
        .distinct()
        .all()
    )
    return render_template('elo_ranking.html', user=current_user, clubs=clubs_with_games)


@views.route('/elo_ranking/<club_slug>', methods=['GET'])
def elo_club_ranking(club_slug):
    """ELO ranking for a specific club, computed from all scored games at that club."""
    club = Club.query.filter_by(cl_slug=club_slug).first_or_404()
    rankings = func_calculate_ELO_by_club(club.cl_id)
    nicknames = PlayerClubNickname.query.filter_by(pcn_club_id=club.cl_id).all()
    nickname_map = {n.pcn_user_id: n.pcn_nickname for n in nicknames}
    return render_template('elo_club_ranking.html', user=current_user, club=club, rankings=rankings, nickname_map=nickname_map)


@views.route('/recalculate_ELO_full', methods=['GET', 'POST'])
@login_required
def recalculate_ELO_full():
    return func_calculate_ELO_full()

# Event creation step functions
@views.route('/create_event_step2/<int:event_id>', methods=['GET'])
@login_required  
def create_event_step2(event_id):
    """Step 2: Configure courts and game settings for event"""
    # Get the event
    event = Event.query.get_or_404(event_id)
    
    # Check if user is authorized for this club (only if event has a club)
    if event.ev_club_id:
        is_authorized = db.session.query(ClubAuthorization).filter(
            ClubAuthorization.ca_user_id == current_user.us_id,
            ClubAuthorization.ca_club_id == event.ev_club_id
        ).first() is not None
        
        if not is_authorized:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
        
        # Get club 
        club = Club.query.get_or_404(event.ev_club_id)
        club_name = club.cl_name
    else:
        # Public event - check if current user is the creator
        if event.ev_created_by_id != current_user.us_id:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
        club_name = "Public Event"
    
    # Calculate number of courts needed (max_players / 4)
    courts_needed = event.ev_max_players // 4

    # Fetch the club's existing courts to pre-fill court names
    club_courts = []
    if event.ev_club_id:
        club_courts = Court.query.filter_by(ct_club_id=event.ev_club_id).order_by(Court.ct_id).all()
    
    return render_template('create_event_step2.html', 
                           user=current_user, 
                           event=event, 
                           courts_needed=courts_needed,
                           club_name=club_name,
                           club_courts=club_courts)

@views.route('/create_event_step2/<int:event_id>', methods=['POST'])
@login_required
def process_event_step2(event_id):
    """Process step 2 and redirect to step 3"""
    # Get the event
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if event.ev_club_id:
        is_authorized = db.session.query(ClubAuthorization).filter(
            ClubAuthorization.ca_user_id == current_user.us_id,
            ClubAuthorization.ca_club_id == event.ev_club_id
        ).first() is not None
        
        if not is_authorized:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
    else:
        # Public event - check if current user is the creator
        if event.ev_created_by_id != current_user.us_id:
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
        valid_pairing_types = ['Random', 'Manual', 'L&R Random', 'Ranking']
        if pairing_type not in valid_pairing_types:
            flash(translate('Invalid pairing type selected!'), 'error')
            return redirect(url_for('views.create_event_step2', event_id=event_id))
        
        # Store court names and pairing type
        # Clear any existing court assignments
        EventCourts.query.filter_by(evc_event_id=event.ev_id).delete()
        
        # Only process courts if event has a club
        if event.ev_club_id:
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
    
    # Check authorization
    if event.ev_club_id:
        is_authorized = db.session.query(ClubAuthorization).filter(
            ClubAuthorization.ca_user_id == current_user.us_id,
            ClubAuthorization.ca_club_id == event.ev_club_id
        ).first() is not None
        
        if not is_authorized:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
        
        club = Club.query.get_or_404(event.ev_club_id)
        club_name = club.cl_name
    else:
        # Public event - check if current user is the creator
        if event.ev_created_by_id != current_user.us_id:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
        club_name = "Public Event"
    
    # Calculate variables needed for player registration UI
    max_players = event.ev_max_players
    pairing_type = event.ev_pairing_type or 'Random'
    
    # Calculate teams needed for Manual pairing
    teams_needed = max_players // 2 if pairing_type == 'Manual' else 0
    
    # Generate team letters (A, B, C, etc.)
    team_letters = [chr(65 + i) for i in range(teams_needed)]  # A, B, C...
    
    # Get existing player data for editing
    existing_players = EventPlayerNames.query.filter_by(epn_event_id=event.ev_id).all()
    
    # Organize existing player data by type and position for easy template access
    player_data = {}
    if pairing_type in ('Random', 'Ranking'):
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
                           club_name=club_name,
                           max_players=max_players,
                           pairing_type=pairing_type,
                           teams_needed=teams_needed,
                           team_letters=team_letters,
                           player_data=player_data)
@views.route('/complete_event_creation/<int:event_id>', methods=['POST'])
@login_required
def complete_event_creation(event_id):
    """Complete event creation: register players and create games"""
    event = Event.query.get_or_404(event_id)
    
    # Check authorization
    if event.ev_club_id:
        is_authorized = db.session.query(ClubAuthorization).filter(
            ClubAuthorization.ca_user_id == current_user.us_id,
            ClubAuthorization.ca_club_id == event.ev_club_id
        ).first() is not None
        
        if not is_authorized:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
    else:
        # Public event - check if current user is the creator
        if event.ev_created_by_id != current_user.us_id:
            flash(translate('You are not authorized to edit this event!'), 'error')
            return redirect(url_for('views.managementEvents'))
    
    try:
        # Process player registrations using the update_event_players logic
        # We need to call this directly to handle the form processing
        from .models import EventPlayerNames
        
        # Determine the user ID to use for created_by and registered_by
        creator_user_id = current_user.us_id
        
        # Collect all player names first for validation
        all_player_names = []
        pairing_type = event.ev_pairing_type or 'Random'
        max_players = event.ev_max_players
        
        # Collect names based on pairing type
        if pairing_type in ('Random', 'Ranking'):
            for i in range(max_players):
                player_name = request.form.get(f'player_{i}')
                if player_name and player_name.strip():
                    all_player_names.append(player_name.strip())
                    
        elif pairing_type == 'Manual':
            teams_needed = max_players // 2
            for team_idx in range(teams_needed):
                team_letter = chr(65 + team_idx)  # A, B, C...
                player1_name = request.form.get(f'team_{team_letter}_player1')
                player2_name = request.form.get(f'team_{team_letter}_player2')
                
                if player1_name and player1_name.strip():
                    all_player_names.append(player1_name.strip())
                if player2_name and player2_name.strip():
                    all_player_names.append(player2_name.strip())
                    
        elif pairing_type == 'L&R Random':
            left_players = max_players // 2
            right_players = max_players // 2
            
            for i in range(left_players):
                left_player = request.form.get(f'left_player_{i}')
                if left_player and left_player.strip():
                    all_player_names.append(left_player.strip())
                    
            for i in range(right_players):
                right_player = request.form.get(f'right_player_{i}')
                if right_player and right_player.strip():
                    all_player_names.append(right_player.strip())
        
        # Validation: Check for duplicate names (case insensitive)
        names_lower = [name.lower() for name in all_player_names]
        if len(names_lower) != len(set(names_lower)):
            flash(translate('Duplicate player names found. Each player must have a unique name.'), 'error')
            return redirect(url_for('views.create_event_step3', event_id=event_id))
        
        all_players_complete = (len(all_player_names) == max_players)
        
        # Helper function to get or create user
        def get_or_create_user(player_name):
            """Get existing user or create new player user"""
            if not player_name or not player_name.strip():
                return None
                
            # Try to find existing user by name (case insensitive)
            user = Users.query.filter(Users.us_name.ilike(player_name.strip())).first()
            if not user:
                # Try word-by-word match (e.g. "Luciano Oliveira" matches "Luciano \"Fugi\" Oliveira")
                words = [w for w in player_name.strip().split() if w]
                if words:
                    q = Users.query
                    for word in words:
                        q = q.filter(Users.us_name.ilike(f'%{word}%'))
                    user = q.first()
            
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
        
        # Process players based on pairing type
        players_registered = 0
        
        if pairing_type in ('Random', 'Ranking'):
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
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        # Register player
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                        
        elif pairing_type == 'Manual':
            teams_needed = max_players // 2
            for team_idx in range(teams_needed):
                team_letter = chr(65 + team_idx)
                
                # Player 1
                player1_name = request.form.get(f'team_{team_letter}_player1')
                if player1_name and player1_name.strip():
                    user = get_or_create_user(player1_name.strip())
                    if user:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=player1_name.strip(),
                            epn_position_type='team',
                            epn_team_identifier=team_letter,
                            epn_team_position=1,
                            epn_position_index=team_idx,
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                
                # Player 2
                player2_name = request.form.get(f'team_{team_letter}_player2')
                if player2_name and player2_name.strip():
                    user = get_or_create_user(player2_name.strip())
                    if user:
                        player_record = EventPlayerNames(
                            epn_event_id=event.ev_id,
                            epn_player_name=player2_name.strip(),
                            epn_position_type='team',
                            epn_team_identifier=team_letter,
                            epn_team_position=2,
                            epn_position_index=team_idx,
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
                        
        elif pairing_type == 'L&R Random':
            left_players = max_players // 2
            right_players = max_players // 2
            
            # Process left players
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
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
            
            # Process right players
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
                            epn_created_by_id=creator_user_id
                        )
                        db.session.add(player_record)
                        
                        registration = EventRegistration(
                            er_event_id=event.ev_id,
                            er_player_id=user.us_id,
                            er_registered_by_id=creator_user_id,
                            er_is_substitute=False
                        )
                        db.session.add(registration)
                        players_registered += 1
        
        # Commit player registrations
        db.session.commit()
        
        # Only create games if all players are registered
        if all_players_complete:
            num_games = create_games_for_event(event_id)
            db.session.commit()
            flash(translate('Event created successfully with {} players and {} games!').format(players_registered, num_games), 'success')
        else:
            flash(translate('Saved {} of {} players. Add remaining players to complete the event.').format(players_registered, max_players), 'warning')
        return redirect(url_for('views.detail_event', slug=event.ev_slug))
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(translate('Error creating event: {}').format(str(e)), 'error')
        return redirect(url_for('views.create_event_step3', event_id=event_id))