# Database schema: user, event, ticket_type, booking, comment.
# Status-style fields are plain strings (SQLite has no enum type); the allowed
# values are listed beside each column and should be enforced by the forms.
# Each relationship(backref=...) adds an attribute on BOTH sides - e.g.
# User.events below also creates Event.owner.
import os

from . import db
from datetime import datetime
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
    venue = db.Column(db.String(255), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.Time, nullable=False)
    image_filename = db.Column(db.String(255))

    # optional filter/category fields - validated in the WTForms layer
    dietary_preference = db.Column(db.String(50))   # Vegan, Halal, Gluten-Free, ...
    seasonal_cultural = db.Column(db.String(50))    # Summer BBQ, Cultural, ...
    proficiency = db.Column(db.String(50))          # Beginner, Family Friendly, ...

    # 'Open' | 'Inactive' | 'Sold Out' | 'Cancelled'
    # Nothing updates this automatically yet (e.g. to 'Inactive' once the date passes).
    status = db.Column(db.String(20), nullable=False, default='Open')

    # How many likes the event has - the homepage and category pages sort by
    # this, and Popular needs at least POPULAR_MIN_LIKES (views.py). Only the
    # sample events have likes so far; the heart button doesn't save yet.
    # server_default lets add_missing_columns() add it to older databases.
    likes = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))

    # 'None' | 'Generic' | 'Enhanced'
    # Acknowledgement of Country chosen by the event creator (#6).
    # acknowledgement_city is the capital city picked for an Enhanced
    # acknowledgement ('Sydney', 'Brisbane', ...) and empty for the other types.
    acknowledgement_type = db.Column(db.String(20), default='None')
    acknowledgement_city = db.Column(db.String(50))
    # Not written by the Create Event form: the statement shown is worked out
    # from acknowledgement_type and acknowledgement_city.
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


# One purchase: a user buying `quantity` tickets of one TicketType.
# order_number is the reference shown to the user. event_id duplicates
# ticket_type.event_id to make per-event queries simple - keep the two consistent.
class Booking(db.Model):
    __tablename__ = 'booking'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)  # 'EPI-64118'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    ticket_type_id = db.Column(db.Integer, db.ForeignKey('ticket_type.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Numeric(8, 2), nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return "<Booking {}>".format(self.order_number)


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
