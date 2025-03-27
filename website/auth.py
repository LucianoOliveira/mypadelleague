from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from .models import Users
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from flask_login import login_user, login_required, logout_user, current_user
import os
from werkzeug.utils import secure_filename

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = Users.query.filter_by(us_email=email).first()
        if user:
            if check_password_hash(user.us_pwd, password):
                if user.us_is_active:
                    flash('Logged in successfully!', category='success')
                    login_user(user, remember=True)
                    return redirect(url_for('views.home'))
                else:
                    flash('User account is not active.', category='error')
            else:
                flash('Incorrect password, try again.', category='error')
        else:
            flash('Email does not exist.', category='error')

    return render_template("login.html", user=current_user)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        telephone = request.form.get('telephone')
        password1 = request.form.get('password1')
        password2 = request.form.get('password2')
        photo = request.files.get('photo')

        # Validation
        if len(email) < 4:
            flash(g.translations.get('Email must be greater than 4 characters.', {}).get(g.lang, 'Email must be greater than 4 characters.'), category='error')
            return render_template("sign_up.html", user=current_user)
            
        if len(fullname) < 4:
            flash(g.translations.get('Name must be greater than 4 characters.', {}).get(g.lang, 'Name must be greater than 4 characters.'), category='error')
            return render_template("sign_up.html", user=current_user)
            
        if not telephone or len(telephone.strip()) == 0:
            flash(g.translations.get('Telephone number is required.', {}).get(g.lang, 'Telephone number is required.'), category='error')
            return render_template("sign_up.html", user=current_user)
            
        if password1 != password2:
            flash(g.translations.get('Passwords don\'t match.', {}).get(g.lang, 'Passwords don\'t match.'), category='error')
            return render_template("sign_up.html", user=current_user)
            
        if len(password1) < 7:
            flash(g.translations.get('Password must be greater than 6 characters.', {}).get(g.lang, 'Password must be greater than 6 characters.'), category='error')
            return render_template("sign_up.html", user=current_user)

        # Check for existing phone number
        existing_phone = Users.query.filter_by(us_telephone=telephone).first()
        if existing_phone:
            flash(g.translations.get('A user with this telephone number already exists.', {}).get(g.lang, 'A user with this telephone number already exists.'), category='error')
            return render_template("sign_up.html", user=current_user)

        # Check for existing email
        existing_email = Users.query.filter_by(us_email=email).first()
        if existing_email:
            flash(g.translations.get('Email already exists.', {}).get(g.lang, 'Email already exists.'), category='error')
            return render_template("sign_up.html", user=current_user)

        # Create user
        new_user = Users(
            us_name=fullname, 
            us_email=email,
            us_telephone=telephone,
            us_is_player=True,
            us_is_active=True,
            us_pwd=generate_password_hash(password1, method='pbkdf2:sha256')
        )
        db.session.add(new_user)
        db.session.commit()

        # Handle photo upload after user is created (so we have the user ID)
        if photo:
            # Create user photos directory
            path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'photos', 'users', str(new_user.us_id))
            if not os.path.exists(path):
                os.makedirs(path)
            
            # Save the photo as main.jpg
            filePath = os.path.join(path, 'main.jpg')
            if os.path.exists(filePath):
                os.remove(filePath)
            photo.save(filePath)

        # Login user
        login_user(new_user, remember=True)
        flash(g.translations.get('Account created successfully!', {}).get(g.lang, 'Account created successfully!'), category='success')
        return redirect(url_for('views.home'))
        
    return render_template("sign_up.html", user=current_user)