# import flask - from 'package' import 'Class'
from flask import Flask, render_template
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Shared database handle. Created unbound so models.py can import it without an
# app existing yet; create_app() binds it with db.init_app(app).
db = SQLAlchemy()

# create a function that creates a web application
# a web server will run this web application
def create_app():
  
    app = Flask(__name__)  # this is the name of the module/package that is calling this app
    # Should be set to false in a production environment
    app.debug = True
    app.secret_key = 'somesecretkey'
    # set the app configuration data 
    # A relative sqlite path lands in the instance/ folder (Flask-SQLAlchemy 3.x):
    # a2_group5/instance/sitedata.sqlite. The URL is fixed once init_app runs -
    # changing app.config afterwards has no effect. Tables are created at the
    # end of create_app().
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sitedata.sqlite'
    # initialise db with flask app
    db.init_app(app)

    # bootstrap-flask's Bootstrap 5 helpers. Only the starter templates (base.html,
    # user.html) would use these; the Epicurean pages load Bootstrap 4 from a CDN
    # in base_epicurean.html, and no route renders the starter templates.
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
    # Note: while app.debug is True, crashes show Flask's debugger instead of
    # the 500 page. The 500 page appears once debug is switched off.
    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(error):
        # discard any half-finished database change so later requests aren't affected
        db.session.rollback()
        return render_template('500.html'), 500

    # Create any tables that don't exist yet, so a fresh clone works with just
    # `python main.py`. Never drops or alters existing tables or data.
    with app.app_context():
        db.create_all()

    return app