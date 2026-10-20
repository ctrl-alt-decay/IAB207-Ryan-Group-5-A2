import re
from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import Form
from wtforms.fields import (TextAreaField, SubmitField, StringField,
                            PasswordField, SelectField, IntegerField,
                            DecimalField, DateField, TimeField, RadioField,
                            BooleanField, FieldList, FormField, HiddenField)
from wtforms.validators import (InputRequired, DataRequired, Length, Email,
                                EqualTo, NumberRange, Optional, ValidationError)
from wtforms.widgets import HiddenInput


class LoginForm(FlaskForm):
    email = StringField("Email Address", validators=[
        InputRequired('Enter your email address'),
        Email('Please enter a valid email address')])
    password = PasswordField("Password", validators=[
        InputRequired('Enter your password')])
    submit = SubmitField("Login")


class RegisterForm(FlaskForm):
    first_name = StringField("First Name", validators=[
        InputRequired('Enter your first name'), Length(max=100)])
    last_name = StringField("Last Name", validators=[
        InputRequired('Enter your last name'), Length(max=100)])
    email = StringField("Email Address", validators=[
        InputRequired('Enter your email address'),
        Email("Please enter a valid email"), Length(max=150)])

    # DataRequired, not InputRequired, so whitespace-only is rejected
    contact_number = StringField("Contact Number", validators=[
        DataRequired('Enter your contact number'), Length(max=20)])
    street_address = StringField("Street Address", validators=[
        DataRequired('Enter your street address'), Length(max=255)])

    password = PasswordField("Password", validators=[
        InputRequired(),
        Length(min=8, message='Password must be at least 8 characters'),
        EqualTo('confirm', message="Passwords should match")])
    confirm = PasswordField("Confirm Password", validators=[
        InputRequired('Confirm your password')])

    submit = SubmitField("Register")


class ProfilePictureForm(FlaskForm):
    # extension check only, not the actual file contents
    ALLOWED = ['jpg', 'jpeg', 'png', 'gif']

    picture = FileField("Profile Picture", validators=[
        FileRequired('Choose an image to upload'),
        FileAllowed(ALLOWED, 'Images only - jpg, jpeg, png or gif')])
    submit = SubmitField("Upload")


# CSRF only. Quantity fields vary per event so the view reads them itself
# (see _requested_quantities in views.py).
class OrderForm(FlaskForm):
    pass


# Plain Form, not FlaskForm - it's nested in EventForm which has the CSRF token.
# Blank rows are ignored; half-filled ones get caught in validate().
class TicketTypeForm(Form):
    # The CSS-only "Add Ticket Type" checkbox in listevent.html. Unticked rows are
    # ignored even if they still have typed data. Row 1 sends it via a hidden input.
    included = BooleanField()
    # Edit Event only - lets us update the existing TicketType in place so its
    # bookings stay attached.
    ticket_id = IntegerField(widget=HiddenInput(), validators=[Optional()])
    name = StringField("Ticket Type", validators=[Optional(), Length(max=50)])
    price = DecimalField("Price", places=2, validators=[
        Optional(),
        NumberRange(min=0, max=999999.99, message='Price must be between $0 and $999,999.99')])
    capacity = IntegerField("Capacity", validators=[
        Optional(), NumberRange(min=1, message='Capacity must be at least 1')])
    description = StringField("Ticket Description", validators=[
        Optional(), Length(max=255)])

    def is_blank(self):
        if not self.included.data:
            return True
        return not any(f.raw_data and f.raw_data[0].strip()
                       for f in self if f not in (self.included, self.ticket_id))

    def validate(self, extra_validators=None):
        if not self.included.data:
            return True
        if not super().validate(extra_validators):
            return False
        if self.is_blank():
            return True
        valid = True
        if not (self.name.data or '').strip():
            self.name.errors.append('Enter a ticket type name')
            valid = False
        if self.price.data is None:
            self.price.errors.append('Enter a price')
            valid = False
        if self.capacity.data is None:
            self.capacity.errors.append('Enter a capacity')
            valid = False
        return valid


# 'None' options are saved as empty. Date/time come from the A1 text pickers
# as dd/mm/yyyy and hh:mm, not native date inputs.
class EventForm(FlaskForm):
    # style.css has a show rule per extra row - add more there if you raise this.
    TICKET_ROWS = 6

    DIETARY = ['None', 'Gluten-Free', 'Halal', 'Keto Friendly', 'Kosher',
               'Low Carb', 'Paleo', 'Vegan', 'Vegetarian']
    SEASONAL = ['None', 'Spring Flavours', 'Summer BBQ', 'Autumn Harvest',
                'Winter Comforts', 'Cultural', 'Holidays']
    PROFICIENCY = ['None', 'Beginner', 'Intermediate', 'Expert', 'Foodie',
                   'Chef', 'Family Friendly']

    CAPITAL_CITIES = ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide',
                      'Hobart', 'Darwin', 'Canberra', 'Other']
    # Rendered via views.ack_text, which fills {eventname} and fixes the line
    # breaks. 'Other' is empty - the creator types the custodians in instead.
    GENERIC_ACK_PREVIEW = """The organisers of {eventname} would like to acknowledge and pay 
    respects to the Traditional Owners of the land we gather and connect on. We also recognise 
    the ongoing connection between Indigenous peoples and their Country that has never been ceded.
      Always was and always will be Aboriginal land."""
    ENHANCED_ACK_PREVIEW = {
        'Brisbane-AoC' : """The organisers of {eventname} acknowledge and pay their respects to the 
        traditional owners of Meanjin (Brisbane), the Turrbal and Jagera peoples. 
        We recognise and appreciate that these lands have forever been a place of community 
        and are now home to a multitude of culinary experiences. While we enjoy the flavourful 
        journey of the present day, we also pay homage to the ever present and ever lasting cultures 
        that cultivated the lands and waters we derive our ingredients from. The Turrbal and Jagera 
        communities have been discovering, innovating and connecting over food for millenia using 
        native flora and fauna including pencil yams, zamia nuts, goannas, and scrub turkeys. 
        We are ever grateful to Indigenous peoples for their deep respect and responsibility of the 
        land that was never ceded.""",

        'Sydney-AoC' : """The organisers of {eventname} acknowledge and pay their respects to the 
        traditional owners of Warrang (or Cadi), the Gadigal people. We recognise and appreciate 
        that these lands have forever been a place of community and are now home to a multitude 
        of culinary experiences. While we enjoy the flavourful journey of the present day, we 
        also pay homage to the ever present and ever lasting cultures that cultivated the lands 
        and waters we derive our ingredients from. The Gadigal people cultivated their meals 
        through fishing in the cove and other nearby waterways, in which they sustained plentiful 
        fish populations by using shells to indicate to others when it was best for an area to be 
        left to replenish itself after being fished from. These early practices of sustainability 
        have been upheld by Indigenous populations for thousands of years, to which we are ever 
        thankful. """,

        'Canberra-AoC' : """The organisers of {eventname} acknowledge and pay their respects to the 
        traditional owners of Canberra, the Ngambri and Ngunnawal peoples. We recognise and 
        appreciate that these lands have forever been a place of community and are now home to a 
        multitude of culinary experiences. While we enjoy the flavourful journey of the present 
        day, we also pay homage to the ever present and ever lasting cultures that cultivated the 
        lands and waters we derive our ingredients from. A key ingredient used by the Ngambri was 
        the murnong (yam daisy). Murnong would be collected by the Ngambri and Ngunnawal using yam 
        sticks and dillybags. It would also be prepared alongside other plants like bulrushes and 
        apple berries, as well as meat from witchetty grubs and brolgas. We pay our respects to 
        the culture of the Ngambri and Ngunnawal peoples that lives and breathes alongside their 
        Country.""", 

        'Melbourne-AoC' : """The organisers of {eventname} acknowledge and pay their respects to the 
        traditional owners of Naarm, the Wurundjeri and Boon Wurrung peoples. We recognise and 
        appreciate that these lands have forever been a place of community and are now home to a 
        multitude of culinary experiences. While we enjoy the flavourful journey of the present 
        day, we also pay homage to the ever present and ever lasting cultures that cultivated the 
        lands and waters we derive our ingredients from. Traditionally, the Wurundjeri and Boon 
        Wurrung peoples lived in accordance with the seasons to find food. Yam daisies would be 
        bitter in the winter but sweet by spring and in the wetter seasons, the creeks were 
        abundant with eel and ducks. They also made use of both the meat and furs of possums 
        for food and clothing, getting the most out of the animal. We acknowledge and pay our 
        respects to the Elders of the past, present and future who continue to maintain their 
        people’s connections to the lands and waters of Naarm.""",

        'Darwin-AoC' : """The organisers of {eventname} acknowledge and pay their respects to 
        the traditional owners of Gulumoerrgin, the Larrakia people. We recognise and appreciate 
        that these lands have forever been a place of community and are now home to a multitude 
        of culinary experiences. While we enjoy the flavourful journey of the present day, we also 
        pay homage to the ever present and ever lasting cultures that cultivated the lands and 
        waters we derive our ingredients from. The mangroves of Gulumoerrgin have served as a 
        core food source for the Larrakia people for millenia. There they would seek out mangrove 
        worms, longbums (telescopic snails), mussels, and periwinkles.The worms and longbums had 
        to be specially prepared to avoid illness and this is a technique the Larrakia still 
        practise to this day. We acknowledge the Larrakia people’s ongoing connection to their 
        Country and the fact it has never been ceded.""",

        'Perth-AoC' : """The organisers of {eventname} acknowledge and pay their respects to the 
        traditional owners of Boorloo, the Whadjuk Noongar people. We recognise and appreciate 
        that these lands have forever been a place of community and are now home to a multitude 
        of culinary experiences. While we enjoy the flavourful journey of the present day, we 
        also pay homage to the ever present and ever lasting cultures that cultivated the lands 
        and waters we derive our ingredients from. The lands and waterways of Boorloo are 
        expansive and home to a variety of flora and fauna. Through their connection and 
        history with their Country, the Whadjuk Noongar would travel with the many seasons 
        the area experienced in order to find food. During the hot and windy months in the 
        grasslands, wattle seeds would be used to make damper and mallee fowl eggs were in 
        abundance. Then, as the weather cooled off and got wetter, zamia palm nuts, frogs and 
        kangaroos became more prevalent in the Whadjuk Noongar diet. We pay our respects to the 
        Elders, past and present, of the Whadjuk Noongar and their everlasting connection to 
        Boorloo.""",

        'Adelaide-AoC' : """The organisers of {eventname} acknowledge and pay their respects to 
        the traditional owners of Tarndanya, the Kaurna people. We recognise and appreciate that 
        these lands have forever been a place of community and are now home to a multitude of 
        culinary experiences. While we enjoy the flavourful journey of the present day, we also 
        pay homage to the ever present and ever lasting cultures that cultivated the lands and 
        waters we derive our ingredients from. The sand dunes of Tarndanya’s coastline are the 
        edible garden of the Kaurna people. When in season, the dunes produced small fruit-like 
        plants such as mantarri and wadni that could be eaten. Away from the coast, tarnta tutha 
        (kangaroo grass) was harvested using fire by the Kaurna to turn into damper and, as the 
        rainy season came, yam daisies would be collected to eat. We acknowledge and pass on our 
        respects to the Kaurna people and their enduring connection to the lands and waters of 
        Tarndanya. """,

        'Hobart-AoC' : """The organisers of {eventname} acknowledge and pay their respects to the
          traditional owners of Nipaluna, the Palawa people. We recognise and appreciate that 
          these lands have forever been a place of community and are now home to a multitude of 
          culinary experiences. While we enjoy the flavourful journey of the present day, we also 
          pay homage to the ever present and ever lasting cultures that cultivated the lands and 
          waters we derive our ingredients from. The Palawa people commonly used mutton birds as
            their main source of protein, as well as wallaby - which would be cooked over fire. 
            The sea provided oysters which would pair tastily with the native pepper berry and 
            blue-gum honey, which added a fruity and spicy taste to the meal. We recognise and 
            appreciate the strong identity of the Palawa people is everlasting, much like their 
            connection to their Country of Nipaluna.""",
        'Other-AoC': ''
    }

    title = StringField("Event Title", validators=[
        DataRequired('Enter an event title'), Length(max=150)])
    image = FileField("Event Image", validators=[
        FileRequired('Choose an image for your event'),
        FileAllowed(ProfilePictureForm.ALLOWED, 'Images only - jpg, jpeg, png or gif')])
    description = TextAreaField("Description", validators=[
        DataRequired('Describe your event')])

    dietary_preference = SelectField("Dietary Preference", choices=DIETARY)
    seasonal_cultural = SelectField("Seasonal / Cultural Options", choices=SEASONAL)
    proficiency = SelectField("Proficiency", choices=PROFICIENCY)

    CITIES = ['Adelaide, SA', 'Albury, NSW', 'Alice Springs, NT', 'Ballarat, VIC',
              'Bendigo, VIC', 'Brisbane, QLD', 'Bunbury, WA', 'Bundaberg, QLD',
              'Cairns, QLD', 'Canberra, ACT', 'Central Coast, NSW', 'Coffs Harbour, NSW',
              'Darwin, NT', 'Geelong, VIC', 'Gold Coast, QLD', 'Hervey Bay, QLD',
              'Hobart, TAS', 'Launceston, TAS', 'Mackay, QLD', 'Melbourne, VIC',
              'Newcastle, NSW', 'Perth, WA', 'Rockhampton, QLD', 'Sunshine Coast, QLD',
              'Sydney, NSW', 'Toowoomba, QLD', 'Townsville, QLD', 'Wagga Wagga, NSW',
              'Wollongong, NSW']

    venue = StringField("Venue / Address", validators=[
        DataRequired('Enter the venue address'), Length(max=255)])
    city = SelectField("City", choices=[('', 'Choose the closest city')]
                       + [(city, city) for city in CITIES],
                       validators=[DataRequired('Choose the city closest to the venue')])
    event_date = DateField("Event Date", format='%d/%m/%Y', validators=[
        InputRequired('Choose the event date')])
    event_time = TimeField("Event Time", format='%H:%M', validators=[
        InputRequired('Choose the event time')])

    acknowledgement_type = RadioField("Acknowledgement of Country", default='None',
                                      choices=['None', 'Generic', 'Enhanced'])
    # Only required for Enhanced, so validate_acknowledgement_city does the choice check
    acknowledgement_city = RadioField("Where is your event?", choices=CAPITAL_CITIES,
                                      validate_choice=False)
    # Enhanced-only. Don't add Optional() - it would skip the validate_ methods below.
    acknowledgement_custodians = StringField("Traditional Custodians", validators=[
        Length(max=255)])
    acknowledgement_connection = TextAreaField("How does your event connect to Country?",
                                               validators=[Length(max=600)])
    acknowledgement_commitment = StringField("A commitment", validators=[
        Length(max=255)])
    acknowledgement_elders = BooleanField("Pay respects to Elders", default=True)

    ticket_types = FieldList(FormField(TicketTypeForm),
                             min_entries=TICKET_ROWS, max_entries=TICKET_ROWS)

    submit = SubmitField("Submit")

    def validate_event_date(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('The event date cannot be in the past')

    def validate_acknowledgement_city(self, field):
        if self.acknowledgement_type.data == 'Enhanced' and field.data not in self.CAPITAL_CITIES:
            raise ValidationError('Choose where your event is for the Enhanced acknowledgement')

    def _enhanced(self):
        return self.acknowledgement_type.data == 'Enhanced'

    @staticmethod
    def _no_welcome(field):
        # only Traditional Owners can give a Welcome to Country
        if field.data and re.search(r'\bwelcom', field.data, re.IGNORECASE):
            raise ValidationError('Leave out "welcome" - only Traditional Owners can give '
                                  'a Welcome to Country')

    def validate_acknowledgement_custodians(self, field):
        if not self._enhanced():
            return
        if self.acknowledgement_city.data == 'Other' and not (field.data or '').strip():
            raise ValidationError("Enter the Traditional Custodians of your event's location")
        self._no_welcome(field)

    def validate_acknowledgement_connection(self, field):
        if not self._enhanced():
            return
        if not (field.data or '').strip():
            raise ValidationError('Say how your event connects to Country')
        self._no_welcome(field)

    def validate_acknowledgement_commitment(self, field):
        if self._enhanced():
            self._no_welcome(field)

    def validate_ticket_types(self, field):
        rows = [entry.form for entry in field.entries if not entry.form.is_blank()]
        if not rows:
            raise ValidationError('Add at least one ticket type')
        names = [(row.name.data or '').strip().lower() for row in rows]
        if len(names) != len(set(names)):
            raise ValidationError('Each ticket type needs a different name')


class CancelEventForm(FlaskForm):
    submit = SubmitField("Yes, Cancel Event")


# Rendered by hand per card in _event_macros.html. The route decides like vs unlike.
class LikeForm(FlaskForm):
    next = HiddenField()


class CommentForm(FlaskForm):
    MAX_LENGTH = 1000

    body = TextAreaField("Comment", validators=[
        DataRequired('Write a comment before posting'),
        Length(max=MAX_LENGTH, message='Comments can be up to 1000 characters')])
    submit = SubmitField("Post")


# Image is optional (keeps the current one), and an already-past date is fine
# as long as it's unchanged. The route sets original_date before validating.
class EditEventForm(EventForm):
    image = FileField("Event Image", validators=[
        FileAllowed(ProfilePictureForm.ALLOWED, 'Images only - jpg, jpeg, png or gif')])

    original_date = None

    def validate_event_date(self, field):
        if field.data and field.data != self.original_date and field.data < date.today():
            raise ValidationError('The event date cannot be in the past')
