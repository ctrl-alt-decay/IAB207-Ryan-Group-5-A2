# import flask - from 'package' import 'Class'
import os
import secrets

from flask import Flask, render_template, flash, redirect, request, url_for
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError

# Shared database handle. Created unbound so models.py can import it without an
# app existing yet; create_app() binds it with db.init_app(app).
db = SQLAlchemy()

def add_missing_columns():
    """db.create_all() only creates missing *tables*, so a model column added
    after someone's database was made (e.g. Event.likes) would crash the app
    with "no such column". This adds each missing column to the existing table.
    Additive only - it never drops or changes anything. A NOT NULL column needs
    a server_default on the model so existing rows get a value."""
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


def _secret_key(app):
    """The key Flask signs sessions and CSRF tokens with (#27), so it isn't
    written in the code: the EPICUREAN_SECRET_KEY environment variable if it's
    set, otherwise a random key made the first time the app runs and kept in
    instance/secret_key (instance/ is gitignored), so logins survive restarts."""
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


# create a function that creates a web application
# a web server will run this web application
def create_app():
  
    app = Flask(__name__)  # this is the name of the module/package that is calling this app
    # Debug mode is off unless asked for (#27): set FLASK_DEBUG=1 before
    # `python main.py` to get the debugger and auto-reload while developing.
    # It's never switched on in the code, so the submitted app runs without it.
    app.secret_key = _secret_key(app)
    # Every POST must carry the form's CSRF token (#27) - forms from forms.py add
    # it with hidden_tag(), and hand-written ones with csrf_token()
    CSRFProtect(app)
    # set the app configuration data 
    # A relative sqlite path lands in the instance/ folder (Flask-SQLAlchemy 3.x):
    # a2_group5/instance/sitedata.sqlite. The URL is fixed once init_app runs -
    # changing app.config afterwards has no effect. Tables are created at the
    # end of create_app().
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sitedata.sqlite'
    # initialise db with flask app
    db.init_app(app)

    # Bootstrap-Flask (Bootstrap 5): base_epicurean.html loads Bootstrap's CSS
    # with bootstrap.load_css() and builds the nav links with render_nav_item;
    # the category pages use render_pagination and render_breadcrumb_item.
    Bootstrap5(app)
    
    # initialise the login manager
    login_manager = LoginManager()
    
    # set the name of the login function that lets user login
    # in our case it is auth.login (blueprintname.viewfunction name)
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    # create a user loader function takes userid and returns User
    # Importing inside the create_app function avoids circular references
    # Flask-Login calls load_user on every request with the id stored in the
    # session cookie; whatever it returns becomes `current_user` everywhere,
    # including in templates.
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
       return db.session.scalar(db.select(User).where(User.id==user_id))

    # main_bp (views.py) = public site pages; auth_bp (auth.py) = register,
    # login, logout and the account page. Neither uses a url_prefix.
    from . import views
    app.register_blueprint(views.main_bp)

    from . import auth
    app.register_blueprint(auth.auth_bp)

    # Custom error pages (brief item 9). Registered on the app rather than a
    # blueprint so they catch errors from every route.
    # Note: with FLASK_DEBUG=1, crashes show Flask's debugger instead of the
    # 500 page.
    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    # A form posted without a valid CSRF token - usually one left open so long
    # its token expired. Go back to that page with a message, not an error page.
    @app.errorhandler(CSRFError)
    def csrf_error(error):
        flash('That form had expired, so nothing was changed. Please try again.', 'danger')
        back = request.referrer or ''
        on_site = back.startswith(request.host_url)
        return redirect(back if on_site else url_for('main.index'))

    @app.errorhandler(500)
    def server_error(error):
        # discard any half-finished database change so later requests aren't affected
        db.session.rollback()
        return render_template('500.html'), 500

    # Create any tables that don't exist yet, so a fresh clone works with just
    # `python main.py`, then add any columns an older database is missing.
    # Never drops or changes existing tables, columns or data.
    with app.app_context():
        db.create_all()
        add_missing_columns()

    return app