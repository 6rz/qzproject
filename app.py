# -*- coding:utf-8 -*-
import os
import flask_admin
import flask_login

from flask import Flask, url_for, redirect, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.event import listens_for

from wtforms import form, fields, validators
from jinja2 import Markup
from flask_admin.form import rules
from flask_admin.contrib import sqla

from werkzeug.security import generate_password_hash, check_password_hash

# Create application
app = Flask(__name__, static_folder='files')


# set flask admin swatch
#app.config['FLASK_ADMIN_SWATCH'] = 'cerulean'
app.config['FLASK_ADMIN_SWATCH'] = 'cosmo'

# Create dummy secrey key so we can use sessions
app.config['SECRET_KEY'] = '123456790'

# Create in-memory database
app.config['DATABASE_FILE'] = 'sample_db.sqlite'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + app.config['DATABASE_FILE']
app.config['SQLALCHEMY_ECHO'] = True
db = SQLAlchemy(app)

# Create directory for file fields to use
file_path = os.path.join(os.path.dirname(__file__), 'files')
try:
    os.mkdir(file_path)
except OSError:
    pass

# ++ 根据登录用户设置访问目录
user_home = 'userhome'

# Create models
class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(64))
    path = db.Column(db.Unicode(128))

    def __unicode__(self):
        return self.name


class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(64))
    path = db.Column(db.Unicode(128))

    def __unicode__(self):
        return self.name

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(64))
    path = db.Column(db.Unicode(128))
    audio = db.Column(db.Unicode(128))

    def __unicode__(self):
        return '%s - %s - %s' % (self.name, self.path,self.audio)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    login = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120))
    password = db.Column(db.String(64))
    phone = db.Column(db.Unicode(32))
    notes = db.Column(db.UnicodeText)

    # Flask-Login integration
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    # Required for administrative interface
    def __unicode__(self):
        return self.name


# Define login and registration forms (for flask-login)
class LoginForm(form.Form):
    login = fields.StringField(validators=[validators.required()])
    password = fields.PasswordField(validators=[validators.required()])

    def validate_login(self, field):
        user = self.get_user()

        if user is None:
            raise validators.ValidationError('Invalid user')

        # we're comparing the plaintext pw with the the hash from the db
        if not check_password_hash(user.password, self.password.data):
        # to compare plain text passwords use
        # if user.password != self.password.data:
            raise validators.ValidationError('Invalid password')

    def get_user(self):
        return db.session.query(User).filter_by(login=self.login.data.lower()).first()


class RegistrationForm(form.Form):
    login = fields.StringField(validators=[validators.required()])
    email = fields.StringField()
    password = fields.PasswordField(validators=[validators.required()])

    def validate_login(self, field):
        if db.session.query(User).filter_by(login=self.login.data.lower()).count() > 0:
            raise validators.ValidationError('Duplicate username')


# Administrative views
class FileView(sqla.ModelView):
    # Override form field to use Flask-Admin FileUploadField
    form_overrides = {
        'path': flask_admin.form.FileUploadField
    }

    # Pass additional parameters to 'path' to FileUploadField constructor
    form_args = {
        'path': {
            'label': 'File',
            'base_path': file_path,
            'allow_overwrite': False
        }
    }
    def is_accessible(self):
        return flask_login.current_user.is_authenticated

class ImageView(sqla.ModelView):
    def _list_thumbnail(view, context, model, name):
        if not model.path:
            return ''

        return Markup('<img src="%s">' % url_for('static',filename=flask_admin.form.thumbgen_filename(model.path)))

    column_formatters = {
        'path': _list_thumbnail
    }

    # Alternative way to contribute field is to override it completely.
    # In this case, Flask-Admin won't attempt to merge various parameters for the field.
    form_extra_fields = {
        'path': flask_admin.form.ImageUploadField('Image',
                                      base_path=file_path,
                                      thumbnail_size=(100, 100, True))
    }
    def is_accessible(self):
        return flask_login.current_user.is_authenticated
        
class StoryView(sqla.ModelView):
    def storyurl(view, context, model, name):
        if not model.path:
            return ''

        return Markup('<a href="%s">%s</a>' % (url_for('static',filename=model.path),model.path))

    column_formatters = {
        'path': storyurl,
        'id': lambda v, c, m, p: m.id*2
    }

    column_list = ('id', 'name', 'path','audio')
    column_labels = dict(name=u'文件名',path=u'URL',audio=u'音频')
    def is_accessible(self):
        return flask_login.current_user.is_authenticated
        
class UserView(sqla.ModelView):
    """
    This class demonstrates the use of 'rules' for controlling the rendering of forms.
    """
    form_create_rules = [
        # Header and four fields. Email field will go above phone field.
        rules.FieldSet(('name', 'email', 'phone'), u'个人信息'),
        # Separate header and few fields
        rules.Header(u'备注'),
#        rules.Field('city'),
        # String is resolved to form field, so there's no need to explicitly use `rules.Field`
#        'country',
        # Show macro from Flask-Admin lib.html (it is included with 'lib' prefix)
        rules.Container('rule_demo.wrap', rules.Field('notes'))
    ]

    # Use same rule set for edit page
    form_edit_rules = form_create_rules

    create_template = 'rule_create.html'
    edit_template = 'rule_edit.html'

    column_exclude_list = ('password', 'notes')
    def is_accessible(self):
        return flask_login.current_user.is_authenticated
# Create customized model view class
class MyModelView(sqla.ModelView):

    def is_accessible(self):
        return flask_login.current_user.is_authenticated


# Create customized index view class that handles login & registration
class MyAdminIndexView(flask_admin.AdminIndexView):

    @flask_admin.expose('/')
    def index(self):
        if not flask_login.current_user.is_authenticated:
            return redirect(url_for('.login_view'))

        # Create User directory for file fields to use
#        user_dir = os.path.join(os.path.dirname(__file__), 'files', flask_login.current_user.name)
        user_dir = os.path.join(os.path.dirname(__file__), 'files', flask_login.current_user.login)
        ret = os.access(user_dir, os.R_OK)
#        print u"R_OK - 返回值 %s"% ret
        if ret:
#            print u"已存在目录 %s"% user_dir
            pass
        else:
            try:
                os.mkdir(user_dir)
#                print u"创建目录 %s"% user_dir                
            except OSError:
                pass
        return super(MyAdminIndexView, self).index()

    @flask_admin.expose('/login/', methods=('GET', 'POST'))
    def login_view(self):
        # handle user login
        form = LoginForm(request.form)
        if flask_admin.helpers.validate_form_on_submit(form):
            user = form.get_user()
            flask_login.login_user(user)

        if flask_login.current_user.is_authenticated:
            return redirect(url_for('.index'))
        link = '<p>Don\'t have an account? <a href="' + url_for('.register_view') + '">Click here to register.</a></p>'
        self._template_args['form'] = form
        self._template_args['link'] = link
        return super(MyAdminIndexView, self).index()

    @flask_admin.expose('/register/', methods=('GET', 'POST'))
    def register_view(self):
        form = RegistrationForm(request.form)
        if flask_admin.helpers.validate_form_on_submit(form):
            user = User()

            form.populate_obj(user)
            user.name = form.login.data.lower()
            user.login = user.name
            user.email = form.email.data
            # we hash the users password to avoid saving it as plaintext in the db,
            # remove to use plain text:
            user.password = generate_password_hash(form.password.data)

            db.session.add(user)
            db.session.commit()

            flask_login.login_user(user)
            return redirect(url_for('.index'))
        link = '<p>Already have an account? <a href="' + url_for('.login_view') + '">Click here to log in.</a></p>'
        self._template_args['form'] = form
        self._template_args['link'] = link
        return super(MyAdminIndexView, self).index()

    @flask_admin.expose('/logout/')
    def logout_view(self):
        flask_login.logout_user()
        return redirect(url_for('.index'))

    #增加这个必须要登录后才能访问，不然显示403错误
    #但是还是不许再每一个函数前加上这么判定的  ，不然还是可以直接通过地址访问
    def is_accessible(self):
        return flask_login.current_user.is_authenticated

    #跳转
    def inaccessible_callback(self, name, **kwargs):
        if flask_login.current_user.is_authenticated:
            return redirect(url_for('.index'))

class UseroptView(flask_admin.BaseView):
    @flask_admin.expose('/')
    def index(self):
        if flask_login.current_user.login == "admin":
            return render_template('user_admin.html')

        return render_template('user_profile.html')

    def is_accessible(self):
        return flask_login.current_user.is_authenticated
        
# Initialize flask-login
def init_login():
    login_manager = flask_login.LoginManager()
    login_manager.init_app(app)

    # Create user loader function
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.query(User).get(user_id)

# Delete hooks for models, delete files if models are getting deleted
@listens_for(File, 'after_delete')
def del_file(mapper, connection, target):
    if target.path:
        try:
            os.remove(os.path.join(file_path, target.path))
        except OSError:
            # Don't care if was not deleted because it does not exist
            pass


@listens_for(Image, 'after_delete')
def del_image(mapper, connection, target):
    if target.path:
        # Delete image
        try:
            os.remove(os.path.join(file_path, target.path))
        except OSError:
            pass

        # Delete thumbnail
        try:
            os.remove(os.path.join(file_path,flask_admin.form.thumbgen_filename(target.path)))
        except OSError:
            pass

# Flask views
@app.route('/')
def index():
    return render_template('index.html')


# Initialize flask-login
init_login()

# Create admin
admin = flask_admin.Admin(app,u'Qz阅读', index_view=MyAdminIndexView(), base_template='my_master.html',template_mode='bootstrap3')

# Add views
admin.add_view(FileView(File, db.session))
admin.add_view(ImageView(Image, db.session))
admin.add_view(StoryView(Story, db.session))
admin.add_view(UserView(User, db.session, name='User'))
admin.add_view(UseroptView())

def build_sample_db():
    """
    Populate a small db with some example entries.
    """

    import string
    import random

    db.drop_all()
    db.create_all()
    # passwords are hashed, to use plaintext passwords instead:
    # test_user = User(login="test", password="test")
    test_user = User(login="test", password=generate_password_hash("test"))
    db.session.add(test_user)

    user_names = [
        'Harry','Mia','Riley', 'William', 'James', 'Geoffrey', 'Lisa', 'Lucy'
    ]

    for i in range(len(user_names)):
        user = User()
        user.name = user_names[i]
        user.login = user.name.lower()
        user.email = user.login + "@example.com"
        tmp = ''.join(random.choice(string.digits) for i in range(10))
        user.phone = "(" + tmp[0:3] + ") " + tmp[3:6] + " " + tmp[6::]
        db.session.add(user)

    images = ["Buffalo", "Elephant", "Leopard", "Lion", "Rhino"]
    for name in images:
        image = Image()
        image.name = name
        image.path = name.lower() + ".jpg"
        db.session.add(image)

    for i in [1, 2, 3]:
        file = File()
        file.name = "Example " + str(i)
        file.path = "example_" + str(i) + ".pdf"
        db.session.add(file)

    for i in [1, 2, 3]:
        story = Story()
        story.name = "Example " + str(i)
        story.path = "example_" + str(i)
        story.audio = "example_" + str(i) + ".mp3"
        db.session.add(story)

    db.session.commit()
    return

if __name__ == '__main__':

    # Build a sample db on the fly, if one does not exist yet.
    app_dir = os.path.realpath(os.path.dirname(__file__))
    database_path = os.path.join(app_dir, app.config['DATABASE_FILE'])
    if not os.path.exists(database_path):
        build_sample_db()

    # Start app
    app.run(host='0.0.0.0', debug=True, use_reloader=True)
