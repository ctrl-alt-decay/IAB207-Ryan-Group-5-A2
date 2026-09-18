# Entry point. Run `python main.py` from this folder to start the Flask dev server
# at http://127.0.0.1:5000 (debug mode is switched on inside create_app).
# If the 'website' package is renamed (per the brief), update this import too.
from website import create_app

if __name__ == '__main__':
    app = create_app()
    app.run()