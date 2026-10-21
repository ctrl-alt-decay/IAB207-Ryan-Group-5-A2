"""Usage (from the folder with main.py): python -m epicurean.seed

DROPS every table. To add the sample events without wiping anything, use
python -m epicurean.sample_events instead.
"""

from datetime import date, time, datetime
from decimal import Decimal

from . import create_app, db, add_missing_embeddings
from .models import Event, TicketType, Booking, Comment
from .sample_events import add_sample_events, get_organisers

from . import encoder
import json


def seed():
    amity, rukayya, ro = get_organisers()

    embedding = encoder.encode('A relaxed rooftop BBQ with seasonal produce and live music')
    embedding_text = json.dumps(embedding.tolist())
    bbq = Event(
        title='Summer Rooftop BBQ',
        description='A relaxed rooftop BBQ with seasonal produce and live music.',
        description_embedding = embedding_text, 
        venue='Rooftop Terrace, 45 Edward St, Brisbane QLD 4000',
        city='Brisbane, QLD',
        event_date=date(2026, 12, 5),
        event_time=time(17, 30),
        image_filename='bbq-seminar_event.jpg',
        dietary_preference='Halal',
        seasonal_cultural='Summer BBQ',
        proficiency='Family Friendly',
        status='Open',
        acknowledgement_type='Generic',
        owner=amity,
    )
    embedding = encoder.encode('Learn to make fresh pasta from scratch with a local chef.')
    embedding_text = json.dumps(embedding.tolist())
    pasta = Event(
        title='Handmade Pasta Workshop',
        description='Learn to make fresh pasta from scratch with a local chef.',
        description_embedding = embedding_text,
        venue='The Kitchen Studio, 7 Gouger Street, Adelaide SA 5000',
        city='Adelaide, SA',
        event_date=date(2026, 11, 21),
        event_time=time(10, 0),
        image_filename='gnocchi_workshop.jpg',
        dietary_preference='Vegan',
        seasonal_cultural='Cultural',
        proficiency='Beginner',
        status='Open',
        acknowledgement_type='None',
        owner=rukayya,
    )
    bbq_adult = TicketType(event=bbq, name='Adult', price=Decimal('45.00'),
                           capacity=60, description='General admission, 18+')
    db.session.add_all([
        bbq, pasta, bbq_adult,
        TicketType(event=bbq, name='Child', price=Decimal('20.00'),
                   capacity=30, description='Ages 5-17'),
        TicketType(event=pasta, name='Adult', price=Decimal('89.50'),
                   capacity=16, description='Includes all ingredients'),
        TicketType(event=pasta, name='Student', price=Decimal('69.50'),
                   capacity=8, description='Valid student ID required'),
        Booking(order_number='EPI-64118', user=ro, event=bbq, ticket_type=bbq_adult,
                quantity=2, total_price=bbq_adult.price * 2, booked_at=datetime.utcnow()),
        Comment(event=bbq, user=amity,
                body='Booked for me and a friend - looking forward to it!'),
    ])
    db.session.commit()


# WARNING: wipes the real database in instance/.
def main():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed()
        print('Sample events added:', add_sample_events())
        add_missing_embeddings()
    print('Done. Database seeded.')


if __name__ == '__main__':
    main()
