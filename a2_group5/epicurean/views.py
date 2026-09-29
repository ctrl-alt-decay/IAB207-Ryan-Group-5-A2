import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   current_app, abort)
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from werkzeug.utils import secure_filename

from . import db
from .models import Event, TicketType, Booking, Like, Comment, Order, orders_from
from .forms import (OrderForm, EventForm, EditEventForm, CancelEventForm, LikeForm,
                    CommentForm)

# Public site pages, events and booking. Endpoints are referenced as
# 'main.<function>' in url_for().
main_bp = Blueprint('main', __name__)

# where uploaded event images are stored, relative to the static folder
EVENT_UPLOAD_DIR = os.path.join('uploads', 'events')

# Homepage: Recently Added shows the newest few (so the team and the marker can
# find what they just created); each category section shows its top few.
RECENTLY_ADDED_SIZE = 4
SECTION_SIZE = 8
# Category pages ("Explore more events"): events per page
EVENTS_PER_PAGE = 12
# an event needs at least this many likes to count as Popular
POPULAR_MIN_LIKES = 100
# a ticket type with any of these in its name counts as a kids' ticket
KID_TICKET_WORDS = ('child', 'kid', 'family')
# Times like Booking.booked_at are stored in UTC and shown in Brisbane time,
# which is UTC+10 all year (Queensland has no daylight saving).
SITE_TIMEZONE = timezone(timedelta(hours=10))


@main_bp.app_template_filter('local_time')
def local_time(value, fmt='%d/%m/%Y, %H:%M'):
    """A stored UTC datetime as Brisbane time, e.g. {{ booking.booked_at|local_time }}."""
    if value is None:
        return ''
    return value.replace(tzinfo=timezone.utc).astimezone(SITE_TIMEZONE).strftime(fmt)


def this_weekend(today):
    """(Friday, Sunday) of the closest weekend: the coming one from Monday to
    Thursday, or the current one from today if it's already Fri, Sat or Sun."""
    if today.weekday() < 4:  # Monday-Thursday
        start = today + timedelta(days=4 - today.weekday())
    else:
        start = today
    return start, start + timedelta(days=6 - start.weekday())


def _kid_friendly():
    """Family Friendly proficiency, or any ticket type for children/families."""
    kids_ticket = db.or_(*[db.func.lower(TicketType.name).contains(word)
                           for word in KID_TICKET_WORDS])
    return db.or_(Event.proficiency == 'Family Friendly', Event.ticket_types.any(kids_ticket))


def _this_weekend_filter():
    start, end = this_weekend(date.today())
    return Event.event_date.between(start, end)


def _upcoming():
    """Not cancelled and not already past (#15). The homepage and the category
    pages only list these; every event's own page still opens by its link."""
    return db.and_(Event.status != 'Cancelled', Event.event_date >= date.today())


# The homepage's category sections, which also each have their own paginated
# page (main.category). Rules are evaluated when the page loads. On its category
# page an event is listed under every category it fits, but the homepage shows
# each event only once (see index). Everything is sorted by likes first.
CATEGORIES = {
    'popular': ('Popular', lambda: Event.likes >= POPULAR_MIN_LIKES),
    'this-weekend': ('This Weekend', _this_weekend_filter),
    'kid-friendly': ('Kid Friendly', _kid_friendly),
}


def _category_query(slug):
    heading, rule = CATEGORIES[slug]
    return (db.select(Event).where(rule(), _upcoming())
            .order_by(Event.likes.desc(), Event.event_date, Event.event_time, Event.id))


def _liked_event_ids():
    """The ids of the events the logged-in user has liked, so their hearts show
    filled in. Empty for visitors who aren't logged in."""
    if not current_user.is_authenticated:
        return set()
    return set(db.session.scalars(db.select(Like.event_id).where(Like.user_id == current_user.id)))


# csrf_token() for templates, for small forms written out by hand rather than
# from a form object (the like hearts). A template global, not a context
# processor, so the macros in _event_macros.html can use it too. LikeForm
# checks the token on submit.
@main_bp.app_template_global('csrf_token')
def csrf_token():
    return generate_csrf()


# Homepage (#15): Recently Added, then the top events of each category, each
# with an "Explore more events" link to its full page. For variety, a section
# prefers events not already shown above it; only if fewer than SECTION_SIZE of
# those fit does it top up with events already shown, so every section still
# fills up when enough events qualify. Empty sections are left off the page.
@main_bp.route('/')
def index():
    recent = db.session.scalars(
        db.select(Event).where(_upcoming())
        .order_by(Event.created_at.desc(), Event.id.desc())
        .limit(RECENTLY_ADDED_SIZE)).all()
    sections = [dict(heading='Recently Added', events=recent, repeat_ids=set(), slug=None)]
    shown = {event.id for event in recent}
    for slug, (heading, rule) in CATEGORIES.items():
        events = db.session.scalars(
            _category_query(slug).where(Event.id.not_in(shown)).limit(SECTION_SIZE)).all()
        repeats = []
        if len(events) < SECTION_SIZE:
            repeats = db.session.scalars(
                _category_query(slug).where(Event.id.in_(shown))
                .limit(SECTION_SIZE - len(events))).all()
        shown.update(event.id for event in events)
        # repeat_ids: cards already on the page, which mustn't repeat its id
        sections.append(dict(heading=heading, events=events + repeats,
                             repeat_ids={event.id for event in repeats}, slug=slug))
    return render_template('index.html', sections=sections, liked_ids=_liked_event_ids())


# One category's events, most liked first, EVENTS_PER_PAGE to a page
# (?page=2 ...). Linked from each homepage section's "Explore more events".
@main_bp.route('/events/<slug>')
def category(slug):
    if slug not in CATEGORIES:
        abort(404)
    events = db.paginate(_category_query(slug), per_page=EVENTS_PER_PAGE, error_out=True)
    return render_template('events.html', heading=CATEGORIES[slug][0], slug=slug, events=events,
                           liked_ids=_liked_event_ids())


def local_path(path):
    """`path` if it's a page on this site (e.g. '/events/popular?page=2'),
    otherwise None. For "go back to where you were" addresses that arrive in a
    request - the like form's `next`, and login's ?next= (auth.login) - so they
    can't be used to send people to another site. Refused: full addresses
    ('https://...'), '//other-site.com', backslashes ('/\\other-site.com'), and
    tabs, line breaks or other control characters, which browsers strip out
    ('/<tab>/other-site.com' would become '//other-site.com')."""
    if not path or not path.startswith('/') or path.startswith('//'):
        return None
    if '\\' in path or any(ord(c) < 32 or c.isspace() for c in path):
        return None
    return path


# Like / unlike an event: the heart on the event cards. It's a small form, so
# no JavaScript - this saves the change, then sends the browser back to the
# page it was on, scrolled to the same card (#event-<id>), with the new count.
# Login required, so each person can like an event once and unlike it again.
# A GET only happens when Flask-Login sends someone back here after they logged
# in; liking needs a POST, so show them the event instead.
@main_bp.route('/event/<int:event_id>/like', methods=['GET', 'POST'])
@login_required
def toggle_like(event_id):
    event = db.get_or_404(Event, event_id)
    if request.method == 'GET':
        return redirect(url_for('main.event_details', event_id=event.id))

    form = LikeForm()
    if form.validate_on_submit():
        like = db.session.scalar(db.select(Like).where(
            Like.user_id == current_user.id, Like.event_id == event.id))
        if like:
            db.session.delete(like)
            event.likes = max(event.likes - 1, 0)
        else:
            db.session.add(Like(user_id=current_user.id, event_id=event.id))
            event.likes += 1
        db.session.commit()
    else:
        flash("Your like couldn't be saved. Please try again.", 'danger')
    back = local_path(form.next.data) or url_for('main.index')
    return redirect('{}#event-{}'.format(back, event.id))


# Login required (#5): logged-out visitors are sent to /login and brought back
# here afterwards via ?next=. The decorator guards POST as well as GET, so no
# event can ever be saved by someone who isn't logged in.
@main_bp.route('/create-event', methods=['GET', 'POST'])
@login_required
def create_event():
    form = EventForm()
    if form.validate_on_submit():
        event = Event(owner_id=current_user.id,
                      image_filename=_save_event_image(form.image.data))
        _apply_event_details(event, form)
        _apply_ticket_rows(event, form)
        db.session.add(event)
        db.session.commit()
        flash('Your event "{}" has been created.'.format(event.title), 'success')
        return redirect(url_for('main.event_details', event_id=event.id))

    if request.method == 'POST':
        flash('Please fix the highlighted fields. If you chose an image, choose it again.',
              'danger')
    return render_template('listevent.html', form=form)


def _not_the_owner(event):
    """For the edit and cancel routes: if the logged-in user doesn't own the
    event, return a redirect back to its page (with a message) to send instead
    of doing anything; for the owner, None. This server-side check is the real
    protection - hiding the Edit/Cancel buttons from others is only a courtesy."""
    if event.owner_id != current_user.id:
        flash('Only the event\'s owner can edit or cancel it.', 'danger')
        return redirect(url_for('main.event_details', event_id=event.id))
    return None


# Edit Event (#24). Owner only. Reuses the Create Event page and form; the
# status can't be changed here (Cancel is its own action below).
@main_bp.route('/event/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    event = db.get_or_404(Event, event_id)
    refused = _not_the_owner(event)
    if refused:
        return refused
    if event.status == 'Cancelled':
        flash('"{}" has been cancelled, so it can no longer be edited.'.format(event.title),
              'info')
        return redirect(url_for('main.event_details', event_id=event.id))

    if request.method == 'POST':
        form = EditEventForm()
    else:
        # Fill the form from the event. Given explicitly rather than with
        # obj=event, because WTForms would then use event.ticket_types (plain
        # TicketType rows) over these dicts - and the rows need included=True
        # and their ticket_id so saving updates them instead of replacing them.
        form = EditEventForm(
            title=event.title, description=event.description, venue=event.venue,
            event_date=event.event_date, event_time=event.event_time,
            dietary_preference=event.dietary_preference or 'None',
            seasonal_cultural=event.seasonal_cultural or 'None',
            proficiency=event.proficiency or 'None',
            acknowledgement_type=event.acknowledgement_type or 'None',
            acknowledgement_city=event.acknowledgement_city,
            ticket_types=[{'included': True, 'ticket_id': t.id, 'name': t.name,
                           'price': t.price, 'capacity': t.capacity,
                           'description': t.description}
                          for t in event.ticket_types])
    form.original_date = event.event_date
    form.submit.label.text = 'Save Changes'

    if form.validate_on_submit():
        problems = _ticket_change_problems(form, event)
        if not problems:
            _apply_event_details(event, form)
            if form.image.data:
                old_image = event.image_filename
                event.image_filename = _save_event_image(form.image.data)
                _delete_uploaded_image(old_image)
            _apply_ticket_rows(event, form)
            db.session.commit()
            flash('Your changes to "{}" have been saved.'.format(event.title), 'success')
            return redirect(url_for('main.event_details', event_id=event.id))
        for problem in problems:
            flash(problem, 'danger')
    elif request.method == 'POST':
        flash('Please fix the highlighted fields. If you chose a new image, choose it again.',
              'danger')
    return render_template('listevent.html', form=form, event=event)


# Cancel Event (#24). Owner only. GET asks for confirmation; POST cancels.
# A soft delete: the status becomes Cancelled and the row stays, so bookings
# and comments made against the event keep pointing at it.
@main_bp.route('/event/<int:event_id>/cancel', methods=['GET', 'POST'])
@login_required
def cancel_event(event_id):
    event = db.get_or_404(Event, event_id)
    refused = _not_the_owner(event)
    if refused:
        return refused
    if event.status == 'Cancelled':
        flash('"{}" is already cancelled.'.format(event.title), 'info')
        return redirect(url_for('main.history'))

    form = CancelEventForm()
    if form.validate_on_submit():
        event.status = 'Cancelled'
        db.session.commit()
        flash('"{}" has been cancelled.'.format(event.title), 'success')
        return redirect(url_for('main.history'))
    return render_template('cancel_event.html', event=event, form=form)


def _apply_event_details(event, form):
    """Copy the form's fields onto the event - everything except the image,
    the ticket types and the status."""
    ack_type = form.acknowledgement_type.data
    event.title = form.title.data.strip()
    event.description = form.description.data.strip()
    event.venue = form.venue.data.strip()
    event.event_date = form.event_date.data
    event.event_time = form.event_time.data
    # the 'None' option is stored as an empty column
    event.dietary_preference = _none_to_null(form.dietary_preference.data)
    event.seasonal_cultural = _none_to_null(form.seasonal_cultural.data)
    event.proficiency = _none_to_null(form.proficiency.data)
    event.acknowledgement_type = ack_type
    # a city left selected before switching away from Enhanced is dropped
    event.acknowledgement_city = (form.acknowledgement_city.data
                                  if ack_type == 'Enhanced' else None)


def _ticket_rows(form):
    """The ticket rows actually filled in (removed and blank rows skipped)."""
    return [entry.form for entry in form.ticket_types.entries if not entry.form.is_blank()]


def _apply_ticket_rows(event, form):
    """Make the event's ticket types match the form. A row carrying the id of
    one of this event's ticket types updates it in place; any other row adds a
    new one; ticket types with no row left are removed. (For a new event there
    are no existing ones, so every row is added.)"""
    existing = {t.id: t for t in event.ticket_types}
    kept = set()
    for row in _ticket_rows(form):
        values = dict(name=row.name.data.strip(), price=row.price.data,
                      capacity=row.capacity.data,
                      description=(row.description.data or '').strip() or None)
        ticket = existing.get(row.ticket_id.data)
        if ticket is None or ticket.id in kept:
            event.ticket_types.append(TicketType(**values))
        else:
            kept.add(ticket.id)
            for name, value in values.items():
                setattr(ticket, name, value)
    for ticket_id, ticket in existing.items():
        if ticket_id not in kept:
            event.ticket_types.remove(ticket)  # delete-orphan deletes the row


def _ticket_change_problems(form, event):
    """Edits that would break existing bookings: removing a ticket type people
    have bought, or cutting its capacity below the tickets already sold.
    Returns a message for each."""
    existing = {t.id: t for t in event.ticket_types}
    problems = []
    kept = set()
    for row in _ticket_rows(form):
        ticket = existing.get(row.ticket_id.data)
        if ticket is None:
            continue
        kept.add(ticket.id)
        if row.capacity.data < ticket.tickets_sold:
            message = '{} tickets already sold'.format(ticket.tickets_sold)
            row.capacity.errors.append(message)
            problems.append('"{}": capacity can\'t go below the {}.'.format(ticket.name, message))
    for ticket_id, ticket in existing.items():
        if ticket_id not in kept and ticket.tickets_sold:
            problems.append('"{}" can\'t be removed - {} tickets have already been sold.'
                            .format(ticket.name, ticket.tickets_sold))
    return problems


def _none_to_null(value):
    return None if value == 'None' else value


def _save_event_image(image):
    """Save an uploaded event image under static/uploads/events/ and return the
    stored filename (a random name, so two uploads called 'food.jpg' can't clash)."""
    ext = secure_filename(image.filename).rsplit('.', 1)[-1].lower()
    stored_name = '{}.{}'.format(uuid.uuid4().hex, ext)
    upload_dir = os.path.join(current_app.static_folder, EVENT_UPLOAD_DIR)
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    image.save(os.path.join(upload_dir, stored_name))
    return stored_name


def _delete_uploaded_image(filename):
    """Remove an event's old uploaded image. Only files in uploads/events/ are
    touched - the sample events' photos in img/ are shared site files."""
    if filename:
        path = os.path.join(current_app.static_folder, EVENT_UPLOAD_DIR,
                            secure_filename(filename))
        if os.path.exists(path):
            os.remove(path)


# Booking history (#22): the user's own orders, newest first - an order's
# bookings (one per ticket type) are grouped into one row - plus (#24) the
# events they have created themselves.
@main_bp.route('/history')
@login_required
def history():
    orders = orders_from(db.session.scalars(
        db.select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.booked_at.desc(), Booking.id.desc())))
    my_events = db.session.scalars(
        db.select(Event)
        .where(Event.owner_id == current_user.id)
        .order_by(Event.event_date.desc(), Event.event_time.desc())).all()
    return render_template('history.html', orders=orders, my_events=my_events)


# An event's own page (#20): the same layout for every event, filled from its row.
@main_bp.route('/event/<int:event_id>')
def event_details(event_id):
    return _event_page(db.get_or_404(Event, event_id))


def _event_page(event, checkout=None):
    """Render an event's page. With `checkout` (from main.checkout: the chosen
    ticket type, quantity and total), the checkout screen is shown over it."""
    is_owner = current_user.is_authenticated and event.owner_id == current_user.id
    comments = sorted(event.comments, key=lambda c: c.posted_at, reverse=True)
    return render_template('viewitem.html', event=event, is_owner=is_owner,
                           comments=comments, comment_form=CommentForm(),
                           sale_message=NOT_ON_SALE.get(event.effective_status),
                           checkout=checkout,
                           acknowledgement=_acknowledgement_statement(event))


# Posting a comment (#23). Login required, so every comment has a name on it;
# everyone - logged in or not - can read them on the event page. Afterwards the
# browser goes back to the event page's Comments section, where the new comment
# is first in the list, or where a refusal is shown ('comment-error' messages
# appear there, not at the top of the page). A GET only happens when
# Flask-Login sends someone back here after they logged in, so show them the
# event to write their comment there.
@main_bp.route('/event/<int:event_id>/comment', methods=['GET', 'POST'])
@login_required
def post_comment(event_id):
    event = db.get_or_404(Event, event_id)
    comments_section = url_for('main.event_details', event_id=event.id) + '#comments'
    if request.method == 'GET':
        return redirect(comments_section)

    form = CommentForm()
    if form.validate_on_submit():
        db.session.add(Comment(event_id=event.id, user_id=current_user.id,
                               body=form.body.data.strip()))
        db.session.commit()
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, 'comment-error')
    return redirect(comments_section)


def _acknowledgement_statement(event):
    """The Acknowledgement of Country shown on the event page, or None.
    PLACEHOLDER wording (from EventForm) until the real copy is written."""
    if event.acknowledgement_type == 'Generic':
        return EventForm.GENERIC_ACK_PREVIEW
    if event.acknowledgement_type == 'Enhanced' and event.acknowledgement_city:
        return EventForm.ENHANCED_ACK_PREVIEW.format(event.acknowledgement_city)
    return None


def new_order_number():
    """Return an order number like 'EPI-64118' that no booking uses yet."""
    while True:
        number = 'EPI-{:05d}'.format(secrets.randbelow(100000))
        taken = db.session.scalar(db.select(Booking.id).where(Booking.order_number == number))
        if not taken:
            return number


# Why tickets can't be bought, by effective_status (#25). Open isn't here - an
# Open event is on sale. Shown on the event page and by main.book_tickets.
NOT_ON_SALE = {
    'Cancelled': 'This event has been cancelled, so tickets are no longer on sale.',
    'Inactive': 'This event has already taken place, so tickets are no longer on sale.',
    'Sold Out': 'This event is sold out.',
}


def _tickets_section(event):
    return url_for('main.event_details', event_id=event.id) + '#ticketsSection'


def _requested_quantities(event, data):
    """How many of each of the event's ticket types were asked for, from form
    data with a 'qty-<ticket type id>' field per type (the Tickets table, or
    the checkout screen's Confirm form). Only this event's ticket types are
    read, so another event's can't sneak in. Returns [(ticket, quantity)] for
    those above 0, or flashes why not and returns None."""
    lines = []
    for ticket in event.ticket_types:
        value = data.get('qty-{}'.format(ticket.id), '').strip() or '0'
        if not value.isdigit():   # also refuses negatives and decimals
            flash('Quantities must be whole numbers, 0 or more.', 'ticket-error')
            return None
        if int(value):
            lines.append((ticket, int(value)))
    if not lines:
        flash('Choose how many tickets you would like of at least one ticket type.',
              'ticket-error')
        return None
    return lines


def _checked_order(event, data):
    """Check an order for `event` - used by both the checkout screen and the
    final booking, so they can't disagree. Returns its lines,
    [(ticket, quantity)], if it can go ahead. If not, flashes why as a
    'ticket-error' (the event page shows those in its Tickets section, where
    the browser is sent back to) and returns None. Checked on the server, so a
    request made straight to the URL is refused too: the event must be on sale
    (not Cancelled, Inactive or Sold Out - #25), and every ticket type ordered
    must have enough tickets left."""
    if event.effective_status in NOT_ON_SALE:
        flash(NOT_ON_SALE[event.effective_status], 'ticket-error')
        return None
    lines = _requested_quantities(event, data)
    if lines is None:
        return None
    ok = True
    for ticket, quantity in lines:
        if quantity > ticket.tickets_left:
            ok = False
            if ticket.tickets_left:
                flash('Only {} {} ticket{} left - please choose {} or fewer.'.format(
                    ticket.tickets_left, ticket.name, 's' if ticket.tickets_left != 1 else '',
                    ticket.tickets_left), 'ticket-error')
            else:
                flash('{} tickets are sold out.'.format(ticket.name), 'ticket-error')
    return lines if ok else None


# The checkout screen (#21). Checkout under the event page's ticket table opens
# it - a GET form, so the chosen quantities are in the URL. It's the event page
# with the checkout panel over it: the order's lines and total on the right,
# demo payment options on the left, and Confirm / Cancel. Confirm posts to
# main.book_tickets, which checks the order again. Login required; a logged-out
# visitor is brought back here after logging in.
@main_bp.route('/event/<int:event_id>/checkout')
@login_required
def checkout(event_id):
    event = db.get_or_404(Event, event_id)
    lines = _checked_order(event, request.args)
    if lines is None:
        return redirect(_tickets_section(event))
    lines = [(ticket, quantity, ticket.price * quantity) for ticket, quantity in lines]
    return _event_page(event, checkout=dict(lines=lines,
                                            total=sum(line[2] for line in lines)))


# Buying tickets (#5, #21): Confirm on the checkout screen posts here. Login
# required. One order can have several ticket types: it's saved as one Booking
# per ticket type, all sharing a new order number (see Booking in models.py).
@main_bp.route('/event/<int:event_id>/book', methods=['GET', 'POST'])
@login_required
def book_tickets(event_id):
    event = db.get_or_404(Event, event_id)

    # A GET only happens when Flask-Login sends someone back here after they
    # logged in. Booking is POST-only, so return them to the event page to buy.
    if request.method == 'GET':
        return redirect(url_for('main.event_details', event_id=event.id))

    if not OrderForm().validate_on_submit():   # the CSRF token
        flash("Your order couldn't be confirmed. Please try again.", 'ticket-error')
        return redirect(_tickets_section(event))
    lines = _checked_order(event, request.form)
    if lines is None:
        return redirect(_tickets_section(event))

    order_number = new_order_number()
    booked_at = datetime.utcnow()   # the same for every line of the order
    for ticket, quantity in lines:
        db.session.add(Booking(
            order_number=order_number,
            user_id=current_user.id,
            event_id=event.id,
            ticket_type_id=ticket.id,
            quantity=quantity,
            # priced on the server from the ticket type - never trusted from the page
            total_price=ticket.price * quantity,
            booked_at=booked_at,
        ))
    db.session.commit()
    return redirect(url_for('main.order_confirmation', order_number=order_number))


# The order page: shown straight after buying, and from the order number in the
# booking history. Only the user who made the order can open it - anyone else
# gets a 404, so order numbers can't be probed.
@main_bp.route('/order/<order_number>')
@login_required
def order_confirmation(order_number):
    lines = db.session.scalars(db.select(Booking).where(
        Booking.order_number == order_number,
        Booking.user_id == current_user.id)).all()
    if not lines:
        abort(404)
    return render_template('order_confirmation.html', order=Order(lines))
