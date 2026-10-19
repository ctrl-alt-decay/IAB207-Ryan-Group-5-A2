# Entry point. Run `python main.py` from this folder to start the Flask dev server
# at http://epicurean.localhost:5000 (browsers send any *.localhost name to this
# computer, so it's the same site as http://127.0.0.1:5000, which also works).
# Debug mode is off; to turn it on while developing
# (debugger + auto-reload), set FLASK_DEBUG=1 first, e.g. in PowerShell:
#   $env:FLASK_DEBUG = "1"; python main.py
# The app lives in the 'epicurean' package (renamed from the starter's 'website',
# as the brief asks - #26).
import os

from epicurean import create_app

if __name__ == '__main__':
    app = create_app()
    # with auto-reload on, this file runs twice - only print the address once
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print(' * Epicurean is running at http://epicurean.localhost:5000')
    app.run()
