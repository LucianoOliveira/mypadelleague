from datetime import datetime, timezone
from . import db
from .models import League
import threading
import time
import logging
import atexit

# Global variable to track thread state
_update_thread = None
_should_stop = False

def update_league_statuses(app):
    with app.app_context():
        try:
            leagues = League.query.all()
            for league in leagues:
                if league.should_update_status():
                    league.update_status()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating league statuses: {str(e)}")
        finally:
            db.session.close()  # Ensure connections are closed

def run_status_updates(app):
    global _should_stop
    while not _should_stop:
        try:
            update_league_statuses(app)
        except Exception as e:
            logging.error(f"Unhandled exception in status update thread: {str(e)}")
        
        # Check every minute
        for _ in range(60):  # Check stop flag every second instead of blocking for 60 seconds
            if _should_stop:
                break
            time.sleep(1)

def start_background_tasks(app):
    global _update_thread, _should_stop
    
    # Don't start if already running
    if _update_thread and _update_thread.is_alive():
        return
    
    _should_stop = False
    _update_thread = threading.Thread(target=run_status_updates, args=(app,), daemon=True)
    _update_thread.start()
    
    # Register shutdown handler
    atexit.register(stop_background_tasks)
    
    # Log that we started tasks (only in debug mode)
    if app.debug:
        logging.info("Background league status update task started")

def stop_background_tasks():
    global _should_stop, _update_thread
    
    if _update_thread and _update_thread.is_alive():
        _should_stop = True
        _update_thread.join(timeout=5)  # Wait up to 5 seconds for thread to end

# For PythonAnywhere - this function can be called from a scheduled task
def scheduled_task(app):
    """Function to be called from a scheduled task instead of using threads"""
    with app.app_context():
        try:
            update_league_statuses(app)
        except Exception as e:
            logging.error(f"Error in scheduled task: {str(e)}")