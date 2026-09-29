import os
import uuid

from flask import (Blueprint, flash, render_template, request, url_for,
                   redirect, current_app)
from werkzeug.utils import secure_filename
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from .models import User
from .forms import LoginForm, RegisterForm, ProfilePictureForm
from .views import local_path
from . import db

# Account routes: register, login, logout, the account page and profile pictures.
# Endpoints are referenced as 'auth.<function>' in url_for().
# Create a blueprint - make sure all BPs have unique names
auth_bp = Blueprint('auth', __name__)


# GET shows the sign-up form. A valid POST creates the User, logs them straight
# in and sends them to /account.
@auth_bp.route('/register', methods=['GET', 'POST'])
# view function
def register():
    # already signed in - nothing to register
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    register_form = RegisterForm()
    if register_form.validate_on_submit():
        # emails are stored lowercased so 'Amy@x.com' and 'amy@x.com' are one account
        email = register_form.email.data.strip().lower()

        # email is unique on the User model, so check before inserting
        existing = db.session.scalar(db.select(User).where(User.email == email))
        if existing is not None:
            flash('An account with that email already exists. Try logging in.',
                  'danger')
            return redirect(url_for('auth.register'))

        # flask_bcrypt returns bytes; password_hash is a String column
        pwd_hash = generate_password_hash(
            register_form.password.data).decode('utf-8')

        user = User(
            first_name=register_form.first_name.data.strip(),
            last_name=register_form.last_name.data.strip(),
            email=email,
            password_hash=pwd_hash,
            contact_number=register_form.contact_number.data.strip(),
            street_address=register_form.street_address.data.strip(),
        )
        db.session.add(user)
        db.session.commit()

        # log the new account straight in
        login_user(user)
        flash('Welcome to Epicurean, {}! Your account has been created.'.format(
            user.first_name), 'success')
        return redirect(url_for('auth.account'))

    return render_template('register.html', form=register_form,
                           heading='Sign Up')


# this is a hint for a login function
@auth_bp.route('/login', methods=['GET', 'POST'])
# view function
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    # a valid POST checks the email, then the bcrypt hash; one of two errors is
    # flashed on failure
    login_form = LoginForm()
    error = None
    if login_form.validate_on_submit():
        email = login_form.email.data.strip().lower()
        password = login_form.password.data
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user is None:
            error = 'Incorrect email address'
        elif not check_password_hash(user.password_hash, password):  # takes the hash and cleartext password
            error = 'Incorrect password'
        if error is None:
            login_user(user)
            flash('Welcome back, {}.'.format(user.first_name), 'success')
            # ?next= is the page that sent them here to log in (#5, #27). Only
            # follow it if it's a page on this site - local_path refuses
            # '//other-site.com' and the like - otherwise go to the account page.
            nextp = local_path(request.args.get('next'))
            return redirect(nextp or url_for('auth.account'))
        else:
            flash(error, 'danger')

    return render_template('login.html', form=login_form, heading='Login')


# where uploaded profile pictures are stored, relative to the static folder
PROFILE_UPLOAD_DIR = os.path.join('uploads', 'profile')


# GET shows the user's details, activity counts and picture form.
# POST handles a profile picture upload (the form posts back to this same URL).
@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    picture_form = ProfilePictureForm()

    if picture_form.validate_on_submit():
        picture = picture_form.picture.data

        # secure_filename strips any path the browser sent; the uuid prefix stops
        # two users who both upload "me.jpg" from overwriting each other
        safe_name = secure_filename(picture.filename)
        ext = safe_name.rsplit('.', 1)[-1].lower()
        stored_name = '{}.{}'.format(uuid.uuid4().hex, ext)

        upload_dir = os.path.join(current_app.static_folder, PROFILE_UPLOAD_DIR)
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        picture.save(os.path.join(upload_dir, stored_name))

        # remove the previous picture so uploads don't pile up on disk
        old_name = current_user.profile_image
        if old_name:
            old_path = os.path.join(upload_dir, old_name)
            if os.path.exists(old_path):
                os.remove(old_path)

        current_user.profile_image = stored_name
        db.session.commit()
        flash('Your profile picture has been updated.', 'success')
        return redirect(url_for('auth.account'))

    for errors in picture_form.picture.errors:
        flash(errors, 'danger')

    return render_template('account.html', picture_form=picture_form)


# Deletes the picture file and clears the database reference. POST-only so a
# plain link or prefetch can't trigger it.
@auth_bp.route('/account/picture/remove', methods=['POST'])
@login_required
def remove_picture():
    stored_name = current_user.profile_image
    if stored_name:
        path = os.path.join(current_app.static_folder, PROFILE_UPLOAD_DIR, stored_name)
        if os.path.exists(path):
            os.remove(path)
        current_user.profile_image = None
        db.session.commit()
        flash('Your profile picture has been removed.', 'success')
    return redirect(url_for('auth.account'))


# @login_required sends anonymous visitors to /login instead of erroring.
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))
