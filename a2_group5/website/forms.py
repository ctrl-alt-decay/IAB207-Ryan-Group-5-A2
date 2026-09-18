# WTForms classes. Each is validated server-side in its route with
# validate_on_submit(), which also checks the CSRF token that {{ form.hidden_tag() }}
# puts into the template. Error messages here are what the user sees.
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.fields import (TextAreaField, SubmitField, StringField,
                            PasswordField)
from wtforms.validators import (InputRequired, DataRequired, Length, Email,
                                EqualTo)


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
