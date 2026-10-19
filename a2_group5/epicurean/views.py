import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   current_app, abort)
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import false
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
# The card grid is 5 a row from 1400px wide and 4 below that, so the section
# and page sizes are multiples of 5 (and of 2, for the 2-a-row tablet grid).
RECENTLY_ADDED_SIZE = 4
SECTION_SIZE = 10
# Category pages ("Explore more events") and search results: events per page
EVENTS_PER_PAGE = 20
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
    """Not cancelled and not already past (#15). The homepage, the category
    pages and search only list these; every event's own page still opens by
    its link."""
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
    # the filter dropdowns' options come from EventForm, so the homepage, the
    # search results page and Create Event can never get out of sync
    return render_template('index.html', sections=sections, liked_ids=_liked_event_ids(),
                           dietary_options=EventForm.DIETARY, seasonal_options=EventForm.SEASONAL,
                           proficiency_options=EventForm.PROFICIENCY)


# One category's events, most liked first, EVENTS_PER_PAGE to a page
# (?page=2 ...). Linked from each homepage section's "Explore more events".
@main_bp.route('/events/<slug>')
def category(slug):
    if slug not in CATEGORIES:
        abort(404)
    events = db.paginate(_category_query(slug), per_page=EVENTS_PER_PAGE, error_out=True)
    return render_template('events.html', heading=CATEGORIES[slug][0], slug=slug, events=events,
                           liked_ids=_liked_event_ids())


# About page (linked from the footer, #30). The numbers strip is live from the
# database, so it grows as people list events and book tickets.
@main_bp.route('/about')
def about():
    stats = [
        ('Events listed', db.session.scalar(db.select(db.func.count(Event.id)))),
        ('Cities', db.session.scalar(db.select(db.func.count(db.distinct(Event.city))))),
        ('Likes', db.session.scalar(db.select(db.func.coalesce(db.func.sum(Event.likes), 0)))),
        ('Tickets booked', db.session.scalar(db.select(db.func.coalesce(db.func.sum(Booking.quantity), 0)))),
    ]
    return render_template('about.html', stats=stats)


# ---- Keyword search (#17) and filters (#16) -------------------------------
# The navbar search bar (#17, base_epicurean.html) and the homepage filter
# dropdowns (#16, index.html) both post here as plain GET forms - no JavaScript,
# so a search is just a shareable, bookmarkable URL
# (e.g. /search?q=ramen&dietary=Vegan). Query params:
#   q                                - free text: matched against the title,
#                                       description and venue
#   dietary, seasonal, proficiency   - exact match against the matching Event
#                                       column; missing or 'None' means no
#                                       filter on that one
#   date_from, date_to               - the date range (#38), YYYY-MM-DD as sent
#                                       by <input type="date">: events on or
#                                       after date_from and on or before
#                                       date_to. Either can be left out for an
#                                       open-ended range; an unreadable date is
#                                       ignored, and a date_to before date_from
#                                       matches nothing (see _date_range)
# TODO (AI-enhanced discovery): `q` currently does a plain case-insensitive
# substring match. The brief's AI-enhanced discovery requirement belongs here -
# e.g. ranking/matching with sentence-transformers embeddings over the title +
# description instead of (or as well as) the substring match below. Left for
# a follow-up once this plain version is confirmed working.
FILTER_PARAMS = {
    'dietary': Event.dietary_preference,
    'seasonal': Event.seasonal_cultural,
    'proficiency': Event.proficiency,
}


LIKE_ESCAPE = '\\'   # the escape character used in the ilike(...) calls below


def _contains(text):
    """'%text%' for ilike, with any % or _ the user typed matched literally.
    In a LIKE pattern % means "any amount of anything" and _ means "any one
    character", so typed unescaped they would match far too much (searching
    just % would return every event). The escape character itself is escaped
    first, so a typed backslash is matched literally too. Use it with
    column.ilike(_contains(text), escape=LIKE_ESCAPE)."""
    for special in (LIKE_ESCAPE, '%', '_'):
        text = text.replace(special, LIKE_ESCAPE + special)
    return '%{}%'.format(text)


def _filter_value(args, param):
    """The chosen value for one of the dropdown filters, or '' if it's missing
    or left on 'None' (which means "don't filter on this one")."""
    value = (args.get(param) or '').strip()
    return '' if value == 'None' else value


def _parse_date(args, param):
    """The date typed into the `param` box (YYYY-MM-DD, which is what
    <input type="date"> sends), or None if it's missing or not a real date
    (e.g. a hand-edited URL like ?date_from=banana or 2026-02-31)."""
    value = (args.get(param) or '').strip()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _date_range(args):
    """(start, end, problem) for the date_from / date_to boxes. start and end
    are dates or None (no limit on that side). problem is a short message for
    the page when the range can't be used, else None:
      - a date that couldn't be read is ignored, and the page says so;
      - an end date before the start date can never match anything, so
        _search_query returns no events and the page explains why."""
    start, end = _parse_date(args, 'date_from'), _parse_date(args, 'date_to')
    unreadable = [label for param, label, parsed in
                  (('date_from', 'From', start), ('date_to', 'To', end))
                  if (args.get(param) or '').strip() and parsed is None]
    if unreadable:
        return start, end, ("The {} date wasn't a valid date, so it was ignored."
                            .format(' and '.join(unreadable)))
    if start and end and end < start:
        return start, end, 'The To date is before the From date, so no events can match.'
    return start, end, None


def _search_query(args):
    """The Event select for a search/filter request, built from `args`
    (request.args): upcoming and not cancelled, like every other listing page,
    narrowed by whichever of q / dietary / seasonal / proficiency /
    date_from / date_to were actually given."""
    query = db.select(Event).where(_upcoming())

    start, end, _problem = _date_range(args)
    if start and end and end < start:
        query = query.where(false())     # an impossible range matches nothing
    else:
        if start:
            query = query.where(Event.event_date >= start)
        if end:
            query = query.where(Event.event_date <= end)

    text = (args.get('q') or '').strip()
    if text:
        pattern = _contains(text)
        query = query.where(db.or_(
            Event.title.ilike(pattern, escape=LIKE_ESCAPE),
            Event.description.ilike(pattern, escape=LIKE_ESCAPE),
            Event.venue.ilike(pattern, escape=LIKE_ESCAPE)))

    for param, column in FILTER_PARAMS.items():
        value = _filter_value(args, param)
        if value:
            query = query.where(column == value)

    return query.order_by(Event.likes.desc(), Event.event_date, Event.event_time, Event.id)


def _has_search_criteria(args):
    """True if the request actually asked for anything (so the page can tell
    "no events listed yet" apart from "nothing matched your search"). A
    dropdown left on 'None' isn't a criterion."""
    return (any((args.get(key) or '').strip()
                for key in ('q', 'date_from', 'date_to'))
            or any(_filter_value(args, param) for param in FILTER_PARAMS))


# Search results: reached from the navbar search bar (#17) and the homepage
# filter dropdowns (#16). Same layout as a category page - most liked first,
# paginated, and a page number past the end is a 404 like the category pages -
# plus a "refine your search" panel so the keywords and filters can be changed
# without going back to the homepage. filters_active tells the page to open
# its Advanced search section, so the filters narrowing the results stay visible.
@main_bp.route('/search')
def search():
    events = db.paginate(_search_query(request.args), per_page=EVENTS_PER_PAGE, error_out=True)
    start, end, date_problem = _date_range(request.args)
    return render_template(
        'search.html', events=events, liked_ids=_liked_event_ids(),
        has_criteria=_has_search_criteria(request.args),
        # the dates to echo back into the two date boxes (only readable ones)
        date_from=start.isoformat() if start else '',
        date_to=end.isoformat() if end else '',
        date_problem=date_problem,
        filters_active=any(_filter_value(request.args, param) for param in FILTER_PARAMS),
        dietary_options=EventForm.DIETARY, seasonal_options=EventForm.SEASONAL,
        proficiency_options=EventForm.PROFICIENCY)


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
    # "Preview acknowledgement" posts the form too, but only to show the
    # statement its answers would give - nothing is checked or saved
    if 'preview_ack' in request.form:
        return render_template('listevent.html', form=form,
                               ack_preview=_acknowledgement_preview(form))
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
            city=event.city or '',
            event_date=event.event_date, event_time=event.event_time,
            dietary_preference=event.dietary_preference or 'None',
            seasonal_cultural=event.seasonal_cultural or 'None',
            proficiency=event.proficiency or 'None',
            acknowledgement_type=event.acknowledgement_type or 'None',
            acknowledgement_city=event.acknowledgement_city,
            acknowledgement_custodians=event.acknowledgement_custodians,
            acknowledgement_connection=event.acknowledgement_connection,
            acknowledgement_commitment=event.acknowledgement_commitment,
            acknowledgement_elders=event.acknowledgement_elders,
            ticket_types=[{'included': True, 'ticket_id': t.id, 'name': t.name,
                           'price': t.price, 'capacity': t.capacity,
                           'description': t.description}
                          for t in event.ticket_types])
    form.original_date = event.event_date
    form.submit.label.text = 'Save Changes'

    if 'preview_ack' in request.form:   # show the statement only - nothing saved
        return render_template('listevent.html', form=form, event=event,
                               ack_preview=_acknowledgement_preview(form))
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
    event.city = form.city.data
    event.event_date = form.event_date.data
    event.event_time = form.event_time.data
    # the 'None' option is stored as an empty column
    event.dietary_preference = _none_to_null(form.dietary_preference.data)
    event.seasonal_cultural = _none_to_null(form.seasonal_cultural.data)
    event.proficiency = _none_to_null(form.proficiency.data)
    event.acknowledgement_type = ack_type
    # answers left in the Enhanced builder before switching away are dropped
    enhanced = ack_type == 'Enhanced'
    event.acknowledgement_city = form.acknowledgement_city.data if enhanced else None
    event.acknowledgement_custodians = (
        (form.acknowledgement_custodians.data or '').strip() or None if enhanced else None)
    event.acknowledgement_connection = (
        (form.acknowledgement_connection.data or '').strip() or None if enhanced else None)
    event.acknowledgement_commitment = (
        (form.acknowledgement_commitment.data or '').strip() or None if enhanced else None)
    event.acknowledgement_elders = bool(form.acknowledgement_elders.data)


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


@main_bp.app_template_filter('ack_text')
def ack_text(statement, event_title=None):
    """One of the written statements in EventForm (GENERIC_ACK_PREVIEW or a
    city's ENHANCED_ACK_PREVIEW) ready to show: {eventname} filled in with the
    event's title ("this event" before it has one), and the line breaks and
    indentation from the source file collapsed to single spaces. Also a
    template filter: {{ form.GENERIC_ACK_PREVIEW|ack_text(form.title.data) }}."""
    title = (event_title or '').strip() or 'this event'
    # replace, not str.format: a title with { or } in it mustn't break it
    return ' '.join((statement or '').replace('{eventname}', title).split())


def compose_acknowledgement(ack_type, city, custodians, connection, commitment, elders,
                            event_title=None):
    """The Acknowledgement of Country statement for these answers, or None for
    'None'. Generic is the written generic statement. Enhanced is put together
    from the builder's answers:
      - the opening: the chosen capital's written statement, which names its
        Traditional Custodians (ENHANCED_ACK_PREVIEW) - or, for 'Other' or when
        the creator typed the custodians in, a sentence naming those;
      - then how the event connects to Country and the optional commitment;
      - then respects to Elders, if ticked and the opening doesn't already."""
    if ack_type == 'Generic':
        return ack_text(EventForm.GENERIC_ACK_PREVIEW, event_title)
    if ack_type != 'Enhanced':
        return None
    custodians = re.sub(r'^the\s+', '', (custodians or '').strip(), flags=re.IGNORECASE)
    written = EventForm.ENHANCED_ACK_PREVIEW.get('{}-AoC'.format(city), '')
    if custodians:   # "the" is added here
        parts = ['We acknowledge the {}, the Traditional Custodians of the land where this '
                 'event takes place.'.format(custodians)]
    elif written:
        parts = [ack_text(written, event_title)]
    else:
        parts = ['We acknowledge the Traditional Custodians of the land where this event '
                 'takes place.']
    for answer in (connection, commitment):
        answer = (answer or '').strip()
        if answer:
            parts.append(answer if answer[-1] in '.!?' else answer + '.')
    if elders and 'elders' not in parts[0].lower():
        parts.append('We pay our respects to their Elders past and present.')
    return ' '.join(parts)


def _acknowledgement_statement(event):
    """The Acknowledgement of Country shown on the event page, or None."""
    return compose_acknowledgement(
        event.acknowledgement_type, event.acknowledgement_city,
        event.acknowledgement_custodians, event.acknowledgement_connection,
        event.acknowledgement_commitment, event.acknowledgement_elders, event.title)


def _acknowledgement_preview(form):
    """The statement the Create/Edit Event form's current answers would give -
    for its "Preview acknowledgement" button, which shows it without saving."""
    statement = compose_acknowledgement(
        form.acknowledgement_type.data, form.acknowledgement_city.data,
        form.acknowledgement_custodians.data, form.acknowledgement_connection.data,
        form.acknowledgement_commitment.data, form.acknowledgement_elders.data,
        form.title.data)
    return statement or 'No Acknowledgement of Country will be shown on your event page.'


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
