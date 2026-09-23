"""The 24 sample events from the A1 homepage cards, as real database rows (#15).
The homepage sorts them into its categories like any other event - by likes,
date and kids' tickets (CATEGORIES in views.py).

Run from the projectfile directory (the one containing main.py):

    python -m website.sample_events

Safe to run on a database that matters - nothing is dropped:
  - add_sample_events() adds any sample event whose title isn't there yet
  - refresh_sample_events() updates sample events added by an older version
    of this file (likes, longer description), but only where they're still
    untouched - anything changed through Edit Event is left alone
Running it twice is harmless. seed.py also calls add_sample_events() after
rebuilding its own data.

Where the data came from:
  - title, venue, time, weekday, "From" price, status and likes: the A1 cards
  - image: the card's photo in static/img/ (stored as just the filename;
    Event.image_path finds it there)
  - ticket tiers: the patterns in TIERS, modelled on the A1 Cinco De Mayo page
    (Child / Adult / Senior / Student). The card price is the main tier's price.
  - description (a brief plus a longer paragraph in DETAILS) and categories:
    written for each event (the cards had none)

Dates: the cards gave a day and month but no year, and most had passed. So:
  - Popular events: the next time that day and month comes round
  - This Weekend: the coming Friday-Sunday (on the card's weekday), so they
    really are this weekend when seeded
  - Bring Your Kids: the weekend after that
  - the one Inactive card: last weekend, so its status matches its date
"Sales End Soon" isn't one of the four statuses, so those cards became Open.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask_bcrypt import generate_password_hash

from . import db
from .models import User, Event, TicketType, Booking


# The events are shared out between the group's three test accounts (all with
# password 'Password123'). They're created here if they don't exist yet.
ORGANISERS = [
    dict(first_name='Amity', last_name='Group5', email='amity@example.com',
         contact_number='0400 111 222', street_address='12 Ann St, Brisbane QLD 4000'),
    dict(first_name='Rukayya', last_name='Group5', email='rukayya@example.com',
         contact_number='0400 333 444', street_address='88 Grey St, South Brisbane QLD 4101'),
    dict(first_name='Ro', last_name='Group5', email='ro@example.com',
         contact_number='0400 777 888', street_address='1 Test St, Brisbane QLD 4000'),
]

# Ticket tier patterns: (name, share of the card price, description, capacity).
# The share-1 tier is charged exactly the card price; others are rounded to 50c.
# FAMILY reproduces the A1 Cinco De Mayo page's four tiers exactly.
TIERS = {
    'family': [
        ('Child', '0.43', "Ages 3-12. Under 3s enter free and don't need a ticket.", 60),
        ('Adult', '1', 'General admission for guests aged 18 and over.', 150),
        ('Senior', '0.8', 'Ages 65+. ID may be requested at entry.', 40),
        ('Student', '0.714', 'Valid student ID required at entry.', 50),
    ],
    'adults': [
        ('Adult', '1', 'General admission. 18+ only - ID is checked at the door.', 120),
        ('Senior', '0.85', 'Ages 65+. ID may be requested at entry.', 30),
        ('Student', '0.8', 'Valid student ID required. 18+ only.', 40),
    ],
    'premium': [
        ('Standard', '1', 'Includes every course of the set menu.', 20),
        ('With Wine Pairing', '1.4', 'Adds a matched wine with each course. 18+ only.', 10),
    ],
    'general': [
        ('General Admission', '1', 'Entry only - food and drinks are sold at the stalls.', 600),
        ('VIP Pass', '3', 'Fast-track entry, shaded seating and two drink tokens.', 60),
    ],
    'workshop': [
        ('Participant', '1', 'All ingredients, equipment and an apron are provided.', 16),
        ('Observer', '0.5', 'Watch the class and taste the results without cooking.', 6),
    ],
    'kids': [
        ('Child', '1', 'Ages 4-12. Every child must be booked with an adult.', 30),
        ('Accompanying Adult', '0.5', 'One supervising adult per child.', 30),
        ('Family (2 adults + 2 kids)', '2.6', 'Best value for a family of four.', 10),
    ],
}

CINCO_DESCRIPTION = (
    'Wander the plaza between food stalls serving fresh ceviche, elote, and slow-cooked '
    'birria while a live mariachi trio plays through the square. Try your hand at piñata '
    'breaking or the chilli tasting challenge, then cool off at the tequila and mezcal '
    'sampling bar as the afternoon heats up. Once the sun sets, the plaza turns into an '
    'open-air dance floor with a folklórico performance followed by a DJ set. Come hungry, '
    'come ready to dance, and stay for the fireworks that close out the night.'
)

# One entry per A1 card, in the order they appeared on the homepage.
# 'group' is the A1 homepage section the card was in (it decides the date - see
# the top of this file). 'day' is (day, month) for Popular events; weekend
# events give their weekday. 'likes' is the card's like count, saved as
# Event.likes (the homepage sorts by it) and used to size the sample bookings.
# 'description' is the short brief; DETAILS below adds a longer paragraph.
EVENTS = [
    # ---- Popular ----
    dict(group='popular', title='Cinco De Mayo Fiesta', image='cinco-de-mayo_event.jpg',
         day=(2, 5), at=time(12, 0), venue='Fiesta Square, Riverside Markets',
         price='35.00', status='Sold Out', tiers='family', likes=412,
         dietary=None, seasonal='Cultural', proficiency='Family Friendly', ack='Generic',
         description=CINCO_DESCRIPTION),
    dict(group='popular', title='Oktoberfest', image='oktoberfest_event.jpg',
         day=(25, 9), at=time(18, 0), venue='The Beer Hall, Warehouse District',
         price='29.99', status='Open', tiers='adults', likes=356,
         dietary=None, seasonal='Cultural', proficiency='Foodie', ack=('Enhanced', 'Brisbane'),
         description='A Bavarian beer hall takeover with steins, pretzels, bratwurst and an '
                     'oompah band. Long shared tables, a stein-holding contest at 8pm and '
                     'plenty of sauerkraut.'),
    dict(group='popular', title='Underwater Dining Experience', image='underwater_event.jpg',
         day=(14, 11), at=time(19, 0), venue='The Reef Room, Marina Point',
         price='250.00', status='Sold Out', tiers='premium', likes=289,
         dietary='Gluten-Free', seasonal=None, proficiency='Foodie', ack=None,
         description='A seven-course seafood degustation served five metres below the '
                     'surface, with the reef drifting past the glass. The whole menu is '
                     'gluten-free.'),
    dict(group='popular', title='Vineyard Vegan Picnic', image='vegan-vinyard_event.jpg',
         day=(8, 2), at=time(12, 30), venue='Hillside Vineyard, Valley Road',
         price='75.00', status='Cancelled', tiers='adults', likes=178,
         dietary='Vegan', seasonal='Summer BBQ', proficiency=None, ack=None,
         description='A plant-based picnic hamper on the lawns between the vines, with a '
                     'cellar-door tasting of the estate whites.'),
    dict(group='popular', title='Truffle Hunting & Feast', image='truffle-hunt_event.jpg',
         day=(21, 6), at=time(9, 0), venue='Blackwood Forest Estate',
         price='120.00', status='Open', tiers='premium', likes=233,
         dietary=None, seasonal='Winter Comforts', proficiency='Foodie', ack=None,
         description='Follow the estate\'s truffle dogs through the oak grove at first light, '
                     'then sit down to a three-course lunch built around the morning\'s find.'),
    dict(group='popular', title='Midnight Ramen Society', image='midnight-ramen_event.jpg',
         day=(10, 7), at=time(23, 0), venue='Back Alley Kitchen, Chinatown',
         price='28.00', status='Open', tiers='adults', likes=501,
         dietary=None, seasonal='Winter Comforts', proficiency='Foodie', ack=None,
         description='A late-night ramen counter that only opens once a month. Three broths, '
                     'hand-pulled noodles and a whisky list for the night owls.'),
    dict(group='popular', title="Chef's Table Tasting Menu", image='chef-table_event.jpg',
         day=(30, 8), at=time(19, 30), venue='The Pass, City Centre',
         price='180.00', status='Open', tiers='premium', likes=94,
         dietary=None, seasonal=None, proficiency='Expert', ack=None,
         description='Eight courses served at the pass, with the head chef talking you '
                     'through each dish as it is plated.'),
    dict(group='popular', title='Harbourside Seafood Festival', image='harbor-seafood_event.jpg',
         day=(15, 3), at=time(11, 0), venue='Harbourside Promenade, Pier 4',
         price='15.00', status='Open', tiers='general', likes=620,
         dietary=None, seasonal='Autumn Harvest', proficiency=None, ack='Generic',
         description='Forty stalls along the promenade serving oysters, grilled prawns, '
                     'fish tacos and chowder, with live music on the pier all day.'),

    # ---- This Weekend ----
    dict(group='weekend', title='Gnocchi Culinary Workshop', image='gnocchi_workshop.jpg',
         day='Sat', at=time(10, 0), venue='Trattoria Alessandra, Little Italy',
         price='40.00', status='Cancelled', tiers='workshop', likes=87,
         dietary='Vegetarian', seasonal='Cultural', proficiency='Beginner', ack=None,
         description='Learn to make potato gnocchi from scratch and pair it with a brown '
                     'butter and sage sauce. Lunch is whatever you make.'),
    dict(group='weekend', title='Night Market Noodle Crawl', image='night-noodle_event.jpg',
         day='Fri', at=time(18, 30), venue='Lantern Night Market',
         price='60.00', status='Inactive', tiers='family', likes=145,
         dietary=None, seasonal='Cultural', proficiency='Foodie', ack=None,
         description='A guided crawl through five noodle stalls at the night market, from '
                     'hand-cut biang biang to laksa.'),
    dict(group='weekend', title='Smoked BBQ Masterclass', image='bbq-seminar_event.jpg',
         day='Sat', at=time(13, 0), venue="Pitmaster's Yard, Southside",
         price='85.00', status='Open', tiers='workshop', likes=210,
         dietary='Low Carb', seasonal='Summer BBQ', proficiency='Intermediate', ack=None,
         description='Fire management, rubs and resting: a hands-on afternoon at the smoker '
                     'finishing with a brisket and rib feast.'),
    dict(group='weekend', title='Farmers Market Brunch Tour', image='farmers-market_event.jpg',
         day='Sat', at=time(8, 0), venue='Old Town Farmers Market',
         price='25.00', status='Open', tiers='family', likes=132,
         dietary='Vegetarian', seasonal='Spring Flavours', proficiency=None, ack=None,
         description='Meet the growers, taste as you go, and finish with a brunch cooked '
                     'from the morning\'s produce.'),
    dict(group='weekend', title='Sunday Roast Pop-Up', image='sunday-roast_event.jpg',
         day='Sun', at=time(13, 0), venue='The Ivy Kitchen, Parkside',
         price='32.00', status='Open', tiers='family', likes=76,
         dietary='Halal', seasonal='Winter Comforts', proficiency=None, ack=None,
         description='A proper Sunday roast with all the trimmings, Yorkshire puddings and '
                     'sticky date pudding to finish.'),
    dict(group='weekend', title='Craft Beer & Cheese Pairing', image='craft-beer-and-cheese_event.jpg',
         day='Sat', at=time(16, 0), venue='Hopyard Taproom, Dock Street',
         price='45.00', status='Open', tiers='adults', likes=168,
         dietary='Vegetarian', seasonal=None, proficiency='Foodie', ack=None,
         description='Five local craft beers matched with five farmhouse cheeses, led by '
                     'the brewer and the cheesemonger.'),
    dict(group='weekend', title='Dongzhi Festival Dumpling Class', image='dumpling-dongzhi-festival_event.jpg',
         day='Sat', at=time(11, 0), venue='Golden Wok Studio',
         price='38.00', status='Open', tiers='workshop', likes=99,
         dietary=None, seasonal='Cultural', proficiency='Beginner', ack=None,
         description='Celebrate the winter solstice festival by folding and steaming '
                     'dumplings and tangyuan with a family recipe.'),
    dict(group='weekend', title='Riverside Food Truck Rally', image='riverside-foodtruck_event.jpg',
         day='Sun', at=time(12, 0), venue='Riverside Green, East Bank',
         price='10.00', status='Open', tiers='general', likes=304,
         dietary=None, seasonal='Spring Flavours', proficiency=None, ack=('Enhanced', 'Brisbane'),
         description='Twenty-five food trucks, lawn games and a DJ on the riverbank. '
                     'Bring a picnic rug.'),

    # ---- Bring Your Kids ----
    dict(group='kids', title='Sunrise Sourdough Bake', image='sourdough-class_event.jpg',
         day='Sat', at=time(7, 0), venue='The Rustic Loaf Bakery',
         price='45.00', status='Open', tiers='kids', likes=63,
         dietary=None, seasonal=None, proficiency='Family Friendly', ack=None,
         description='Shape, score and bake your own sourdough loaf with the bakers before '
                     'the shop opens. Kids get their own mini loaf.'),
    dict(group='kids', title='Petting Zoo Picnic Day', image='petting-zoo_event.jpg',
         day='Sun', at=time(10, 0), venue='Green Meadows Farm',
         price='15.00', status='Open', tiers='kids', likes=221,
         dietary=None, seasonal='Spring Flavours', proficiency='Family Friendly', ack=None,
         description='Feed the lambs and goats, then settle in for a farm picnic lunch '
                     'under the trees.'),
    dict(group='kids', title="Kids' Pizza Making Party", image='kids-pizza_event.jpg',
         day='Sat', at=time(14, 0), venue='Little Chefs Kitchen Studio',
         price='30.00', status='Open', tiers='kids', likes=189,
         dietary='Vegetarian', seasonal=None, proficiency='Family Friendly', ack=None,
         description='Kids stretch their own dough, choose their toppings and watch their '
                     'pizza come out of the wood-fired oven.'),
    dict(group='kids', title="Storytime & S'mores Campfire", image='campsite-smore_event.jpg',
         day='Sat', at=time(18, 0), venue='Lakeside Campgrounds',
         price='20.00', status='Open', tiers='kids', likes=154,
         dietary=None, seasonal='Winter Comforts', proficiency='Family Friendly', ack=None,
         description='Campfire stories by the lake with toasted marshmallows, s\'mores and '
                     'hot chocolate.'),
    dict(group='kids', title='Cupcake Decorating Workshop', image='cupcake-decor-workshop_event.jpg',
         day='Sun', at=time(11, 0), venue='Sweet Tooth Studio',
         price='25.00', status='Open', tiers='kids', likes=267,
         dietary=None, seasonal=None, proficiency='Family Friendly', ack=None,
         description='Piping bags, sprinkles and fondant: decorate a box of six cupcakes '
                     'to take home.'),
    dict(group='kids', title='Kids Cooking Challenge', image='kids-cooking_event.jpg',
         day='Sat', at=time(10, 0), venue='Community Kitchen Hall',
         price='35.00', status='Open', tiers='kids', likes=312,
         dietary=None, seasonal=None, proficiency='Family Friendly', ack=None,
         description='Teams of young cooks get a mystery basket and forty minutes. '
                     'Every finalist takes home an apron.'),
    dict(group='kids', title='Ice Cream Sundae Bar', image='icecream-bar_event.jpg',
         day='Sun', at=time(13, 0), venue='Scoops & Sprinkles Parlour',
         price='18.00', status='Open', tiers='kids', likes=198,
         dietary='Gluten-Free', seasonal='Summer BBQ', proficiency='Family Friendly', ack=None,
         description='Build-your-own sundaes with twelve flavours, hot fudge and a '
                     'mountain of toppings.'),
    dict(group='kids', title='Carnival Fun Fair Food Trail', image='carnival-funfaire_event.jpg',
         day='Sat', at=time(12, 0), venue='Riverside Green, East Bank',
         price='12.00', status='Open', tiers='kids', likes=276,
         dietary=None, seasonal='Holidays', proficiency='Family Friendly', ack=None,
         description='Fairy floss, dagwood dogs and toffee apples between the rides, with a '
                     'stamp card for every stall you visit.'),
]

# The longer paragraph that follows each event's brief in its description.
DETAILS = {
    'Cinco De Mayo Fiesta':
        'Food and drink stalls take card and cash. The plaza is step-free with shaded seating '
        'near the stage, and a quiet zone sits behind the main tent for anyone who needs a '
        'break from the music. Tickets cover entry and the evening fireworks; food, drinks '
        'and the piñata workshop are paid for on the day.',
    'Oktoberfest':
        'Every ticket includes a souvenir stein and your first pour, with a rotating tap list of '
        'German lagers, wheat beers and a non-alcoholic option. Traditional dress is encouraged '
        'but not required. This is an 18+ event and ID is checked at the door.',
    'Underwater Dining Experience':
        'Seating is at a single long table for twenty-four, with a window table for eight '
        'right against the glass. The menu changes with the day\'s catch and is fully '
        'gluten-free; let us know about other allergies when you book. Smart casual dress.',
    'Vineyard Vegan Picnic':
        'Each hamper feeds one person and includes seasonal salads, house-made dips, flatbread, '
        'a cheese-free antipasto board and a dessert jar. Rugs and umbrellas are provided, or '
        'bring your own. The cellar-door tasting is 18+; sparkling juice is available.',
    'Truffle Hunting & Feast':
        'The hunt covers about two kilometres of uneven forest track, so wear sturdy shoes and '
        'bring a warm layer - mornings are cold under the oaks. Lunch is served in the estate\'s '
        'barn afterwards, and the wine pairing tier adds three matched wines.',
    'Midnight Ramen Society':
        'Choose from tonkotsu, shoyu or a slow-simmered mushroom broth, each with house noodles '
        'and toppings. The bottomless tier includes refills until 1am. Seating is at the counter '
        'and a handful of stools, so expect to share space with fellow night owls.',
    "Chef's Table Tasting Menu":
        'Twelve guests sit at the pass and watch every plate come together, with a short talk '
        'from the kitchen before each course. The wine pairing tier adds a glass with each of '
        'the eight courses. Please tell us about dietary needs at least 48 hours ahead.',
    'Harbourside Seafood Festival':
        'General admission covers entry; food and drinks are sold by each stall. The VIP pass '
        'adds fast-track entry, shaded seating on the pier and two drink tokens. The promenade '
        'is flat and pram friendly, and the festival runs until 6pm.',
    'Gnocchi Culinary Workshop':
        'You will make potato and ricotta gnocchi by hand, then cook them with brown butter and '
        'sage and a simple tomato sauce. All ingredients, equipment and aprons are provided, '
        'and observers can watch and taste without cooking.',
    'Night Market Noodle Crawl':
        'The crawl is led by a guide who knows the stallholders, with tasting portions at each '
        'of the five stops and a sweet finish at the end. Expect about ninety minutes on your '
        'feet. Vegetarian options are available at every stop.',
    'Smoked BBQ Masterclass':
        'The pitmaster walks you through choosing wood, managing the fire and reading the '
        'smoke, then you trim and rub your own cut. The class finishes around a shared table '
        'with brisket, ribs and sides. Closed-toe shoes are a must around the smokers.',
    'Farmers Market Brunch Tour':
        'The tour starts at the market gate and visits six growers before settling in for '
        'brunch at the market kitchen. Brunch is vegetarian and made from what you just tasted. '
        'Bring a bag if you would like to take produce home.',
    'Sunday Roast Pop-Up':
        'Choose roast lamb, chicken or a vegetable wellington, all served with roast potatoes, '
        'seasonal greens and gravy. All meat is halal. Dessert is sticky date pudding with '
        'butterscotch sauce, and kids\' portions are available.',
    'Craft Beer & Cheese Pairing':
        'Each pairing comes with tasting notes and the story of how the beer and cheese were '
        'made. Non-alcoholic pairings can be arranged on request. This is an 18+ event, and '
        'the taproom kitchen is open afterwards for anyone staying on.',
    'Dongzhi Festival Dumpling Class':
        'Learn two folds for dumplings and how to roll sweet tangyuan, the rice balls eaten at '
        'the winter solstice. You will eat what you make, with plenty to take home. Beginners '
        'are very welcome - the recipe card is yours to keep.',
    'Riverside Food Truck Rally':
        'General admission covers entry, with food and drinks bought from each truck. The VIP '
        'lounge adds shaded seating and two drink tokens. Dogs on leads are welcome, and there '
        'is a free water station by the playground.',
    'Sunrise Sourdough Bake':
        'Adults and kids share a workstation and bake side by side, then take home a full loaf '
        'and a mini loaf each, plus a pot of starter to keep going. The class runs for about '
        'two and a half hours. Suitable for ages 6 and up.',
    'Petting Zoo Picnic Day':
        'Entry includes feeding time with the lambs and goats, a hay-bale picnic spot and a '
        'farm-style lunch box for each child. Enclosed shoes are recommended, and there are '
        'hand-washing stations throughout the farm.',
    "Kids' Pizza Making Party":
        'Each child stretches their own dough and chooses from a vegetarian topping bar, then '
        'watches their pizza cook in the wood-fired oven. Aprons are provided and all the '
        'mess stays at the studio. Suitable for ages 4 to 12.',
    "Storytime & S'mores Campfire":
        'A local storyteller leads an hour of campfire stories as the sun goes down, with '
        'marshmallows, s\'mores and hot chocolate included. Bring a picnic rug and a warm '
        'jacket. Every child must be accompanied by an adult.',
    'Cupcake Decorating Workshop':
        'Kids decorate a box of six cupcakes with piping bags, fondant shapes and sprinkles, '
        'and learn a few simple piping techniques along the way. Everything is provided, '
        'including a take-home box. Suitable for ages 4 and up.',
    'Kids Cooking Challenge':
        'Young cooks work in small teams with a mystery basket, guided by our chefs, before a '
        'friendly judging round. Every participant takes home an apron and a recipe card. '
        'Suitable for ages 7 to 12; adults watch from the gallery.',
    'Ice Cream Sundae Bar':
        'Build your own sundae from twelve flavours, including dairy-free options, with hot '
        'fudge, fresh fruit and a mountain of toppings. Everything on the bar is gluten-free. '
        'Sessions run for an hour, so there is plenty of time to go back for more.',
    'Carnival Fun Fair Food Trail':
        'Collect a stamp at every food stall on the trail to earn a prize at the finish. Ride '
        'tickets are sold separately at the gate. The grounds are pram friendly, and there is a '
        'quiet tent with water and shade near the entrance.',
}


def _full_description(spec):
    """The brief plus its longer paragraph (the event page keeps line breaks)."""
    return spec['description'] + '\n\n' + DETAILS[spec['title']]


WEEKDAY_OFFSET = {'Fri': 0, 'Sat': 1, 'Sun': 2}


def _event_date(spec, today):
    """Work out the event date from the card, as described at the top of this file."""
    friday = today + timedelta(days=(4 - today.weekday()) % 7)  # the coming Friday
    if spec['group'] == 'popular':
        day, month = spec['day']
        for year in (today.year, today.year + 1):
            candidate = date(year, month, day)
            if candidate > today:
                return candidate
    offset = WEEKDAY_OFFSET[spec['day']]
    if spec['status'] == 'Inactive':
        return friday - timedelta(days=7) + timedelta(days=offset)  # last weekend
    if spec['group'] == 'weekend':
        return friday + timedelta(days=offset)
    return friday + timedelta(days=7 + offset)  # kids: the weekend after


def _ticket_types(spec):
    card_price = Decimal(spec['price'])
    tickets = []
    for name, share, description, capacity in TIERS[spec['tiers']]:
        if share == '1':
            price = card_price
        else:
            # round to the nearest 50c
            price = (card_price * Decimal(share) * 2).quantize(Decimal('1'), ROUND_HALF_UP) / 2
        tickets.append(TicketType(name=name, price=price.quantize(Decimal('0.01')),
                                  capacity=capacity, description=description))
    return tickets


def _organisers():
    """The three test accounts, creating any that don't exist yet."""
    users = []
    for details in ORGANISERS:
        user = db.session.scalar(db.select(User).where(User.email == details['email']))
        if user is None:
            user = User(password_hash=generate_password_hash('Password123').decode('utf-8'),
                        **details)
            db.session.add(user)
        users.append(user)
    db.session.flush()  # gives new users their ids
    return users


def add_sample_events():
    """Add any of the sample events that aren't in the database yet (matched by
    title), plus a few bookings for the Popular ones. Returns how many events
    were added. Commits."""
    from .views import new_order_number  # here, not at the top: views imports forms etc.

    users = _organisers()
    now = datetime.utcnow()
    today = date.today()
    added = []
    for index, spec in enumerate(EVENTS):
        exists = db.session.scalar(db.select(Event.id).where(Event.title == spec['title']))
        if exists:
            continue
        ack = spec['ack']
        ack_type, ack_city = (ack if isinstance(ack, tuple) else (ack or 'None', None))
        event = Event(
            title=spec['title'],
            description=_full_description(spec),
            venue=spec['venue'],
            likes=spec['likes'],
            event_date=_event_date(spec, today),
            event_time=spec['at'],
            image_filename=spec['image'],
            dietary_preference=spec['dietary'],
            seasonal_cultural=spec['seasonal'],
            proficiency=spec['proficiency'],
            status=spec['status'],
            acknowledgement_type=ack_type,
            acknowledgement_city=ack_city,
            owner=users[index % len(users)],
            # a minute apart, in card order, so Recently Added lists them predictably
            created_at=now - timedelta(minutes=len(EVENTS) - index),
            ticket_types=_ticket_types(spec),
        )
        db.session.add(event)
        added.append((spec, event))
    db.session.flush()

    # Sample bookings on the Popular events, so they have tickets sold like a
    # popular event would: roughly one ticket per 60 likes, in bookings of up
    # to 4, made by the test accounts that don't own the event
    for spec, event in added:
        if spec['group'] != 'popular' or event.status == 'Cancelled':
            continue
        # the main tier - the one charged the card price
        ticket = next(t for t in event.ticket_types if t.price == Decimal(spec['price']))
        remaining = spec['likes'] // 60
        buyers = [u for u in users if u is not event.owner]
        turn = 0
        while remaining > 0:
            quantity = min(4, remaining)
            db.session.add(Booking(
                order_number=new_order_number(), user=buyers[turn % len(buyers)],
                event=event, ticket_type=ticket, quantity=quantity,
                total_price=ticket.price * quantity))
            db.session.flush()  # so the next order number sees this one
            remaining -= quantity
            turn += 1

    db.session.commit()
    return len(added)


def refresh_sample_events():
    """Bring sample events added by an older version of this file up to date:
    set their likes if they have none, and extend a description that is still
    exactly the old short brief. Anything an owner has changed through Edit
    Event is left alone. Returns (likes set, descriptions extended). Commits."""
    likes_set = descriptions_extended = 0
    for spec in EVENTS:
        event = db.session.scalar(db.select(Event).where(Event.title == spec['title']))
        if event is None:
            continue
        if not event.likes:
            event.likes = spec['likes']
            likes_set += 1
        if event.description == spec['description']:
            event.description = _full_description(spec)
            descriptions_extended += 1
    db.session.commit()
    return likes_set, descriptions_extended


def main():
    from . import create_app
    app = create_app()
    with app.app_context():
        print('Database:', db.engine.url)
        count = add_sample_events()
        likes_set, extended = refresh_sample_events()
        print('Added {} sample events ({} were already there). Events in the database: {}'
              .format(count, len(EVENTS) - count,
                      db.session.scalar(db.select(db.func.count(Event.id)))))
        print('Updated existing sample events: likes set on {}, descriptions extended on {}'
              .format(likes_set, extended))


if __name__ == '__main__':
    main()
