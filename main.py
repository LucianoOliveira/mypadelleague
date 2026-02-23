from website import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Enable debug mode temporarily to see detailed error messages
    debug_mode = True  # os.environ.get('FLASK_ENV') == 'development' or os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode)     