# Entry point. Run `python main.py` from this folder to start the Flask dev server
# at http://127.0.0.1:5000 (debug mode is switched on inside create_app).
# The app lives in the 'epicurean' package (renamed from the starter's 'website',
# as the brief asks - #26).
from epicurean import create_app

if __name__ == '__main__':
    app = create_app()
    app.run()