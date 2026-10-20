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

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    register_form = RegisterForm()
    if register_form.validate_on_submit():
        email = register_form.email.data.strip().lower()

        existing = db.session.scalar(db.select(User).where(User.email == email))
        if existing is not None:
            flash('An account with that email already exists. Try logging in.',
                  'danger')
            return redirect(url_for('auth.register'))

        # bcrypt returns bytes
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

        login_user(user)
        flash('Welcome to Epicurean, {}! Your account has been created.'.format(
            user.first_name), 'success')
        return redirect(url_for('auth.account'))

    return render_template('register.html', form=register_form,
                           heading='Sign Up')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    login_form = LoginForm()
    error = None
    if login_form.validate_on_submit():
        email = login_form.email.data.strip().lower()
        password = login_form.password.data
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user is None:
            error = 'Incorrect email address'
        elif not check_password_hash(user.password_hash, password):
            error = 'Incorrect password'
        if error is None:
            login_user(user)
            flash('Welcome back, {}.'.format(user.first_name), 'success')
            # local_path blocks open redirects like ?next=//other-site.com
            nextp = local_path(request.args.get('next'))
            return redirect(nextp or url_for('auth.account'))
        else:
            flash(error, 'danger')

    return render_template('login.html', form=login_form, heading='Login')


# relative to the static folder
PROFILE_UPLOAD_DIR = os.path.join('uploads', 'profile')


@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    picture_form = ProfilePictureForm()

    if picture_form.validate_on_submit():
        picture = picture_form.picture.data

        # uuid name so two users uploading "me.jpg" don't clobber each other
        safe_name = secure_filename(picture.filename)
        ext = safe_name.rsplit('.', 1)[-1].lower()
        stored_name = '{}.{}'.format(uuid.uuid4().hex, ext)

        upload_dir = os.path.join(current_app.static_folder, PROFILE_UPLOAD_DIR)
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        picture.save(os.path.join(upload_dir, stored_name))

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


# POST-only so a link or <img> on another site can't log someone out.
@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))
