from flask import Blueprint, flash, render_template, request, url_for, redirect
from flask_bcrypt import check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from .models import User, hash_password
from .forms import LoginForm, RegisterForm, ProfilePictureForm
from .uploads import PROFILE_IMAGES, save_upload, delete_upload
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

        user = User(
            first_name=register_form.first_name.data.strip(),
            last_name=register_form.last_name.data.strip(),
            email=email,
            password_hash=hash_password(register_form.password.data),
            contact_number=register_form.contact_number.data.strip(),
            street_address=register_form.street_address.data.strip(),
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Welcome to Epicurean, {}! Your account has been created.'.format(
            user.first_name), 'success')
        return redirect(url_for('auth.account'))

    return render_template('register.html', form=register_form)


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

    return render_template('login.html', form=login_form)


@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    picture_form = ProfilePictureForm()

    if picture_form.validate_on_submit():
        old_name = current_user.profile_image
        current_user.profile_image = save_upload(picture_form.picture.data, PROFILE_IMAGES)
        delete_upload(old_name, PROFILE_IMAGES)
        db.session.commit()
        flash('Your profile picture has been updated.', 'success')
        return redirect(url_for('auth.account'))

    for errors in picture_form.picture.errors:
        flash(errors, 'danger')

    return render_template('account.html', picture_form=picture_form)


@auth_bp.route('/account/picture/remove', methods=['POST'])
@login_required
def remove_picture():
    if current_user.profile_image:
        delete_upload(current_user.profile_image, PROFILE_IMAGES)
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
