from flask import Blueprint, render_template

# Public site pages. Endpoints are referenced as 'main.<function>' in url_for().
# All four currently render static Assignment 1 designs - none of them read
# from the database yet (the templates hold hardcoded example content).
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/create-event')
def create_event():
    # placeholder - the A1 Create Event page, not yet wired to the database
    return render_template('listevent.html')


@main_bp.route('/history')
def history():
    # placeholder - the A1 Booking History page, not yet wired to the database
    return render_template('history.html')


@main_bp.route('/event')
def view_event():
    # placeholder - every event card links here until real event pages exist
    return render_template('viewitem.html')
