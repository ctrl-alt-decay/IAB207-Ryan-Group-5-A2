# WTForms classes. Each is validated server-side in its route with
# validate_on_submit(), which also checks the CSRF token that {{ form.hidden_tag() }}
# puts into the template. Error messages here are what the user sees.
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


# Buying tickets for one event. A booking is for ONE ticket type at a time,
# because each Booking row holds a single ticket_type_id (see models.py).
class BookingForm(FlaskForm):
    # choices are filled in by the route with that event's own ticket types, so
    # validation also rejects a ticket type belonging to a different event
    ticket_type = SelectField("Ticket Type", coerce=int, validators=[
        InputRequired('Choose a ticket type')])
    quantity = IntegerField("Quantity", validators=[
        InputRequired('Choose how many tickets'),
        NumberRange(min=1, message='Choose at least 1 ticket')])
    submit = SubmitField("Purchase")


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

    # Acknowledgement of Country (#6). Only the choice is saved: the type, plus
    # the capital city when the type is Enhanced. These preview lines are
    # PLACEHOLDER wording until the real acknowledgement copy is written.
    CAPITAL_CITIES = ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide',
                      'Hobart', 'Darwin', 'Canberra']
    GENERIC_ACK_PREVIEW = 'GENERIC ACKNOWLEDGEMENT OF COUNTRY PLACEHOLDER TEXT'
    ENHANCED_ACK_PREVIEW = 'ENHANCED ACKNOWLEDGEMENT OF COUNTRY PLACEHOLDER TEXT for {}'

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

    venue = StringField("Venue / Address", validators=[
        DataRequired('Enter the venue address'), Length(max=255)])
    event_date = DateField("Event Date", format='%d/%m/%Y', validators=[
        InputRequired('Choose the event date')])
    event_time = TimeField("Event Time", format='%H:%M', validators=[
        InputRequired('Choose the event time')])

    acknowledgement_type = RadioField("Acknowledgement of Country", default='None',
                                      choices=['None', 'Generic', 'Enhanced'])
    # No city is fine unless the type is Enhanced, so the usual "must be one of
    # the choices" check is off and validate_acknowledgement_city does it instead
    acknowledgement_city = RadioField("Capital City", choices=CAPITAL_CITIES,
                                      validate_choice=False)

    ticket_types = FieldList(FormField(TicketTypeForm),
                             min_entries=TICKET_ROWS, max_entries=TICKET_ROWS)

    submit = SubmitField("Submit")

    def validate_event_date(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('The event date cannot be in the past')

    def validate_acknowledgement_city(self, field):
        if self.acknowledgement_type.data == 'Enhanced' and field.data not in self.CAPITAL_CITIES:
            raise ValidationError('Choose a capital city for the Enhanced acknowledgement')

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
