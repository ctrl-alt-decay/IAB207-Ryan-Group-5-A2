# WTForms classes. Each is validated server-side in its route with
# validate_on_submit(), which also checks the CSRF token that {{ form.hidden_tag() }}
# puts into the template. Error messages here are what the user sees.
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


# creates the login information
class LoginForm(FlaskForm):
    # users are identified by email - the User model has no user name field
    email = StringField("Email Address", validators=[
        InputRequired('Enter your email address'),
        Email('Please enter a valid email address')])
    password = PasswordField("Password", validators=[
        InputRequired('Enter your password')])
    submit = SubmitField("Login")


 # this is the registration form
class RegisterForm(FlaskForm):
    first_name = StringField("First Name", validators=[
        InputRequired('Enter your first name'), Length(max=100)])
    last_name = StringField("Last Name", validators=[
        InputRequired('Enter your last name'), Length(max=100)])
    email = StringField("Email Address", validators=[
        InputRequired('Enter your email address'),
        Email("Please enter a valid email"), Length(max=150)])

    # required by the brief (item 8). DataRequired also rejects whitespace-only
    # input, which InputRequired would let through as a blank value.
    contact_number = StringField("Contact Number", validators=[
        DataRequired('Enter your contact number'), Length(max=20)])
    street_address = StringField("Street Address", validators=[
        DataRequired('Enter your street address'), Length(max=255)])

    # linking two fields - password should be equal to data entered in confirm
    password = PasswordField("Password", validators=[
        InputRequired(),
        Length(min=8, message='Password must be at least 8 characters'),
        EqualTo('confirm', message="Passwords should match")])
    confirm = PasswordField("Confirm Password", validators=[
        InputRequired('Confirm your password')])

    # submit button
    submit = SubmitField("Register")


# lets a logged in user upload a profile picture on the account page
class ProfilePictureForm(FlaskForm):
    # FileAllowed only checks the file extension, not the file's actual contents.
    ALLOWED = ['jpg', 'jpeg', 'png', 'gif']

    picture = FileField("Profile Picture", validators=[
        FileRequired('Choose an image to upload'),
        FileAllowed(ALLOWED, 'Images only - jpg, jpeg, png or gif')])
    submit = SubmitField("Upload")


# Confirming an order on the checkout screen (#21). An order can have any of
# the event's ticket types, so its fields depend on the event: the view reads
# the quantities itself (one 'qty-<ticket type id>' field per type - see
# _requested_quantities in views.py). This form only checks the CSRF token.
class OrderForm(FlaskForm):
    pass


# One row of the Ticket Types table on Create Event. A plain wtforms Form (not
# FlaskForm) because it sits inside EventForm, which already has the CSRF token.
# Every field is Optional so a completely blank row is simply ignored; a row
# that is only partly filled in is caught by validate() below.
class TicketTypeForm(Form):
    # Ticked when the row has been added with "Add Ticket Type" (a CSS-only
    # checkbox - see the Ticket Types section of listevent.html). The first row
    # always sends it from a hidden input. A row that isn't included is ignored
    # entirely, even if something was typed into it before it was removed.
    included = BooleanField()
    # Edit Event only: which existing TicketType this row is, so saving updates
    # it in place (its bookings stay attached). Empty for a new row.
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
        """True when this row wasn't added, or nothing at all was typed into it."""
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
        # a started row needs a name, price and capacity (description is optional)
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


# Create Event (#19). The option lists match the A1 page; 'None' is saved as
# an empty column. Event Date and Time keep the A1 text pickers, so they are
# parsed from dd/mm/yyyy and hh:mm text rather than the browser's date input.
class EventForm(FlaskForm):
    # Most ticket rows a user can add. All of them are rendered, and rows 2+ stay
    # hidden until added. style.css has one show rule per extra row (Ticket Types
    # section), so add rules there if you raise this.
    TICKET_ROWS = 6

    DIETARY = ['None', 'Gluten-Free', 'Halal', 'Keto Friendly', 'Kosher',
               'Low Carb', 'Paleo', 'Vegan', 'Vegetarian']
    SEASONAL = ['None', 'Spring Flavours', 'Summer BBQ', 'Autumn Harvest',
                'Winter Comforts', 'Cultural', 'Holidays']
    PROFICIENCY = ['None', 'Beginner', 'Intermediate', 'Expert', 'Foodie',
                   'Chef', 'Family Friendly']

    # Acknowledgement of Country (#6). Generic is one fixed statement. Enhanced
    # is a guided builder: the creator picks where the event is, says how it
    # connects to Country and (optionally) a commitment, and the statement is
    # put together from their answers (views.compose_acknowledgement).
    CAPITAL_CITIES = ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide',
                      'Hobart', 'Darwin', 'Canberra', 'Other']
    GENERIC_ACK_PREVIEW = 'GENERIC ACKNOWLEDGEMENT OF COUNTRY PLACEHOLDER TEXT'
    # PLACEHOLDERS - to be filled in from research: each capital's Traditional
    # Custodians as they should be named in a statement ("the ... people"),
    # and the source that name came from, so the claim can be checked.
    CAPITAL_CUSTODIANS = {city: '[{} Traditional Custodians - placeholder]'.format(city)
                          for city in CAPITAL_CITIES if city != 'Other'}
    CUSTODIAN_SOURCES = {city: '[source - placeholder]'
                         for city in CAPITAL_CITIES if city != 'Other'}

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

    # The major Australian cities an event can be listed under: the one closest
    # to the venue, so an event in a suburb or a nearby town still shows up under
    # its city. Stored as shown, e.g. 'Townsville, QLD'.
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
    # '' is the "Choose the closest city" prompt, which DataRequired refuses
    city = SelectField("City", choices=[('', 'Choose the closest city')]
                       + [(city, city) for city in CITIES],
                       validators=[DataRequired('Choose the city closest to the venue')])
    event_date = DateField("Event Date", format='%d/%m/%Y', validators=[
        InputRequired('Choose the event date')])
    event_time = TimeField("Event Time", format='%H:%M', validators=[
        InputRequired('Choose the event time')])

    acknowledgement_type = RadioField("Acknowledgement of Country", default='None',
                                      choices=['None', 'Generic', 'Enhanced'])
    # No city is fine unless the type is Enhanced, so the usual "must be one of
    # the choices" check is off and validate_acknowledgement_city does it instead
    acknowledgement_city = RadioField("Where is your event?", choices=CAPITAL_CITIES,
                                      validate_choice=False)
    # The rest of the Enhanced builder. Only used when the type is Enhanced;
    # the validate_ methods below decide what's required. (No Optional() here:
    # on an empty field it would skip those validate_ methods too.)
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
        # only Traditional Owners (or people they've given permission to) can
        # give a Welcome to Country, so an Acknowledgement shouldn't "welcome"
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


# The confirmation button on the Cancel Event page. A form of its own so the
# POST carries a CSRF token like every other change on the site.
class CancelEventForm(FlaskForm):
    submit = SubmitField("Yes, Cancel Event")


# The heart on each event card: a tiny form written out in _event_macros.html
# (one per card, so not from hidden_tag()). This checks its CSRF token; `next`
# is the page the heart was clicked on, to go back to afterwards. The route
# works out whether it's a like or an unlike.
class LikeForm(FlaskForm):
    next = HiddenField()


# Posting a comment on an event page (#23). DataRequired also refuses a comment
# that's nothing but spaces.
class CommentForm(FlaskForm):
    MAX_LENGTH = 1000

    body = TextAreaField("Comment", validators=[
        DataRequired('Write a comment before posting'),
        Length(max=MAX_LENGTH, message='Comments can be up to 1000 characters')])
    submit = SubmitField("Post")


# Edit Event (#24): the Create Event form with two differences. The image is
# optional (leave it empty to keep the current one), and the event's existing
# date is accepted even if it has passed - only a *new* date must be upcoming.
# The route sets original_date before validating.
class EditEventForm(EventForm):
    image = FileField("Event Image", validators=[
        FileAllowed(ProfilePictureForm.ALLOWED, 'Images only - jpg, jpeg, png or gif')])

    original_date = None

    def validate_event_date(self, field):
        if field.data and field.data != self.original_date and field.data < date.today():
            raise ValidationError('The event date cannot be in the past')
