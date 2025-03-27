from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Flask, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_required, current_user
from .models import (Users, UserRequests, Messages, League, Club, ClubAuthorization, 
                    Court, GameDay, LeagueCourts, Game, GameDayPlayer, GameDayClassification, 
                    LeagueClassification, ELOranking, ELOrankingHist, LeaguePlayers, GameDayRegistration)
from . import db
import json, os, threading
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import and_, func, cast, String, text, desc, case, literal_column
from PIL import Image
from io import BytesIO
from .user_info_func import ext_home, ext_userInfo
from .tools import *
from .gameday import *
import shutil

def translate(text):
    # Import translations file
    with open('translations/translations.json', 'r', encoding='utf-8') as f:
        translations = json.load(f)
    
    # Get current language from session or default to English
    lang = session.get('language', 'en')
    
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

# User own info routes
@views.route('/userOwnInfo', methods=['GET', 'POST'])
@login_required
def userOwnInfo():
    return render_template("user_own_info.html", user=current_user)

@views.route('/userInfo/<int:user_id>', methods=['GET', 'POST'])
@login_required
def userInfo(p_user_id):
    return ext_userInfo(p_user_id)

# ...existing code...

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

# ...existing code...

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

    return render_template("user_own_info.html", user=current_user)

@views.route('/updateUser/<int:userID>', methods=['GET', 'POST'])
@login_required
def updateUser(userID):
    user_id = userID
    pass_user = Users.query.get_or_404(userID)
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
    
    return render_template('user_info.html', user=current_user, p_user=p_user)

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

# ...existing code...

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
        image = request.files.get('club_main_photo')  # Using get() instead of direct access
        if image and image.filename and cl_id > 0:
            path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/clubs/'+str(cl_id)+'/'
            if not os.path.exists(path):
                os.makedirs(path)  # Using makedirs instead of mkdir
            
            filePath = os.path.join(path, 'main.jpg')
            if os.path.exists(filePath):
                os.remove(filePath)
            
            image.save(filePath)

        # register secondary photos
        secondary_photos = request.files.getlist('club_secondary_photos')
        if secondary_photos and any(photo.filename for photo in secondary_photos):
            path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/clubs/'+str(cl_id)+'/'
            secondary_path = os.path.join(path, 'secondary')
            if not os.path.exists(secondary_path):
                os.makedirs(secondary_path)
            
            # Save new photos
            for idx, photo in enumerate(secondary_photos, start=1):
                if photo.filename:
                    photo_path = os.path.join(secondary_path, f'{idx}.jpg')
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

# ...existing code...

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

        # Only create basic league details in step 1
        new_league = League(
            lg_club_id=club_id,
            lg_name=name,
            lg_level=level,
            lg_status='announced',  # Initial status for new leagues
            lg_nbrDays=nbr_days,
            lg_nbrTeams=nbr_teams,
            lg_startDate=start_date,
            lg_endDate=start_date + timedelta(days=int(nbr_days)),
            lg_registration_start=registration_start,
            lg_registration_end=registration_end,
            lg_max_players=nbr_teams * 2,  # Set max players to number of teams * 2
            lg_typeOfLeague="Non-Stop League",  # Default value
            tb_maxLevel=0,  # Default value
            lg_eloK=nbr_teams * 10  # Default value based on number of teams
        )
        
        # Validate registration dates
        if registration_start >= registration_end:
            flash(translate('Registration end must be after registration start'), 'error')
            return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

        if registration_end.date() > start_date:
            flash(translate('Registration must end before league start date'), 'error')
            return render_template('create_league.html', user=current_user, clubs=authorized_clubs)

        db.session.add(new_league)
        db.session.commit()

        # Create GameDays for the league using helper function
        func_create_league_gamedays(new_league.lg_id, name, start_date, nbr_days)
        db.session.commit()

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
    club = Club.query.get_or_409(league.lg_club_id)
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

    # Register main photo
    image = request.files.get('league_photo')  # Using get() instead of direct access
    if image and image.filename:
        path = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(league_id)+'/'
        if not os.path.exists(path):
            os.makedirs(path)
            
        filePath = path + 'main.jpg'
        if os.path.exists(filePath):
            os.remove(filePath)
        
        image.save(filePath)

    # Register secondary photos
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

    flash(translate('League created successfully!'), 'success')
    return redirect(url_for('views.managementLeagues'))

@views.route('/edit_league/<int:league_id>', methods=['GET', 'POST'])
@login_required
def edit_league(league_id):
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
    
    # Get club and courts for the form
    club = Club.query.get_or_404(league.lg_club_id)
    courts = Court.query.filter_by(ct_club_id=club.cl_id).all()
    
    # Get gamedays for this league
    gamedays = GameDay.query.filter_by(gd_idLeague=league_id).order_by(GameDay.gd_date).all()
    
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
        return redirect(url_for('views.managementLeagues'))

    return render_template('edit_league.html', 
                           user=current_user, 
                           league=league,
                           club=club,
                           courts=courts,
                           gamedays=gamedays)

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
    league.lg_endDate = league.lg_startDate + timedelta(days=int(league.lg_nbrDays))
    
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

# ...existing code...

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

# ...existing code...

# Other routes
@views.route('/display_user_image/<userID>')
def display_user_image(userID):
    filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/users/'+str(userID)+'/main.jpg'
    if os.path.isfile(filePath):
        img = func_crop_image_in_memory(filePath)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/users/nophoto.jpg'), code=301)

@views.route('/display_club_main_image/<clubID>')
def display_club_main_image(clubID):
    filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/clubs/'+str(clubID)+'/main.jpg'
    if os.path.isfile(filePath):
        img = func_crop_image_in_memory(filePath)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/clubs/nophoto.jpg'), code=301)
    
@views.route('/display_club_second_image/<clubID>')
def display_club_second_image(clubID):
    filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/clubs/'+str(clubID)+'/secondary/1.jpg'
    if os.path.isfile(filePath):
        img = func_crop_image_in_memory(filePath)
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
    filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(leagueID)+'/main.jpg'
    if os.path.isfile(filePath):
        img = func_crop_image_in_memory(filePath)
        img_io = BytesIO()
        img.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return redirect(url_for('static', filename='photos/leagues/nophoto.jpg'), code=301)
    
@views.route('/display_league_second_image/<leagueID>')
def display_league_second_image(leagueID):
    filePath = str(os.path.abspath(os.path.dirname(__file__)))+'/static/photos/leagues/'+str(leagueID)+'/secondary/1.jpg'
    if os.path.isfile(filePath):
        img = func_crop_image_in_memory(filePath)
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
    
    return render_template('league_detail.html', 
                           user=current_user, 
                           league=league,
                           club=club,
                           gamedays=gamedays)

@views.route('/gameday/<int:gameday_id>', methods=['GET'])
def gameday_detail(gameday_id):
    # Get the gameday
    gameday = GameDay.query.get_or_404(gameday_id)
    
    # Get the associated league
    league = League.query.get_or_404(gameday.gd_idLeague)
    
    # Get the club information
    club = Club.query.get_or_404(league.lg_club_id)
    
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
        print(f"Received search query: {query}")  # Debug line
        
        if len(query) < 3:
            print("Query too short")  # Debug line
            return jsonify([])
            
        users = Users.query.filter(
            db.or_(
                db.func.lower(Users.us_name).like(f'%{query}%'),
                db.func.lower(Users.us_email).like(f'%{query}%')
            )
        ).limit(10).all()
        
        print(f"Found {len(users)} users")  # Debug line
        for user in users:
            print(f"Found user: {user.us_name} ({user.us_email})")  # Debug line
        
        results = [{
            'id': user.us_id,
            'name': user.us_name,
            'email': user.us_email
        } for user in users]
        
        return jsonify(results)
    except Exception as e:
        print(f"Error in search_users: {str(e)}")  # Debug line
        return jsonify({'error': str(e)}), 500