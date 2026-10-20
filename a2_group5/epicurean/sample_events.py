"""The 24 A1 homepage cards as real events.

    python -m epicurean.sample_events

Doesn't drop anything - adds missing events by title and refreshes untouched
ones from older versions of this file. Safe to rerun.

The cards had no year, so dates are generated from EARLIEST_MONTH (or today if
later). This Weekend will be empty until that weekend comes round. Only
Cancelled is stored; Sold Out comes from booking every ticket and Inactive from
dating it last weekend. "Sales End Soon" isn't a real status, so those are Open.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask_bcrypt import generate_password_hash

from . import db
from .models import User, Event, TicketType, Booking


# all use 'Password123'
ORGANISERS = [
    dict(first_name='Amity', last_name='Group5', email='amity@example.com',
         contact_number='0400 111 222', street_address='12 Ann St, Brisbane QLD 4000'),
    dict(first_name='Rukayya', last_name='Group5', email='rukayya@example.com',
         contact_number='0400 333 444', street_address='88 Grey St, South Brisbane QLD 4101'),
    dict(first_name='Ro', last_name='Group5', email='ro@example.com',
         contact_number='0400 777 888', street_address='1 Test St, Brisbane QLD 4000'),
]

# (name, share of card price, description, capacity). Non-1 shares round to 50c.
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

# In A1 card order. 'day' is (day, month) for popular, a weekday name otherwise.
# 'likes' also sizes the sample bookings.
EVENTS = [
    dict(group='popular', title='Cinco De Mayo Fiesta', image='cinco-de-mayo_event.jpg',
         day=(2, 5), at=time(12, 0),
         venue='Fiesta Square, 2 Riverside Markets Way, Parramatta NSW 2150', city='Sydney, NSW',
         price='35.00', status='Sold Out', tiers='family', likes=412,
         dietary=None, seasonal='Cultural', proficiency='Family Friendly', ack='Generic',
         description=CINCO_DESCRIPTION),
    dict(group='popular', title='Oktoberfest', image='oktoberfest_event.jpg',
         day=(25, 9), at=time(18, 0),
         venue='The Beer Hall, 14 Warehouse Lane, Fortitude Valley QLD 4006', city='Brisbane, QLD',
         price='29.99', status='Open', tiers='adults', likes=356,
         dietary=None, seasonal='Cultural', proficiency='Foodie', ack=('Enhanced', 'Brisbane'),
         description='Raise your stein: the Warehouse District is going full Bavarian for one night '
                     'only. Long shared tables fill the beer hall while an oompah band works the '
                     'room and servers weave through with platters of pork knuckle, bratwurst, giant '
                     'soft pretzels and bowls of sauerkraut with hot mustard. At 8pm the '
                     'stein-holding contest crowns the steadiest arm in the hall, and once the band '
                     'strikes up the drinking songs, expect the whole room on its feet for a toast.'),
    dict(group='popular', title='Underwater Dining Experience', image='underwater_event.jpg',
         day=(14, 11), at=time(19, 0),
         venue='The Reef Room, 1 Marina Point, Cairns City QLD 4870', city='Cairns, QLD',
         price='250.00', status='Sold Out', tiers='premium', likes=289,
         capacity={'Standard': 22, 'With Wine Pairing': 10},  # must match the seat count in DETAILS
         dietary='Gluten-Free', seasonal=None, proficiency='Foodie', ack=None,
         description='Dinner five metres below the surface, with the reef as your only view. Seven '
                     'courses of seafood arrive one after another while schools of fish drift past '
                     'the glass: kingfish crudo with finger lime, seared scallops in brown butter, '
                     'and a whole baked coral trout carved at the table. The dining room lights dim '
                     'between courses so the reef takes centre stage, and the night ends with a '
                     'coconut and passionfruit dessert as the underwater floodlights switch on '
                     'outside.'),
    dict(group='popular', title='Vineyard Vegan Picnic', image='vegan-vinyard_event.jpg',
         day=(8, 2), at=time(12, 30),
         venue='Hillside Vineyard, 88 Valley Road, Tanunda SA 5352', city='Adelaide, SA',
         price='75.00', status='Cancelled', tiers='adults', likes=178,
         dietary='Vegan', seasonal='Summer BBQ', proficiency=None, ack=None,
         description='Long summer lunches don\'t get much greener than this. Spread out on the lawns '
                     'between the vine rows with a fully plant-based hamper, then wander up to the '
                     'cellar door for a guided tasting of the estate\'s crisp whites and a chilled '
                     'rosé. Claim a spot under the shade umbrellas while a solo guitarist plays on '
                     'the terrace, and before you leave, join the winemaker for a short walk through '
                     'the rows to see the season\'s grapes ripening on the vine.'),
    dict(group='popular', title='Truffle Hunting & Feast', image='truffle-hunt_event.jpg',
         day=(21, 6), at=time(9, 0),
         venue='Blackwood Forest Estate, 210 Blackwood Road, Manjimup WA 6258', city='Bunbury, WA',
         price='120.00', status='Open', tiers='premium', likes=233,
         dietary=None, seasonal='Winter Comforts', proficiency='Foodie', ack=None,
         description='Swap the supermarket for the forest floor and hunt down winter\'s most prized '
                     'ingredient. Head into the oak grove at first light behind the estate\'s trained '
                     'truffle dogs, and watch them sniff out black truffles while the farmer shows '
                     'you how to lift one from the soil without bruising it. Back at the barn, the '
                     'morning\'s find is shaved generously over lunch beside a crackling fire: '
                     'truffled mushroom soup, hand-cut tagliatelle, and a truffle honey panna cotta '
                     'to finish.'),
    dict(group='popular', title='Midnight Ramen Society', image='midnight-ramen_event.jpg',
         day=(10, 7), at=time(23, 0),
         venue='Back Alley Kitchen, 7 Heffernan Lane, Melbourne VIC 3000', city='Melbourne, VIC',
         price='28.00', status='Open', tiers='adults', likes=501,
         dietary=None, seasonal='Winter Comforts', proficiency='Foodie', ack=None,
         description='When the city goes quiet, the best bowl in Chinatown starts steaming. Once a '
                     'month this back-alley kitchen pulls up its shutter at 11pm and serves ramen '
                     'until the pots run dry. Watch the cooks stretch noodles to order behind the '
                     'counter, load your bowl with a soft marinated egg or extra chashu, and work '
                     'down a whisky and sake list picked to stand up to a rich, porky broth. The '
                     'lights stay low, the playlist stays lo-fi, and nobody is in a hurry to leave.'),
    dict(group='popular', title="Chef's Table Tasting Menu", image='chef-table_event.jpg',
         day=(30, 8), at=time(19, 30),
         venue='The Pass, 30 Lonsdale Street, Braddon ACT 2612', city='Canberra, ACT',
         price='180.00', status='Open', tiers='premium', likes=94,
         capacity={'Standard': 8, 'With Wine Pairing': 4},
         dietary=None, seasonal=None, proficiency='Expert', ack=None,
         description='The best seat in the restaurant isn\'t in the dining room: it\'s at the pass. '
                     'Built for diners who want to know how a dish is made, not just how it tastes, '
                     'this is eight courses plated right in front of you, from a single bite of '
                     'cured kingfish to dry-aged duck finished over charcoal. Expect a dish or two '
                     'still in development, the chance to quiz the brigade about technique and '
                     'sourcing, and a front-row view of a professional kitchen running service at '
                     'full pace.'),
    dict(group='popular', title='Harbourside Seafood Festival', image='harbor-seafood_event.jpg',
         day=(15, 3), at=time(11, 0),
         venue='Harbourside Promenade, Pier 4, Hobart TAS 7000', city='Hobart, TAS',
         price='15.00', status='Open', tiers='general', likes=620,
         dietary=None, seasonal='Autumn Harvest', proficiency=None, ack='Generic',
         description='Salt air, sizzling grills and the best of the autumn catch, all along the '
                     'water. Forty stalls line the promenade shucking oysters to order and serving '
                     'garlic prawns off the grill, fish tacos, salt-and-pepper squid and steaming '
                     'cups of chowder. Local bands play on the pier through the afternoon, the '
                     'fishmongers run filleting demos on the hour, and at the dockside market you '
                     'can buy fresh fish to take home straight from the trawlers moored alongside.'),

    dict(group='weekend', title='Gnocchi Culinary Workshop', image='gnocchi_workshop.jpg',
         day='Sat', at=time(10, 0),
         venue='Trattoria Alessandra, 45 Norton Street, Leichhardt NSW 2040', city='Sydney, NSW',
         price='40.00', status='Cancelled', tiers='workshop', likes=87,
         dietary='Vegetarian', seasonal='Cultural', proficiency='Beginner', ack=None,
         description='Pillowy, handmade gnocchi is easier than you think, and Trattoria Alessandra '
                     'is opening its kitchen to prove it. In this relaxed, beginner-friendly class, '
                     'the family behind Little Italy\'s favourite trattoria share the tricks handed '
                     'down through three generations: picking the right potato, using far less flour '
                     'than you\'d expect, and rolling each piece off a fork for those sauce-catching '
                     'ridges. The class ends around the long trattoria table, sharing the meal with '
                     'a glass of Italian red or house-made lemonade.'),
    dict(group='weekend', title='Night Market Noodle Crawl', image='night-noodle_event.jpg',
         day='Fri', at=time(18, 30),
         venue='Lantern Night Market, 1 Smith Street, Darwin City NT 0800', city='Darwin, NT',
         price='60.00', status='Inactive', tiers='family', likes=145,
         dietary=None, seasonal='Cultural', proficiency='Foodie', ack=None,
         description='Follow the lanterns and the sound of sizzling woks through five of the '
                     'market\'s best noodle stalls. Your guide leads the way from hand-slapped biang '
                     'biang noodles glossed in chilli oil to a fragrant bowl of Penang laksa, with '
                     'stops for smoky wok-tossed char kway teow and cold sesame noodles along the '
                     'way. Between stalls, hear the stories of the families behind each recipe, and '
                     'wind down under the lanterns with a bowl of mango sago.'),
    dict(group='weekend', title='Smoked BBQ Masterclass', image='bbq-seminar_event.jpg',
         day='Sat', at=time(13, 0),
         venue="Pitmaster's Yard, 16 Southside Road, Toowoomba City QLD 4350", city='Toowoomba, QLD',
         price='85.00', status='Open', tiers='workshop', likes=210,
         dietary='Low Carb', seasonal='Summer BBQ', proficiency='Intermediate', ack=None,
         description='Low and slow is a craft, and this afternoon at the smoker will sharpen yours. '
                     'Pitched at cooks who already have a few barbecues under their belt, the class '
                     'digs into what separates good from great: building a clean-burning fire, '
                     'holding a steady 110°C for hours, reading the bark, and knowing when to wrap. '
                     'The feast that follows keeps it low carb, with brisket, pork ribs and smoked '
                     'chicken wings served alongside charred greens and a sharp slaw instead of '
                     'buns.'),
    dict(group='weekend', title='Farmers Market Brunch Tour', image='farmers-market_event.jpg',
         day='Sat', at=time(8, 0),
         venue='Old Town Farmers Market, 30 Charles Street, Launceston TAS 7250', city='Launceston, TAS',
         price='25.00', status='Open', tiers='family', likes=132,
         dietary='Vegetarian', seasonal='Spring Flavours', proficiency=None, ack=None,
         description='Beat the crowds and taste spring straight from the people who grow it. Arrive '
                     'as the stalls are setting up and follow your guide past crates of asparagus, '
                     'broad beans, strawberries and just-picked herbs, sampling as you go and '
                     'chatting with the farmers behind each table. Brunch is a spread of spring '
                     'flavours, from ricotta hotcakes with fresh berries to green shakshuka and '
                     'cold-pressed juice, with a local roaster pulling coffees at the finish line.'),
    dict(group='weekend', title='Sunday Roast Pop-Up', image='sunday-roast_event.jpg',
         day='Sun', at=time(13, 0),
         venue='The Ivy Kitchen, 5 Parkside Lane, Ballarat Central VIC 3350', city='Ballarat, VIC',
         price='32.00', status='Open', tiers='family', likes=76,
         dietary='Halal', seasonal='Winter Comforts', proficiency=None, ack=None,
         description='Nothing beats a proper Sunday roast when the weather turns cold. The Ivy '
                     'Kitchen fires up its ovens for one afternoon of classic winter comfort, with '
                     'long communal tables, a fire going in the corner and roasts carved to order at '
                     'the carving station. Yorkshire puddings come out puffed and golden by the '
                     'tray, the gravy is served by the jug, and there\'s always a second helping of '
                     'crispy potatoes for anyone who asks.'),
    dict(group='weekend', title='Craft Beer & Cheese Pairing', image='craft-beer-and-cheese_event.jpg',
         day='Sat', at=time(16, 0),
         venue='Hopyard Taproom, 3 Dock Street, Newcastle NSW 2300', city='Newcastle, NSW',
         price='45.00', status='Open', tiers='adults', likes=168,
         dietary='Vegetarian', seasonal=None, proficiency='Foodie', ack=None,
         description='Two crafts, five pairings, one very good Saturday afternoon. Settle into the '
                     'Hopyard taproom as the head brewer pours a flight running from a crisp pilsner '
                     'to a rich imperial stout, while a local cheesemonger matches each with a '
                     'farmhouse cheese, from fresh goat\'s curd to a washed rind and a crumbly aged '
                     'cheddar. Every cheese is made with vegetarian rennet. Learn why hops cut '
                     'through creaminess and dark malt loves a blue, then finish with a look behind '
                     'the scenes of the brewhouse.'),
    dict(group='weekend', title='Dongzhi Festival Dumpling Class', image='dumpling-dongzhi-festival_event.jpg',
         day='Sat', at=time(11, 0),
         venue='Golden Wok Studio, 22 Roe Street, Northbridge WA 6003', city='Perth, WA',
         price='38.00', status='Open', tiers='workshop', likes=99,
         dietary=None, seasonal='Cultural', proficiency='Beginner', ack=None,
         description='Celebrate the longest night of the year the way families have for centuries: '
                     'around a table, folding dumplings together. Your host shares how her family '
                     'marks Dongzhi, the winter solstice festival, and why dumplings and tangyuan '
                     'always make it onto the table. Mix a pork and cabbage or mushroom and tofu '
                     'filling, roll wrappers by hand, and steam your first batch while a pot of '
                     'ginger syrup simmers away for the sweet rice balls.'),
    dict(group='weekend', title='Riverside Food Truck Rally', image='riverside-foodtruck_event.jpg',
         day='Sun', at=time(12, 0),
         venue='Riverside Green, 1 East Bank Parade, Kangaroo Point QLD 4169', city='Brisbane, QLD',
         price='10.00', status='Open', tiers='general', likes=304,
         dietary=None, seasonal='Spring Flavours', proficiency=None, ack=('Enhanced', 'Brisbane'),
         description='Spring on the riverbank, with twenty-five food trucks and nowhere else you '
                     'need to be. Graze your way from Korean fried chicken and wood-fired pizza to '
                     'Venezuelan arepas and churros rolled in cinnamon sugar, then find a patch of '
                     'grass for your picnic rug. A DJ spins laid-back sets all afternoon, there\'s '
                     'giant Jenga and cornhole on the lawn, and sunset over the river is the perfect '
                     'excuse to go back for one more dessert.'),

    dict(group='kids', title='Sunrise Sourdough Bake', image='sourdough-class_event.jpg',
         day='Sat', at=time(7, 0),
         venue='The Rustic Loaf Bakery, 40 Pall Mall, Bendigo VIC 3550', city='Bendigo, VIC',
         price='45.00', status='Open', tiers='kids', likes=63,
         dietary=None, seasonal=None, proficiency='Family Friendly', ack=None,
         description='Get up with the bakers and learn the secret to a crackling crust. Step behind '
                     'the counter at The Rustic Loaf before the doors open, with the ovens already '
                     'roaring and the first trays of croissants coming out. The bakers show you how '
                     'to stretch and fold the dough, shape a round loaf and score your own pattern '
                     'into the top, while kids get a pint-sized dough of their own to shape. Warm '
                     'pastries and hot chocolate keep everyone going while the bread bakes.'),
    dict(group='kids', title='Petting Zoo Picnic Day', image='petting-zoo_event.jpg',
         day='Sun', at=time(10, 0),
         venue='Green Meadows Farm, 120 Mountain View Road, Maleny QLD 4552', city='Sunshine Coast, QLD',
         price='15.00', status='Open', tiers='kids', likes=221,
         dietary=None, seasonal='Spring Flavours', proficiency='Family Friendly', ack=None,
         description='Spring has sprung at Green Meadows, and the newest arrivals can\'t wait to meet '
                     'you. Bottle-feed the spring lambs, give the goats a scratch behind the ears '
                     'and help the farmer collect eggs from the henhouse, then hop on the '
                     'tractor-drawn hayride for a lap of the paddocks. Lunch is a relaxed picnic '
                     'under the gum trees, with fresh farm produce, homemade lemonade, and scones '
                     'with jam and cream.'),
    dict(group='kids', title="Kids' Pizza Making Party", image='kids-pizza_event.jpg',
         day='Sat', at=time(14, 0),
         venue='Little Chefs Kitchen Studio, 9 Thomas Drive, Surfers Paradise QLD 4217', city='Gold Coast, QLD',
         price='30.00', status='Open', tiers='kids', likes=189,
         dietary='Vegetarian', seasonal=None, proficiency='Family Friendly', ack=None,
         description='Little hands, big flavours, and a wood-fired oven roaring away. The Little '
                     'Chefs team teaches kids to knead, stretch and even toss their own pizza base, '
                     'then lets them loose on a colourful topping bar of mushrooms, capsicum, '
                     'olives, pineapple and plenty of mozzarella. While the pizzas cook there\'s a '
                     'dough-shaping game and a peek at how the oven works, and the party finishes '
                     'with slices, fruit skewers and a cheer for every creation.'),
    dict(group='kids', title="Storytime & S'mores Campfire", image='campsite-smore_event.jpg',
         day='Sat', at=time(18, 0),
         venue='Lakeside Campgrounds, 2 Lakeside Drive, The Entrance NSW 2261', city='Central Coast, NSW',
         price='20.00', status='Open', tiers='kids', likes=154,
         dietary=None, seasonal='Winter Comforts', proficiency='Family Friendly', ack=None,
         description='Cosy up by the crackling fire as the sun sets over the lake. A local '
                     'storyteller spins tales of lost campers, lakeside mysteries and mischievous '
                     'forest creatures, just spooky enough for the older kids and gentle for the '
                     'little ones. Between stories everyone gets a toasting stick for marshmallows, '
                     'and mugs of hot chocolate are topped up all night. The evening ends with a '
                     'torch-lit stargazing walk along the shore, where a ranger points out the '
                     'Southern Cross.'),
    dict(group='kids', title='Cupcake Decorating Workshop', image='cupcake-decor-workshop_event.jpg',
         day='Sun', at=time(11, 0),
         venue='Sweet Tooth Studio, 18 Crown Street, Wollongong NSW 2500', city='Wollongong, NSW',
         price='25.00', status='Open', tiers='kids', likes=267,
         dietary=None, seasonal=None, proficiency='Family Friendly', ack=None,
         description='Sprinkles everywhere, and that\'s exactly the point. At Sweet Tooth Studio, '
                     'kids pull up a stool at a table piled high with pastel buttercreams, edible '
                     'glitter, candy pearls and cut-out fondant shapes, and turn plain cupcakes into '
                     'their own little masterpieces. The decorators show off a few party tricks, '
                     'like piping a rose swirl or shaping a fondant unicorn, and the session ends '
                     'with a mini showcase where every creation gets its moment in the spotlight.'),
    dict(group='kids', title='Kids Cooking Challenge', image='kids-cooking_event.jpg',
         day='Sat', at=time(10, 0),
         venue='Community Kitchen Hall, 25 Flinders Street, Townsville City QLD 4810', city='Townsville, QLD',
         price='35.00', status='Open', tiers='kids', likes=312,
         dietary=None, seasonal=None, proficiency='Family Friendly', ack=None,
         description='Ready, set, cook! Young chefs race the clock in a friendly cook-off full of '
                     'twists. Each team opens a mystery basket of everyday ingredients plus one '
                     'surprise item, then has forty minutes to plan, prep and plate a dish worth '
                     'sharing. Chefs roam the benches with tips on knife safety and flavour, '
                     'families cheer from the gallery, and the judges hand out awards for Best '
                     'Flavour, Most Creative and Best Teamwork.'),
    dict(group='kids', title='Ice Cream Sundae Bar', image='icecream-bar_event.jpg',
         day='Sun', at=time(13, 0),
         venue='Scoops & Sprinkles Parlour, 1 Eastern Beach Road, Geelong VIC 3220', city='Geelong, VIC',
         price='18.00', status='Open', tiers='kids', likes=198,
         dietary='Gluten-Free', seasonal='Summer BBQ', proficiency='Family Friendly', ack=None,
         description='Beat the summer heat one scoop at a time. Step up to the sundae bar at Scoops '
                     '& Sprinkles and pile your bowl high with mango sorbet, cookies and cream or '
                     'salted caramel, then finish it with warm fudge sauce, rainbow sprinkles, '
                     'crushed honeycomb and a cherry on top. The parlour\'s gluten-free waffle bowls '
                     'are baked fresh on the spot, and kids can watch the team churn a new batch of '
                     'ice cream on the vintage machine behind the counter.'),
    dict(group='kids', title='Carnival Fun Fair Food Trail', image='carnival-funfaire_event.jpg',
         day='Sat', at=time(12, 0),
         venue='Riverside Green, 2 River Street, Mackay QLD 4740', city='Mackay, QLD',
         price='12.00', status='Open', tiers='kids', likes=276,
         dietary=None, seasonal='Holidays', proficiency='Family Friendly', ack=None,
         description='Roll up, roll up: the carnival is in town, and the food trail runs right '
                     'through it. Wind your way between the Ferris wheel and the dodgems trying '
                     'fairy floss spun on the spot, dagwood dogs dipped in tomato sauce, hot jam '
                     'doughnuts and toffee apples. Along the way, try your luck at the sideshow '
                     'games, meet the stilt walkers and face painters, and stay for the holiday '
                     'lights parade that closes out the day.'),
]

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
    return spec['description'] + '\n\n' + DETAILS[spec['title']]


WEEKDAY_OFFSET = {'Fri': 0, 'Sat': 1, 'Sun': 2}

EARLIEST_MONTH = 11


def _coming_friday(day):
    return day + timedelta(days=(4 - day.weekday()) % 7)


def _event_date(spec, today):
    offset = WEEKDAY_OFFSET.get(spec['day'])
    if spec['status'] == 'Inactive':
        return _coming_friday(today) - timedelta(days=7) + timedelta(days=offset)
    start = max(today + timedelta(days=1), date(today.year, EARLIEST_MONTH, 1))
    if spec['group'] == 'popular':
        day, month = spec['day']
        for year in (start.year, start.year + 1):
            candidate = date(year, month, day)
            if candidate >= start:
                return candidate
    friday = _coming_friday(start)
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
            price = (card_price * Decimal(share) * 2).quantize(Decimal('1'), ROUND_HALF_UP) / 2
        tickets.append(TicketType(name=name, price=price.quantize(Decimal('0.01')),
                                  capacity=spec.get('capacity', {}).get(name, capacity),
                                  description=description))
    return tickets


def _organisers():
    users = []
    for details in ORGANISERS:
        user = db.session.scalar(db.select(User).where(User.email == details['email']))
        if user is None:
            user = User(password_hash=generate_password_hash('Password123').decode('utf-8'),
                        **details)
            db.session.add(user)
        users.append(user)
    db.session.flush()
    return users


def add_sample_events():
    from .views import new_order_number  # circular import

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
            city=spec['city'],
            likes=spec['likes'],
            event_date=_event_date(spec, today),
            event_time=spec['at'],
            image_filename=spec['image'],
            dietary_preference=spec['dietary'],
            seasonal_cultural=spec['seasonal'],
            proficiency=spec['proficiency'],
            status='Cancelled' if spec['status'] == 'Cancelled' else 'Open',
            acknowledgement_type=ack_type,
            acknowledgement_city=ack_city,
            owner=users[index % len(users)],
            # staggered so Recently Added has a stable order
            created_at=now - timedelta(minutes=len(EVENTS) - index),
            ticket_types=_ticket_types(spec),
        )
        db.session.add(event)
        added.append((spec, event))
    db.session.flush()

    # ~1 ticket per 60 likes, in bookings of up to 4
    for spec, event in added:
        if spec['group'] != 'popular' or event.status == 'Cancelled':
            continue
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
            db.session.flush()  # so new_order_number sees it
            remaining -= quantity
            turn += 1

    # one block booking per tier keeps the test accounts' histories short
    for spec, event in added:
        if spec['status'] != 'Sold Out':
            continue
        buyers = [u for u in users if u is not event.owner]
        for turn, ticket in enumerate(event.ticket_types):
            left = ticket.tickets_left
            if left:
                db.session.add(Booking(
                    order_number=new_order_number(), user=buyers[turn % len(buyers)],
                    event=event, ticket_type=ticket, quantity=left,
                    total_price=ticket.price * left))
                db.session.flush()

    db.session.commit()
    return len(added)


def refresh_sample_events():
    # Only touches fields still at their old defaults, so owner edits survive.
    likes_set = descriptions_extended = cities_added = 0
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
        if not event.city:
            if event.venue.split(',')[0] == spec['venue'].split(',')[0]:
                event.venue = spec['venue']
            event.city = spec['city']
            cities_added += 1
    db.session.commit()
    return likes_set, descriptions_extended, cities_added


def main():
    from . import create_app
    app = create_app()
    with app.app_context():
        print('Database:', db.engine.url)
        count = add_sample_events()
        likes_set, extended, cities = refresh_sample_events()
        print('Added {} sample events ({} were already there). Events in the database: {}'
              .format(count, len(EVENTS) - count,
                      db.session.scalar(db.select(db.func.count(Event.id)))))
        print('Updated existing sample events: likes set on {}, descriptions extended on {}, '
              'city and address added to {}'.format(likes_set, extended, cities))


if __name__ == '__main__':
    main()
