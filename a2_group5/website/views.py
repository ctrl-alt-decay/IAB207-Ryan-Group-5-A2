import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from . import db
from .models import Event, TicketType, Booking
from .forms import BookingForm

# Public site pages plus booking. Endpoints are referenced as 'main.<function>'
# in url_for(). The home, create-event, history and event pages still render
# static Assignment 1 content; booking and order confirmation use the database.
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return render_template('index.html')


# Login required (#5): logged-out visitors are sent to /login and brought back
# here afterwards via ?next=. The decorator guards POST as well as GET, so no
# event can ever be saved by someone who isn't logged in.
@main_bp.route('/create-event', methods=['GET', 'POST'])
@login_required
def create_event():
    if request.method == 'POST':
        # Saving isn't built yet (#19). When it is, the new event must be owned
        # by the logged-in user: Event(..., owner_id=current_user.id)
        flash('Saving events is not built yet.', 'info')
        return redirect(url_for('main.create_event'))
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


def _new_order_number():
    """Return an order number like 'EPI-64118' that no booking uses yet."""
    while True:
        number = 'EPI-{:05d}'.format(secrets.randbelow(100000))
        taken = db.session.scalar(db.select(Booking.id).where(Booking.order_number == number))
        if not taken:
            return number


# Buying tickets (#5). Login required; the booking is saved against the
# logged-in user. One ticket type per booking - the Booking table holds a single
# ticket_type_id and each order number is unique.
@main_bp.route('/event/<int:event_id>/book', methods=['GET', 'POST'])
@login_required
def book_tickets(event_id):
    event = db.get_or_404(Event, event_id)

    # A GET only happens when Flask-Login sends someone back here after they
    # logged in. Booking is POST-only, so return them to the event page to buy.
    # (That becomes this event's own page once #20 exists.)
    if request.method == 'GET':
        return redirect(url_for('main.view_event'))

    form = BookingForm()
    form.ticket_type.choices = [(t.id, t.name) for t in event.ticket_types]
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, 'danger')
        return redirect(url_for('main.view_event'))

    ticket = db.session.get(TicketType, form.ticket_type.data)
    quantity = form.quantity.data
    # TODO(#21): refuse Sold Out / Inactive / Cancelled events and check capacity
    booking = Booking(
        order_number=_new_order_number(),
        user_id=current_user.id,
        event_id=event.id,
        ticket_type_id=ticket.id,
        quantity=quantity,
        # priced on the server from the ticket type - never trusted from the page
        total_price=ticket.price * quantity,
    )
    db.session.add(booking)
    db.session.commit()
    return redirect(url_for('main.order_confirmation', order_number=booking.order_number))


# Shown straight after a successful booking. Only the user who made the booking
# can open it - anyone else gets a 404, so order numbers can't be probed.
@main_bp.route('/order/<order_number>')
@login_required
def order_confirmation(order_number):
    booking = db.first_or_404(db.select(Booking).where(
        Booking.order_number == order_number,
        Booking.user_id == current_user.id))
    return render_template('order_confirmation.html', booking=booking)
