import re
import secrets
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf

from . import db
from .models import Event, TicketType, Booking, Like, Comment, Order
from .forms import (OrderForm, EventForm, EditEventForm, CancelEventForm, LikeForm,
                    CommentForm)
from .uploads import EVENT_IMAGES, save_upload, delete_upload

from . import encoder
import json
import numpy as np
main_bp = Blueprint('main', __name__)

# Grid is 5 per row >=1400px, 4 below, 2 on tablet - keep sizes multiples of 5 and 2.
RECENTLY_ADDED_SIZE = 4
SECTION_SIZE = 10
EVENTS_PER_PAGE = 20
POPULAR_MIN_LIKES = 100
KID_TICKET_WORDS = ('child', 'kid', 'family')
# Brisbane - no DST, so a fixed offset is fine. Stored times are UTC.
SITE_TIMEZONE = timezone(timedelta(hours=10))


@main_bp.app_template_filter('local_time')
def local_time(value, fmt='%d/%m/%Y, %H:%M'):
    if value is None:
        return ''
    return value.replace(tzinfo=timezone.utc).astimezone(SITE_TIMEZONE).strftime(fmt)


@main_bp.app_template_filter('money')
def money(value):
    return '${:.2f}'.format(value)


def this_weekend(today):
    # (Fri, Sun). If it's already Fri-Sun, starts from today.
    if today.weekday() < 4:
        start = today + timedelta(days=4 - today.weekday())
    else:
        start = today
    return start, start + timedelta(days=6 - start.weekday())


def _kid_friendly():
    kids_ticket = db.or_(*[db.func.lower(TicketType.name).contains(word)
                           for word in KID_TICKET_WORDS])
    return db.or_(Event.proficiency == 'Family Friendly', Event.ticket_types.any(kids_ticket))


def _this_weekend_filter():
    start, end = this_weekend(date.today())
    return Event.event_date.between(start, end)


def _upcoming():
    return db.and_(Event.status != 'Cancelled', Event.event_date >= date.today())


# Rules are lambdas so dates are evaluated per request, not at import.
CATEGORIES = {
    'popular': ('Popular', lambda: Event.likes >= POPULAR_MIN_LIKES),
    'this-weekend': ('This Weekend', _this_weekend_filter),
    'kid-friendly': ('Kid Friendly', _kid_friendly),
}


MOST_LIKED_FIRST = (Event.likes.desc(), Event.event_date, Event.event_time, Event.id)


def _category_query(slug):
    heading, rule = CATEGORIES[slug]
    return db.select(Event).where(rule(), _upcoming()).order_by(*MOST_LIKED_FIRST)


def _liked_event_ids():
    if not current_user.is_authenticated:
        return set()
    return set(db.session.scalars(db.select(Like.event_id).where(Like.user_id == current_user.id)))


# Global rather than a context processor so imported macros can see it.
@main_bp.app_template_global('csrf_token')
def csrf_token():
    return generate_csrf()


# Each section prefers events not shown above it, and only tops up with
# repeats if it can't fill otherwise.
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
        # repeats can't reuse the card's HTML id
        sections.append(dict(heading=heading, events=events + repeats,
                             repeat_ids={event.id for event in repeats}, slug=slug))
    return render_template('index.html', sections=sections, liked_ids=_liked_event_ids())


@main_bp.route('/events/<slug>')
def category(slug):
    if slug not in CATEGORIES:
        abort(404)
    events = db.paginate(_category_query(slug), per_page=EVENTS_PER_PAGE, error_out=True)
    return render_template('events.html', heading=CATEGORIES[slug][0], slug=slug, events=events,
                           liked_ids=_liked_event_ids())


@main_bp.route('/about')
def about():
    stats = [
        ('Events listed', db.session.scalar(db.select(db.func.count(Event.id)))),
        ('Cities', db.session.scalar(db.select(db.func.count(db.distinct(Event.city))))),
        ('Likes', db.session.scalar(db.select(db.func.coalesce(db.func.sum(Event.likes), 0)))),
        ('Tickets booked', db.session.scalar(db.select(db.func.coalesce(db.func.sum(Booking.quantity), 0)))),
    ]
    return render_template('about.html', stats=stats)


# TODO: AI-enhanced discovery from the brief goes here (embeddings over
# title + description?). Plain substring match for now.
# (query param, label, column, options) - the homepage and search page both render these
SEARCH_FILTERS = [
    ('dietary', 'Dietary Preference', Event.dietary_preference, EventForm.DIETARY),
    ('seasonal', 'Seasonal / Cultural Options', Event.seasonal_cultural, EventForm.SEASONAL),
    ('proficiency', 'Proficiency Filter', Event.proficiency, EventForm.PROFICIENCY),
]
FILTER_PARAMS = {param: column for param, _, column, _ in SEARCH_FILTERS}


@main_bp.app_template_global('search_filters')
def search_filters():
    return [(param, label, options) for param, label, _, options in SEARCH_FILTERS]


LIKE_ESCAPE = '\\'


def _contains(text):
    # escape user-typed % and _ (and the escape char first), or searching "%" matches everything
    for special in (LIKE_ESCAPE, '%', '_'):
        text = text.replace(special, LIKE_ESCAPE + special)
    return '%{}%'.format(text)


def _filter_value(args, param):
    value = (args.get(param) or '').strip()
    return '' if value == 'None' else value


def _parse_date(args, param):
    value = (args.get(param) or '').strip()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _date_range(args):
    # problem is a message for the page, or None
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
    query = db.select(Event).where(_upcoming())

    start, end, _problem = _date_range(args)
    if start and end and end < start:
        query = query.where(db.false())
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
            Event.venue.ilike(pattern, escape=LIKE_ESCAPE),
            Event.city.ilike(pattern, escape=LIKE_ESCAPE)))

    for param, column in FILTER_PARAMS.items():
        value = _filter_value(args, param)
        if value:
            query = query.where(column == value)

    return query.order_by(*MOST_LIKED_FIRST)


def _has_search_criteria(args):
    # lets the page tell "no events yet" apart from "nothing matched"
    return (any((args.get(key) or '').strip()
                for key in ('q', 'date_from', 'date_to'))
            or any(_filter_value(args, param) for param in FILTER_PARAMS))


@main_bp.route('/search')
def search():
    if request.args.get('q') and request.args['q'] != "":
        if 'use_ai' in request.args:
            print('Semantic search selected.')
            query_embedding = encoder.encode(request.args['q'])
            events = db.session.scalars(db.select(Event)).all()
            results = []
            for event in events:
                event_embedding = np.array(json.loads(event.description_embedding))
                score = cosine_similarity(query_embedding, event_embedding)
                results.append([event, score])

            results.sort(key = lambda x : x[1], reverse = True)

            events =  [x[0] for x in results]

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

        else:
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
    # no keywords (homepage filters, dates only, Browse Events): normal search
    events = db.paginate(_search_query(request.args), per_page=EVENTS_PER_PAGE, error_out=True)
    start, end, date_problem = _date_range(request.args)
    return render_template(
        'search.html', events=events, liked_ids=_liked_event_ids(),
        has_criteria=_has_search_criteria(request.args),
        date_from=start.isoformat() if start else '',
        date_to=end.isoformat() if end else '',
        date_problem=date_problem,
        filters_active=any(_filter_value(request.args, param) for param in FILTER_PARAMS))


def local_path(path):
    # Open-redirect guard. Browsers treat '/\x' like '//x' and strip tabs/newlines,
    # so '/<tab>/evil.com' would become '//evil.com'.
    if not path or not path.startswith('/') or path.startswith('//'):
        return None
    if '\\' in path or any(ord(c) < 32 or c.isspace() for c in path):
        return None
    return path


# GET only happens via Flask-Login's ?next= after logging in.
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


@main_bp.route('/create-event', methods=['GET', 'POST'])
@login_required
def create_event():
    form = EventForm()
    # preview button posts the whole form - just render, don't validate or save
    if 'preview_ack' in request.form:
        return render_template('listevent.html', form=form,
                               ack_preview=_acknowledgement_preview(form))
    if form.validate_on_submit():
        embedding = encoder.encode(form.description.data)
        embedding_text = json.dumps(embedding.tolist())

        event = Event(owner_id=current_user.id,
                      image_filename=save_upload(form.image.data, EVENT_IMAGES),
                      description_embedding=embedding_text)
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
    # The real check - hiding the buttons in the template is just cosmetic.
    if event.owner_id != current_user.id:
        flash('Only the event\'s owner can edit or cancel it.', 'danger')
        return redirect(url_for('main.event_details', event_id=event.id))
    return None


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
        # Not obj=event - WTForms would use the raw TicketType rows over these
        # dicts, and the rows need included/ticket_id so saves update in place.
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

    if 'preview_ack' in request.form:
        return render_template('listevent.html', form=form, event=event,
                               ack_preview=_acknowledgement_preview(form))
    if form.validate_on_submit():
        problems = _ticket_change_problems(form, event)
        if not problems:
            _apply_event_details(event, form)
            if form.image.data:
                old_image = event.image_filename
                event.image_filename = save_upload(form.image.data, EVENT_IMAGES)
                delete_upload(old_image, EVENT_IMAGES)
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


# Soft delete so bookings and comments still point at the event.
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
    ack_type = form.acknowledgement_type.data
    event.title = form.title.data.strip()
    event.description = form.description.data.strip()
    event.venue = form.venue.data.strip()
    event.city = form.city.data
    event.event_date = form.event_date.data
    event.event_time = form.event_time.data
    event.dietary_preference = _none_to_null(form.dietary_preference.data)
    event.seasonal_cultural = _none_to_null(form.seasonal_cultural.data)
    event.proficiency = _none_to_null(form.proficiency.data)
    event.acknowledgement_type = ack_type
    # drop leftover Enhanced answers if they switched type
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
    return [entry.form for entry in form.ticket_types.entries if not entry.form.is_blank()]


def _apply_ticket_rows(event, form):
    # Rows with a known ticket_id update in place, others are added, and
    # anything left without a row is removed.
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
    # Blocks edits that would orphan bookings: removing a sold tier or
    # dropping capacity below what's sold.
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


@main_bp.route('/history')
@login_required
def history():
    my_events = db.session.scalars(
        db.select(Event)
        .where(Event.owner_id == current_user.id)
        .order_by(Event.event_date.desc(), Event.event_time.desc())).all()
    return render_template('history.html', orders=current_user.orders, my_events=my_events)


@main_bp.route('/event/<int:event_id>')
def event_details(event_id):
    return _event_page(db.get_or_404(Event, event_id))


def _event_page(event, checkout=None):
    # checkout set = render the checkout panel over the page
    is_owner = current_user.is_authenticated and event.owner_id == current_user.id
    comments = sorted(event.comments, key=lambda c: c.posted_at, reverse=True)
    return render_template('viewitem.html', event=event, is_owner=is_owner,
                           comments=comments, comment_form=CommentForm(),
                           sale_message=NOT_ON_SALE.get(event.effective_status),
                           checkout=checkout,
                           acknowledgement=_acknowledgement_statement(event))


# 'comment-error' flashes render in the comments section, not the page top.
# GET only happens via Flask-Login's ?next= after logging in.
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
    # collapses the triple-quoted source whitespace into single spaces
    title = (event_title or '').strip() or 'this event'
    # not str.format - a title containing { or } would blow up
    return ' '.join((statement or '').replace('{eventname}', title).split())


def compose_acknowledgement(ack_type, city, custodians, connection, commitment, elders,
                            event_title=None):
    # Enhanced: opening (typed custodians > city statement > fallback), then
    # connection, commitment, and Elders unless the opening already covers it.
    if ack_type == 'Generic':
        return ack_text(EventForm.GENERIC_ACK_PREVIEW, event_title)
    if ack_type != 'Enhanced':
        return None
    custodians = re.sub(r'^the\s+', '', (custodians or '').strip(), flags=re.IGNORECASE)
    written = EventForm.ENHANCED_ACK_PREVIEW.get('{}-AoC'.format(city), '')
    if custodians:   # leading "the" was stripped above, re-added here
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
    return compose_acknowledgement(
        event.acknowledgement_type, event.acknowledgement_city,
        event.acknowledgement_custodians, event.acknowledgement_connection,
        event.acknowledgement_commitment, event.acknowledgement_elders, event.title)


def _acknowledgement_preview(form):
    statement = compose_acknowledgement(
        form.acknowledgement_type.data, form.acknowledgement_city.data,
        form.acknowledgement_custodians.data, form.acknowledgement_connection.data,
        form.acknowledgement_commitment.data, form.acknowledgement_elders.data,
        form.title.data)
    return statement or 'No Acknowledgement of Country will be shown on your event page.'


def new_order_number():
    while True:
        number = 'EPI-{:05d}'.format(secrets.randbelow(100000))
        taken = db.session.scalar(db.select(Booking.id).where(Booking.order_number == number))
        if not taken:
            return number


NOT_ON_SALE = {
    'Cancelled': 'This event has been cancelled, so tickets are no longer on sale.',
    'Inactive': 'This event has already taken place, so tickets are no longer on sale.',
    'Sold Out': 'This event is sold out.',
}


def _tickets_section(event):
    return url_for('main.event_details', event_id=event.id) + '#ticketsSection'


def _requested_quantities(event, data):
    # Only reads this event's tiers, so another event's ticket ids can't sneak in.
    # Returns None after flashing if invalid.
    lines = []
    for ticket in event.ticket_types:
        value = data.get('qty-{}'.format(ticket.id), '').strip() or '0'
        if not value.isdigit():   # rejects negatives and decimals too
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
    # Shared by checkout and book_tickets so they can't disagree.
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


# GET so quantities survive the login redirect. book_tickets re-checks everything.
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


@main_bp.route('/event/<int:event_id>/book', methods=['GET', 'POST'])
@login_required
def book_tickets(event_id):
    event = db.get_or_404(Event, event_id)

    # GET only happens via Flask-Login's ?next= after logging in.
    if request.method == 'GET':
        return redirect(url_for('main.event_details', event_id=event.id))

    if not OrderForm().validate_on_submit():   # CSRF
        flash("Your order couldn't be confirmed. Please try again.", 'ticket-error')
        return redirect(_tickets_section(event))
    lines = _checked_order(event, request.form)
    if lines is None:
        return redirect(_tickets_section(event))

    order_number = new_order_number()
    booked_at = datetime.utcnow()
    for ticket, quantity in lines:
        db.session.add(Booking(
            order_number=order_number,
            user_id=current_user.id,
            event_id=event.id,
            ticket_type_id=ticket.id,
            quantity=quantity,
            # never trust a price from the client
            total_price=ticket.price * quantity,
            booked_at=booked_at,
        ))
    db.session.commit()
    return redirect(url_for('main.order_confirmation', order_number=order_number))


# 404 rather than 403 so order numbers can't be probed.
@main_bp.route('/order/<order_number>')
@login_required
def order_confirmation(order_number):
    lines = db.session.scalars(db.select(Booking).where(
        Booking.order_number == order_number,
        Booking.user_id == current_user.id)).all()
    if not lines:
        abort(404)
    return render_template('order_confirmation.html', order=Order(lines))

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
