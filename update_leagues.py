import os
import sys

# Add your project directory to path
project_path = '/home/mypadelleague/mypadelleague'  # Change to your actual path on PythonAnywhere
if project_path not in sys.path:
    sys.path.append(project_path)

# Import Flask app and run the scheduled task
from website import create_app
from website.tasks import scheduled_task

app = create_app()
scheduled_task(app)

print("League status update completed successfully")