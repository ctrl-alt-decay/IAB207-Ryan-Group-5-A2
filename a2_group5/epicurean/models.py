# Status-style fields are plain strings (SQLite has no enum); forms enforce the values.
import os

from . import db
from datetime import date, datetime
from flask import current_app
from flask_login import UserMixin


class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    street_address = db.Column(db.String(255), nullable=False)
    profile_image = db.Column(db.String(255))   # under static/uploads/profile/

    events = db.relationship('Event', backref='owner', lazy=True)
    bookings = db.relationship('Booking', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='user', lazy=True)

    def __repr__(self):
        return "<User {} {}>".format(self.first_name, self.last_name)


# Prices and capacity live on TicketType, not here.
class Event(db.Model):
    __tablename__ = 'event'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    venue = db.Column(db.String(255), nullable=False)
    # Nearest major city (EventForm.CITIES), so suburb events still show up by city.
    # Empty on events made before this column existed.
    city = db.Column(db.String(50))
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.Time, nullable=False)
    image_filename = db.Column(db.String(255))

    dietary_preference = db.Column(db.String(50))
    seasonal_cultural = db.Column(db.String(50))
    proficiency = db.Column(db.String(50))

    # Only 'Cancelled' is read - everything else comes from effective_status.
    # Old databases may still hold 'Sold Out'/'Inactive' here; ignore them.
    status = db.Column(db.String(20), nullable=False, default='Open')

    # Seeded with fake totals for sample events, so it's not a count of Like rows.
    likes = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))

    # 'None' | 'Generic' | 'Enhanced'. The rest are Enhanced-only and the
    # statement is built at render time (views.compose_acknowledgement).
    # custodians is only used when city is 'Other'.
    acknowledgement_type = db.Column(db.String(20), default='None')
    acknowledgement_city = db.Column(db.String(50))
    acknowledgement_custodians = db.Column(db.String(255))
    acknowledgement_connection = db.Column(db.Text)
    acknowledgement_commitment = db.Column(db.String(255))
    acknowledgement_elders = db.Column(db.Boolean, nullable=False, default=True,
                                       server_default=db.text('1'))
    # unused
    acknowledgement_text = db.Column(db.Text)

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_types = db.relationship('TicketType', backref='event', lazy=True,
                                   cascade='all, delete-orphan',
                                   order_by='TicketType.id')
    bookings = db.relationship('Booking', backref='event', lazy=True)
    comments = db.relationship('Comment', backref='event', lazy=True)

    def __repr__(self):
        return "<Event {}>".format(self.title)

    @property
    def image_path(self):
        # Uploads go in uploads/events/, seeded sample events use the A1 photos in img/.
        if self.image_filename:
            for folder in ('uploads/events', 'img'):
                if os.path.exists(os.path.join(current_app.static_folder, folder,
                                               self.image_filename)):
                    return folder + '/' + self.image_filename
        return 'img/image-placeholder.jpg'

    @property
    def from_price(self):
        prices = [t.price for t in self.ticket_types]
        return min(prices) if prices else None

    @property
    def tickets_sold(self):
        return sum(b.quantity for b in self.bookings)

    @property
    def effective_status(self):
        # Computed rather than stored so it can't go stale. An event with no
        # ticket types yet counts as Open, not Sold Out.
        if self.status == 'Cancelled':
            return 'Cancelled'
        if self.event_date < date.today():
            return 'Inactive'
        if self.ticket_types and not any(t.tickets_left for t in self.ticket_types):
            return 'Sold Out'
        return 'Open'


class TicketType(db.Model):
    __tablename__ = 'ticket_type'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Numeric(8, 2), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255))

    bookings = db.relationship('Booking', backref='ticket_type', lazy=True)

    def __repr__(self):
        return "<TicketType {} ${}>".format(self.name, self.price)

    @property
    def tickets_sold(self):
        return sum(b.quantity for b in self.bookings)

    @property
    def tickets_left(self):
        return max(self.capacity - self.tickets_sold, 0)


# One ticket type within an order. All bookings in an order share order_number,
# user, event and booked_at (see Order). event_id duplicates ticket_type.event_id
# for easier queries - keep them in sync.
class Booking(db.Model):
    __tablename__ = 'booking'

    id = db.Column(db.Integer, primary_key=True)
    # Not unique (shared across an order). Older databases still have it unique - re-seed them.
    order_number = db.Column(db.String(20), nullable=False, index=True)  # 'EPI-64118'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    ticket_type_id = db.Column(db.Integer, db.ForeignKey('ticket_type.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Numeric(8, 2), nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Booking {}>".format(self.order_number)


# Not a table - just the Booking rows grouped by order number.
class Order:

    def __init__(self, bookings):
        self.lines = sorted(bookings, key=lambda b: b.id)
        first = self.lines[0]
        self.order_number = first.order_number
        self.user = first.user
        self.event = first.event
        self.booked_at = first.booked_at

    @property
    def total_price(self):
        return sum(b.total_price for b in self.lines)


def orders_from(bookings):
    # preserves input order, so newest-first bookings give newest-first orders
    grouped = {}
    for booking in bookings:
        grouped.setdefault(booking.order_number, []).append(booking)
    return [Order(lines) for lines in grouped.values()]


class Comment(db.Model):
    __tablename__ = 'comment'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Comment {}>".format(self.id)


# Tracks who liked what; Event.likes holds the total. 'like' is an SQL keyword.
class Like(db.Model):
    __tablename__ = 'event_like'
    __table_args__ = (db.UniqueConstraint('user_id', 'event_id'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    liked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Like user {} event {}>".format(self.user_id, self.event_id)
