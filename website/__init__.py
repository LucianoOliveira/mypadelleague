import logging
from flask import Flask, request, g
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_login import LoginManager
import re
from flask_migrate import Migrate
import json
import os

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    # app = Flask(__name__)
    app = Flask(__name__, instance_relative_config=True)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Enhanced logging configuration
    logging.basicConfig(level=logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)

    app.logger.debug('Starting application configuration...')


    from .config import Config
    app.logger.debug(f'Database path: {Config.DB_NAME}')

    # Load configuration
    app.config.from_object(Config)
    app.logger.debug('Configuration loaded')

    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{Config.DB_NAME}'
    db.init_app(app)
    migrate = Migrate(app, db)
    app.logger.debug('Database initialized')

    # Configure available languages
    LANGUAGES = {
        'en': 'English',
        'pt': 'Portuguese'
    }

    def load_translations(lang):
        translations_path = os.path.join(app.root_path, 'translations', f'{lang}.json')
        if not os.path.exists(translations_path):
            translations_path = os.path.join(app.root_path, '..', 'translations', 'translations.json')
        with open(translations_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @app.before_request
    def before_request():
        lang = request.cookies.get('lang')
        if lang:
            g.lang = lang
        else:
            g.lang = 'en'  # default to English
        g.translations = load_translations(g.lang)

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    from .models import Users
    from datetime import date
    from datetime import datetime, timedelta
    from sqlalchemy.sql import func

    with app.app_context():
        try:
            db.create_all()
            app.logger.debug('Database tables created successfully')
        except Exception as e:
            app.logger.error(f'Error creating database tables: {str(e)}')


    migrate.init_app(app, db)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return Users.query.get(int(id))

    def calculate_age(birthdate):
        today = date.today()
        age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
        return age

    def display_short_name(long_name):
        match = re.search(r'"(.*?)"', long_name)
        if match:
            short_name= match.group(1)
        else:
            short_name = long_name
        return short_name

    # Make the calculate_age function accessible to the entire application
    app.jinja_env.globals.update(calculate_age=calculate_age)
    # Make the display_short_name function accessible to the entire application
    app.jinja_env.globals.update(display_short_name=display_short_name)

    def translate(text):
        return g.translations.get(text, {}).get(g.lang, text)

    app.jinja_env.globals.update(translate=translate)

    # Start background tasks differently based on environment
    from .tasks import start_background_tasks, update_league_statuses
    import os
    
    # Check if running on PythonAnywhere
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        # On PythonAnywhere, don't use background threads
        # Instead, use their task scheduler for update_league_statuses
        pass  # Tasks will be run by the PythonAnywhere scheduled task
    else:
        # For local development, use the background thread
        start_background_tasks(app)

    @app.route('/debug')
    def debug_route():
        app.logger.debug('Debug route accessed')
        info = {}
        try:
            # Check instance path
            info['instance_path'] = app.instance_path
            info['instance_exists'] = os.path.exists(app.instance_path)

            # Check database
            from .config import Config
            info['db_path'] = Config.DB_NAME
            info['db_exists'] = os.path.exists(Config.DB_NAME)
            info['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']

            # Check folders
            info['static_folder'] = app.static_folder
            info['template_folder'] = app.template_folder

            return info
        except Exception as e:
            app.logger.error(f'Debug route error: {str(e)}')
            return {'status': 'error', 'message': str(e)}



    return app

# Create the application instance
# app = create_app()