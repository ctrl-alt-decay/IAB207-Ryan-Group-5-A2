import os
import secrets

from flask import Flask, render_template, flash, redirect, request, url_for
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError

db = SQLAlchemy()

# AI search is optional so the site still runs where sentence-transformers can't
# be installed (PythonAnywhere's free disk quota is too small for torch). Without
# it, encoder is None and search falls back to keywords.
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

if SentenceTransformer is None:
    encoder = None
    print(' * AI search is off: sentence-transformers is not installed')
else:
    try:
        encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
        print("Loaded local AI model")
    except Exception:
        print("Local AI model not found. Downloading...")
        encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        print("Downloaded and loaded AI model")


def embed(text):
    # stored as JSON text in Event.description_embedding; None when AI search is off
    if encoder is None:
        return None
    import json
    return json.dumps(encoder.encode(text).tolist())

def add_missing_columns():
    # create_all() won't add new columns to existing tables, so older databases
    # would crash with "no such column". Additive only. NOT NULL columns need a
    # server_default on the model or existing rows break.
    inspector = db.inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column['name'] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = 'ALTER TABLE {} ADD COLUMN {} {}'.format(
                table.name, column.name, column.type.compile(dialect=db.engine.dialect))
            if column.server_default is not None:
                ddl += ' NOT NULL DEFAULT {}'.format(column.server_default.arg)
            db.session.execute(db.text(ddl))
            print(' * Added missing column {}.{}'.format(table.name, column.name))
    db.session.commit()


def add_missing_embeddings():
    """Events made before AI search existed (the sample events, or ones in an
    older database) have no description_embedding, which AI search needs for
    every event. This works one out for each, the same way create_event does
    for a new event. Only fills in missing ones - never changes existing ones."""
    if encoder is None:
        return
    import json
    from .models import Event
    events = db.session.scalars(
        db.select(Event).where(Event.description_embedding.is_(None))).all()
    if not events:
        return
    vectors = encoder.encode([event.description for event in events])
    for event, vector in zip(events, vectors):
        event.description_embedding = json.dumps(vector.tolist())
    db.session.commit()
    print(' * Added AI search data for {} older events'.format(len(events)))



def _secret_key(app):
    # Env var if set, otherwise generate one and keep it in instance/ (gitignored)
    # so logins survive restarts.
    key = os.environ.get('EPICUREAN_SECRET_KEY')
    if key:
        return key
    path = os.path.join(app.instance_path, 'secret_key')
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    os.makedirs(app.instance_path, exist_ok=True)
    key = secrets.token_hex(32)
    with open(path, 'w') as f:
        f.write(key)
    return key


def create_app():

    app = Flask(__name__)
    app.secret_key = _secret_key(app)
    CSRFProtect(app)
    # Kept in the package folder (not instance/) so the seeded database ships with
    # the submission. Must be set before init_app.
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'sitedata.sqlite')
    db.init_app(app)

    Bootstrap5(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    # imported here to avoid a circular import
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
       return db.session.scalar(db.select(User).where(User.id==user_id))

    from . import views
    app.register_blueprint(views.main_bp)

    from . import auth
    app.register_blueprint(auth.auth_bp)

    # On the app, not a blueprint, so they catch every route.
    # FLASK_DEBUG=1 shows the debugger instead of the 500 page.
    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html', code=404, title='Page Not Found',
                               message="Sorry, we couldn't find that page. The link may be "
                                       "wrong, or the page may have moved."), 404

    # Usually a form left open until its token expired.
    @app.errorhandler(CSRFError)
    def csrf_error(error):
        flash('That form had expired, so nothing was changed. Please try again.', 'danger')
        back = request.referrer or ''
        on_site = back.startswith(request.host_url)
        return redirect(back if on_site else url_for('main.index'))

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template('error.html', code=500, title='Something Went Wrong',
                               message='Sorry, something went wrong on our end. '
                                       'Please try again in a moment.'), 500

    # also fills in AI search data for events that don't have it yet
    with app.app_context():
        db.create_all()
        add_missing_columns()
        add_missing_embeddings()

    return app
