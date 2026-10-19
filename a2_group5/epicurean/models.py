# Database schema: user, event, ticket_type, booking, comment, event_like.
# Status-style fields are plain strings (SQLite has no enum type); the allowed
# values are listed beside each column and should be enforced by the forms.
# Each relationship(backref=...) adds an attribute on BOTH sides - e.g.
# User.events below also creates Event.owner.
import os

from . import db
from datetime import date, datetime
from flask import current_app
from flask_login import UserMixin


# A registered account. UserMixin gives Flask-Login the is_authenticated /
# get_id() hooks it needs. Users log in by email; password_hash is a bcrypt hash.
class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    street_address = db.Column(db.String(255), nullable=False)
    profile_image = db.Column(db.String(255))   # filename under static/uploads/profile/

    # one User -> many Events they created; gives event.owner
    events = db.relationship('Event', backref='owner', lazy=True)
    # one User -> many Bookings; gives booking.user
    bookings = db.relationship('Booking', backref='user', lazy=True)
    # one User -> many Comments; gives comment.user
    comments = db.relationship('Comment', backref='user', lazy=True)

    def __repr__(self):
        return "<User {} {}>".format(self.first_name, self.last_name)


# An event listed by a user (its owner). Prices and capacity are NOT stored here -
# they live on the event's TicketType rows.
class Event(db.Model):
    __tablename__ = 'event'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    description_embedding = db.Column(db.Text)
    venue = db.Column(db.String(255), nullable=False)   # name and street address
    # The major city closest to the venue, e.g. 'Townsville, QLD' (EventForm.CITIES),
    # so events can be found by city even when they're in a suburb or nearby town.
    # Empty for events made before the field existed (add_missing_columns adds it).
    city = db.Column(db.String(50))
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.Time, nullable=False)
    image_filename = db.Column(db.String(255))

    # optional filter/category fields - validated in the WTForms layer
    dietary_preference = db.Column(db.String(50))   # Vegan, Halal, Gluten-Free, ...
    seasonal_cultural = db.Column(db.String(50))    # Summer BBQ, Cultural, ...
    proficiency = db.Column(db.String(50))          # Beginner, Family Friendly, ...

    # 'Open' | 'Cancelled' - the only status set by hand (an owner cancelling).
    # The status SHOWN - Open, Inactive, Sold Out or Cancelled - is worked out
    # by effective_status below (#25), so it can't go out of date. Databases
    # made before #25 may still hold 'Sold Out' or 'Inactive' here; only
    # 'Cancelled' is read.
    status = db.Column(db.String(20), nullable=False, default='Open')

    # How many likes the event has - the homepage and category pages sort by
    # this, and Popular needs at least POPULAR_MIN_LIKES (views.py). The heart
    # on the event cards adds or takes away 1 (main.toggle_like); the sample
    # events start with seeded totals, so this isn't a count of Like rows.
    # server_default lets add_missing_columns() add it to older databases.
    likes = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))

    # 'None' | 'Generic' | 'Enhanced'
    # Acknowledgement of Country chosen by the event creator (#6).
    # acknowledgement_city is the capital city picked for an Enhanced
    # acknowledgement ('Sydney', 'Brisbane', ...) and empty for the other types.
    acknowledgement_type = db.Column(db.String(20), default='None')
    acknowledgement_city = db.Column(db.String(50))
    # The rest of the Enhanced builder's answers (empty for the other types).
    # The statement shown is put together from these when the page is shown
    # (views.compose_acknowledgement). custodians is only needed when the city
    # is 'Other'; for a capital, the capital's custodians are used.
    acknowledgement_custodians = db.Column(db.String(255))
    acknowledgement_connection = db.Column(db.Text)
    acknowledgement_commitment = db.Column(db.String(255))
    acknowledgement_elders = db.Column(db.Boolean, nullable=False, default=True,
                                       server_default=db.text('1'))
    # Not written by the Create Event form (unused).
    acknowledgement_text = db.Column(db.Text)

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # deleting an Event removes its ticket types with it. Ordered by id so the
    # tiers always list in the order they were added.
    ticket_types = db.relationship('TicketType', backref='event', lazy=True,
                                   cascade='all, delete-orphan',
                                   order_by='TicketType.id')
    bookings = db.relationship('Booking', backref='event', lazy=True)
    comments = db.relationship('Comment', backref='event', lazy=True)

    def __repr__(self):
        return "<Event {}>".format(self.title)

    # ---- Read-only helpers for the templates ----

    @property
    def image_path(self):
        """The event image's path under static/, for url_for('static', ...).
        Uploaded images live in uploads/events/; the seeded sample events use
        the A1 photos in img/. Falls back to the placeholder if neither exists."""
        if self.image_filename:
            for folder in ('uploads/events', 'img'):
                if os.path.exists(os.path.join(current_app.static_folder, folder,
                                               self.image_filename)):
                    return folder + '/' + self.image_filename
        return 'img/image-placeholder.jpg'

    @property
    def from_price(self):
        """The cheapest ticket price (the "From $..." figure), or None if the
        event has no ticket types yet."""
        prices = [t.price for t in self.ticket_types]
        return min(prices) if prices else None

    @property
    def tickets_sold(self):
        return sum(b.quantity for b in self.bookings)

    @property
    def effective_status(self):
        """The event's status as shown and enforced (#25), worked out when it's
        read rather than stored, so it's never out of date:
          - Cancelled: the owner cancelled it (the one status that's stored)
          - Inactive:  its date has passed
          - Sold Out:  every ticket type has no tickets left
          - Open:      otherwise - including an event with no ticket types yet
                       ("Tickets coming soon"), which isn't sold out
        The status badges show this, and main.book_tickets only sells tickets
        while it's Open. Tickets left per tier come from TicketType.tickets_left."""
        if self.status == 'Cancelled':
            return 'Cancelled'
        if self.event_date < date.today():
            return 'Inactive'
        if self.ticket_types and not any(t.tickets_left for t in self.ticket_types):
            return 'Sold Out'
        return 'Open'


# One price tier of an event (e.g. Adult, $45.00, 60 available). A Booking points
# at a specific tier, which is where its price comes from.
class TicketType(db.Model):
    __tablename__ = 'ticket_type'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)   # Adult, Child, Senior, Student
    price = db.Column(db.Numeric(8, 2), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255))

    # one TicketType -> many Bookings; gives booking.ticket_type
    bookings = db.relationship('Booking', backref='ticket_type', lazy=True)

    def __repr__(self):
        return "<TicketType {} ${}>".format(self.name, self.price)

    @property
    def tickets_sold(self):
        return sum(b.quantity for b in self.bookings)

    @property
    def tickets_left(self):
        return max(self.capacity - self.tickets_sold, 0)


# One line of an order: a user buying `quantity` tickets of one TicketType.
# An order (one purchase) can cover several ticket types of the same event:
# one Booking per type, all sharing the order's order_number, user, event and
# booked_at - see Order below. order_number is the reference shown to the user.
# event_id duplicates ticket_type.event_id to make per-event queries simple -
# keep the two consistent.
class Booking(db.Model):
    __tablename__ = 'booking'

    id = db.Column(db.Integer, primary_key=True)
    # not unique: an order's bookings share it. (Databases made before orders
    # could hold several ticket types still have it unique - re-seed them.)
    order_number = db.Column(db.String(20), nullable=False, index=True)  # 'EPI-64118'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    ticket_type_id = db.Column(db.Integer, db.ForeignKey('ticket_type.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Numeric(8, 2), nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Booking {}>".format(self.order_number)


class Order:
    """One purchase: the Booking rows that share an order number, one per ticket
    type. Not a table - it's built from those rows (see orders_from) for the
    order page and the booking history."""

    def __init__(self, bookings):
        self.lines = sorted(bookings, key=lambda b: b.id)   # in the order they were chosen
        first = self.lines[0]
        self.order_number = first.order_number
        self.user = first.user
        self.event = first.event
        self.booked_at = first.booked_at

    @property
    def total_price(self):
        return sum(b.total_price for b in self.lines)


def orders_from(bookings):
    """Group bookings into Orders by order number, keeping the order they came in
    (so bookings sorted newest first give orders newest first)."""
    grouped = {}
    for booking in bookings:
        grouped.setdefault(booking.order_number, []).append(booking)
    return [Order(lines) for lines in grouped.values()]


# A comment on an event page, displayed with the commenter's name and posted_at.
class Comment(db.Model):
    __tablename__ = 'comment'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Comment {}>".format(self.id)


# One user liking one event (the heart on the event cards). It records WHO
# liked what, so the heart shows filled for them and a second click unlikes;
# Event.likes holds the total. The unique constraint means a user can like an
# event only once. ('like' is an SQL keyword, hence the table name.)
class Like(db.Model):
    __tablename__ = 'event_like'
    __table_args__ = (db.UniqueConstraint('user_id', 'event_id'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    liked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Like user {} event {}>".format(self.user_id, self.event_id)
