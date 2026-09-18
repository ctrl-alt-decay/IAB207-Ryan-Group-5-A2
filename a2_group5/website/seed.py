"""Seed the database with sample data so the schema can be checked end to end.

Run from the projectfile directory (the one containing main.py):

    python -m website.seed

This DROPS and recreates every table, so only run it against the dev database.
Uses nothing beyond what is already in requirements.txt.
"""

from datetime import date, time, datetime
from decimal import Decimal

from flask_bcrypt import generate_password_hash

from . import create_app, db
from .models import User, Event, TicketType, Booking, Comment


def _hash(password):
    # flask_bcrypt returns bytes; password_hash is a String column
    return generate_password_hash(password).decode('utf-8')


# Every account created here uses the password 'Password123'.
def seed():
    # --- Users -------------------------------------------------------
    amity = User(
        first_name='Amity',
        last_name='Group5',
        email='amity@example.com',
        password_hash=_hash('Password123'),
        contact_number='0400 111 222',
        street_address='12 Ann St, Brisbane QLD 4000',
    )
    rukayya = User(
        first_name='Rukayya',
        last_name='Group5',
        email='rukayya@example.com',
        password_hash=_hash('Password123'),
        contact_number='0400 333 444',
        street_address='88 Grey St, South Brisbane QLD 4101',
    )
    ro = User(
        first_name='Ro',
        last_name='Group5',
        email='ro@example.com',
        password_hash=_hash('Password123'),
        contact_number='0400 777 888',
        street_address='1 Test St, Brisbane QLD 4000',
    )
    db.session.add_all([amity, rukayya, ro])
    db.session.flush()  # assigns user ids for the FKs below

    # --- Events ------------------------------------------------------
    bbq = Event(
        title='Summer Rooftop BBQ',
        description='A relaxed rooftop BBQ with seasonal produce and live music.',
        venue='Rooftop Terrace, 45 Edward St, Brisbane QLD 4000',
        event_date=date(2026, 12, 5),
        event_time=time(17, 30),
        image_filename='summer_bbq.jpg',
        dietary_preference='Halal',
        seasonal_cultural='Summer BBQ',
        proficiency='Family Friendly',
        status='Open',
        acknowledgement_type='Generic',
        acknowledgement_text=(
            'We acknowledge the Traditional Owners of the land on which we gather.'
        ),
        owner=amity,
    )
    pasta = Event(
        title='Handmade Pasta Workshop',
        description='Learn to make fresh pasta from scratch with a local chef.',
        venue='The Kitchen Studio, 7 Boundary St, West End QLD 4101',
        event_date=date(2026, 11, 21),
        event_time=time(10, 0),
        image_filename='pasta_workshop.jpg',
        dietary_preference='Vegan',
        seasonal_cultural='Cultural',
        proficiency='Beginner',
        status='Open',
        acknowledgement_type='None',
        owner=rukayya,
    )
    db.session.add_all([bbq, pasta])
    db.session.flush()

    # --- Ticket types ------------------------------------------------
    bbq_adult = TicketType(event=bbq, name='Adult', price=Decimal('45.00'),
                           capacity=60, description='General admission, 18+')
    bbq_child = TicketType(event=bbq, name='Child', price=Decimal('20.00'),
                           capacity=30, description='Ages 5-17')
    pasta_std = TicketType(event=pasta, name='Adult', price=Decimal('89.50'),
                           capacity=16, description='Includes all ingredients')
    pasta_conc = TicketType(event=pasta, name='Student', price=Decimal('69.50'),
                            capacity=8, description='Valid student ID required')
    db.session.add_all([bbq_adult, bbq_child, pasta_std, pasta_conc])
    db.session.flush()

    # --- Booking -----------------------------------------------------
    qty = 2
    booking = Booking(
        order_number='EPI-64118',
        user=ro,
        event=bbq,
        ticket_type=bbq_adult,
        quantity=qty,
        total_price=bbq_adult.price * qty,
        booked_at=datetime.utcnow(),
    )
    db.session.add(booking)

    # --- Comment -----------------------------------------------------
    comment = Comment(
        event=bbq,
        user=amity,
        body='Booked for me and a friend - looking forward to it!',
    )
    db.session.add(comment)

    db.session.commit()
    return booking


def report(booking):
    """Walk the relationships so a broken FK or backref shows up immediately."""
    print('--- seed summary ---')
    print('users      :', User.query.count())
    print('events     :', Event.query.count())
    print('ticket types:', TicketType.query.count())
    print('bookings   :', Booking.query.count())
    print('comments   :', Comment.query.count())
    print()
    print('booking.order_number     :', booking.order_number)
    print('booking.user.first_name  :', booking.user.first_name)
    print('booking.event.title      :', booking.event.title)
    print('booking.ticket_type.name :', booking.ticket_type.name)
    print('booking.total_price      :', booking.total_price)
    print()
    for event in Event.query.order_by(Event.event_date).all():
        print('{} ({} {})'.format(event.title, event.event_date, event.event_time))
        print('   owner    :', event.owner.first_name, event.owner.last_name)
        print('   status   :', event.status)
        print('   tickets  :', ', '.join(
            '{} ${}'.format(t.name, t.price) for t in event.ticket_types))
        print('   bookings :', len(event.bookings))
        for c in event.comments:
            print('   comment  : {} - "{}"'.format(c.user.first_name, c.body))
    print()
    print('amity.events   :', [e.title for e in User.query.filter_by(
        email='amity@example.com').first().events])
    print('ro.bookings    :', [b.order_number for b in User.query.filter_by(
        email='ro@example.com').first().bookings])


# WARNING: drop_all() wipes the REAL database in instance/ - every account,
# booking and profile-picture link is lost. Don't run it on data you need.
def main():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        booking = seed()
        report(booking)
    print('\nDone. Database seeded.')


if __name__ == '__main__':
    main()
