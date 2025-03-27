from datetime import datetime, timezone
from . import db
from .models import League
import threading
import time

def update_league_statuses(app):
    with app.app_context():
        leagues = League.query.all()
        for league in leagues:
            if league.should_update_status():
                league.update_status()
        db.session.commit()

def start_background_tasks(app):
    def run_status_updates():
        while True:
            update_league_statuses(app)
            # Check every minute
            time.sleep(60)

    thread = threading.Thread(target=run_status_updates, daemon=True)
    thread.start()