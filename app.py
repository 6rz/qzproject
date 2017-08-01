# -*- coding:utf-8 -*-
import os
import flask_admin
import flask_login
import subprocess
import sys
import pandas
import sqlite3
import json

from flask import Flask, url_for, redirect, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.event import listens_for

from wtforms import form, fields, validators
from jinja2 import Markup
from flask_admin.form import rules
from flask_admin.contrib import sqla

from werkzeug.security import generate_password_hash, check_password_hash

reload(sys)
#sys.setdefaultencoding('gb18030')
sys.setdefaultencoding( "utf-8" )



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
    __tablename__ = 'stories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(64))
    path = db.Column(db.Unicode(128))
    audio = db.Column(db.Unicode(128))
    user_story = db.relationship('UserStory', backref='story')
    
    def __unicode__(self):
        return '%s - %s - %s' % (self.name, self.path,self.audio)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    login = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120))
    password = db.Column(db.String(64))
    phone = db.Column(db.Unicode(32))
    notes = db.Column(db.UnicodeText)
    user_story = db.relationship('UserStory', backref='user')
    
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

class UserStory(db.Model):
    __tablename__ = 'userstories'
    id = db.Column(db.Integer, primary_key=True)
    fk_uid = db.Column(db.Integer, db.ForeignKey('users.id'))
    fk_sid = db.Column(db.Integer, db.ForeignKey('stories.id'))
    user_mp3 = db.Column(db.Unicode(128))

    def __unicode__(self):
        return '%s - %s - %s' % (self.id, self.fk_uid,self.fk_sid)

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
        'id': lambda v, c, m, p: m.id
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
        rules.Field('user_story'),
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
#    can_create = False

    def is_accessible(self):
        return flask_login.current_user.is_authenticated
        
#class UserStoryView(sqla.ModelView):
#    column_list = ('id', 'fk_uid', 'fk_sid','user_mp3')
#    column_labels = dict(id=u'ID',fk_uid=u'用户ID',fk_sid=u'故事ID',user_mp3=u'音频')
#    def is_accessible(self):
#        return flask_login.current_user.is_authenticated

class UserStoryView(sqla.ModelView):
    @flask_admin.expose('/')
    def index(self):
#        with sqlite3.connect('sample_db.sqlite') as db:
#            sql = 'select userstories.*,users.name,stories.name from userstories,users,stories where userstories.fk_uid=users.id and userstories.fk_uid=%s and userstories.fk_sid = stories.id' % (flask_login.current_user.id)
#            df = pandas.read_sql_query(sql,con = db)
        output =  build_booked_story()
        return render_template('user_booked.html',data=output)
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
    
#        output = subprocess.Popen(['dir'],stdout=subprocess.PIPE,shell=True).communicate()
#        print output[0]
        output =  build_story_html()
        if flask_login.current_user.login == "admin":
#            return render_template('user_admin.html',data=output[0])
            return render_template('user_story.html',data=output)
            
#        return render_template('user_profile.html',data=output[0])
        return render_template('user_story.html',data=output)
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
admin.add_view(UserView(User, db.session, name='Userlist'))
admin.add_view(UserStoryView(UserStory, db.session, name='UserStory'))
admin.add_view(UseroptView(name = 'UserOption'))

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
        
    for i in [1, 2, 3]:
        ustory = UserStory()
        ustory.fk_uid = i
        ustory.fk_sid = i
        ustory.user_mp3 = "user_" + str(i) + ".mp3"
        db.session.add(ustory)
    
    db.session.commit()
    return

def build_booked_story():
    divs_story = ""
    with sqlite3.connect('sample_db.sqlite') as db:
        sql = 'select userstories.*,users.name as u_name,stories.name as s_name from userstories,users,stories where userstories.fk_uid=users.id and userstories.fk_uid=%s and userstories.fk_sid = stories.id' % (flask_login.current_user.id)
        df = pandas.read_sql_query(sql,con = db)
        for i in range(0,len(df)):
            divs_story +='''
                <tr>
                    <td>
                        <input type="checkbox" name="rowid" class="action-checkbox" value="%s" title="Select record" />
                    </td>
                    <td class="list-buttons-column">
                        <input id="userstory" name="userstory" type="hidden" value="%s">
                    </td>                    
                    <td class="col-id">
                        %s
                    </td>
                    <td class="col-name">
                        %s
                    </td>
                    <td class="col-audio">
                        <audio controls><source src="%s" type="audio/mpeg">您的浏览器不支持 audio 元素。</audio>
                    </td>
                </tr>
                '''%(df['id'][i],df['id'][i],df['id'][i],df['s_name'][i],df['user_mp3'][i])
    return divs_story
    
def build_story_html():
    tmp_mp3 = [
    "http://bos.nj.bpc.baidu.com/v1/developer/39cb48e4-bd09-4e9d-933c-be8bfea0cb45.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/ff390320-372f-4564-87ad-e7eb5cf3f90b.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/ad3240d0-9b50-491f-98a5-d0b956a9f426.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/c303922d-194c-4015-9377-fbf811010a3d.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/eaab7248-af7a-4cd1-94b2-27ddb12ea65a.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/8f5ad243-d684-4443-a3bc-16e6924ae0a4.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/00a81304-25d8-4f31-88b4-44a9b7e620d2.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/24f0aea6-1757-4fec-98b7-30cb483e70c2.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/b3675dd1-5378-43ca-90cc-467c433aab3b.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/f4e9efb0-9207-4f81-93bf-d3871fc33c2a.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/17c99ecd-4ee0-442e-989c-bf26a1c0eca0.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/8855ebb1-0b5f-47a9-96bd-4fd2c9559b83.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/676ded6f-d94a-417e-b5cc-b8ec3aebcff4.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/d5bbfae3-2b1b-4b5a-a2ee-702e64214809.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/207adf7b-99c3-4a0b-a6ac-b89b1d783858.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/97fea474-2512-407b-9c9f-9fadf7306216.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/638792d8-4544-46cf-92cc-88a32ea153cf.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/d648c408-7f89-4185-aa61-77d31080d60a.mp3",
    "http://bos.nj.bpc.baidu.com/v1/developer/e4700f90-0b96-40d0-8a9d-5b53bc0626b3.mp3"
    ]
    divs_story = ""  
    with sqlite3.connect('qzstorys.sqlite') as db:
        df = pandas.read_sql_query('SELECT * FROM qzstory',con = db)
        for i in range(0,len(df)):
            divs_story += '''
                <tr>
                    <form class="icon" method="POST" action="/admin/userstory/new/">
                    <td>
                        <input type="checkbox" name="rowid" class="action-checkbox" value="1"
                        title="Select record" />
                    </td>
                    <td class="list-buttons-column">

                        <input id="user" name="user" type="hidden" value="%s">
                        <input id="story" name="story" type="hidden" value="%s">
                        <input id="user_mp3" name="user_mp3" type="hidden" value="%s">   
                        <button onclick="return safeConfirm('Are you sure you want to Add this story to your lib?');" title="订阅">
                            <span class="fa fa-plus glyphicon glyphicon-plus">添加</span>
                        </button>
 
                    </td>
                    <td class="col-id">
                        %s
                    </td>
                    <td class="col-name">
                        %s
                    </td>
                    <td class="col-path">
                        <a href="%s">
                            %s
                        </a>
                    </td>
                    <td class="col-audio">
                        <audio controls><source src="%s" type="audio/mpeg">您的浏览器不支持 audio 元素。</audio>
                    </td>
                    <td class="col-btn">
                        <a class="btn btn-default" href="%s" role="button">听故事 &raquo;</a>
                    </td>
                   </form>                    
                </tr>
            ''' % (flask_login.current_user.id,i,tmp_mp3[i],i,df['story_title'][i],df['story_url'][i],df['story_title'][i],tmp_mp3[i],df['story_url'][i])
    return divs_story
if __name__ == '__main__':

    # Build a sample db on the fly, if one does not exist yet.
    app_dir = os.path.realpath(os.path.dirname(__file__))
    database_path = os.path.join(app_dir, app.config['DATABASE_FILE'])
    if not os.path.exists(database_path):
        build_sample_db()

    # Start app
    app.run(host='0.0.0.0', debug=True, use_reloader=True)
