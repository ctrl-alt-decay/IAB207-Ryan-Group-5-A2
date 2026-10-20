import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

# relative to the static folder
EVENT_IMAGES = os.path.join('uploads', 'events')
PROFILE_IMAGES = os.path.join('uploads', 'profile')


def save_upload(file, folder):
    # uuid name so two people uploading "me.jpg" don't clobber each other
    ext = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
    stored_name = '{}.{}'.format(uuid.uuid4().hex, ext)
    upload_dir = os.path.join(current_app.static_folder, folder)
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, stored_name))
    return stored_name


def delete_upload(filename, folder):
    # only ever looks in folder, so the sample events' photos in img/ are safe
    if filename:
        path = os.path.join(current_app.static_folder, folder, secure_filename(filename))
        if os.path.exists(path):
            os.remove(path)
