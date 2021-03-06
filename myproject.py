from flask import Flask, render_template, request, redirect, jsonify, url_for, flash, make_response, session
from flask_mail import Mail, Message
from flask_login import login_user, login_required, logout_user, UserMixin, LoginManager, login_manager, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from time import time
from datetime import datetime
from flask_cors import CORS
import os
from sqlalchemy import event
from sqlalchemy.orm import mapper
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
from uuid import uuid4
import json
import requests
import sqlite3
import pandas as pd

# from tmdbv3api import TMDB
# tmdb = TMDB()
# tmdb.api_key = 'e98fa3586be9a1f4b77ad437cdef9490'
# tmdb.language = 'en'
# tmdb.debug = True
# import tmdbsimple as tmdb
# tmdb.API_KEY = 'e98fa3586be9a1f4b77ad437cdef9490'
 
 

basedir = os.path.abspath(os.path.dirname(__file__))

def setup_schema(Base, session):
	# Create a function which incorporates the Base and session information
	def setup_schema_fn():
		for class_ in Base._decl_class_registry.values():
			if hasattr(class_, '__tablename__'):
				if class_.__name__.endswith('Schema'):
					raise ModelConversionError(
						"For safety, setup_schema can not be used when a"
						"Model class ends with 'Schema'"
						)

				class Meta(object):
					model = class_
					sqla_session = session

				schema_class_name = '%sSchema' % class_.__name__
				

				schema_class = type(
					schema_class_name,
					(ma.ModelSchema,),
					{'Meta': Meta}
					)

				setattr(class_, '__marshmallow__', schema_class)

	return setup_schema_fn

app = Flask(__name__)


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SECRET_KEY'] = 'shadowfox'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_ROOT, 'static','uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

mail= Mail(app)

app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'tomasmuller.ab@gmail.com'
app.config['MAIL_PASSWORD'] = 'admin2642'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True


mail = Mail(app)

db = SQLAlchemy(app)
ma = Marshmallow()
db.init_app(app)
ma.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
CORS(app)

class Recommendation(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'))
  recommended_by = db.Column(db.String(128),nullable=False)
  recommender_id = db.Column(db.String(255),default="no url found")
  movie_title = db.Column(db.String(255))
  description = db.Column(db.Text)
  recommended = db.Column(db.Boolean, default=False)
  accepted = db.Column(db.Boolean, default=False)
  image = db.Column(db.Text)


class RecommendationSchema(ma.ModelSchema):
    class Meta:
        model = Recommendation
        fields = ('id','movie_title','recommended_by','recommender_id','description','accepted','recommended','image')

class Movie(db.Model):
	__searchable__ = ['genre']
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(200))
	timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	username = db.Column(db.String(255))
	description = db.Column(db.String(100))
	genre = db.Column(db.String(50))
	image = db.Column(db.String(50))
	recommendation = db.relationship('Recommendation', backref="movies", cascade="all, delete-orphan" , lazy='dynamic')

class MovieSchema(ma.ModelSchema):
    class Meta:
        model = Movie
        fields = ("id","name","timestamp","username","description","genre","image","recommendation")
    recommendation = ma.Nested(RecommendationSchema, many=True)


movie_schema = MovieSchema()
movies_schema = MovieSchema(many=True)

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class User(db.Model,UserMixin):

    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    movies = db.relationship('Movie', backref='author', lazy='dynamic')

    def get_id(self):
        return str(self.id)

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode({'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)

class UserSchema(ma.ModelSchema):
    class Meta:
        model = User
        fields = ("id", "username", "email","movies")
    movies = ma.Nested(MovieSchema, many=True)

user_schema = UserSchema()
users_schema = UserSchema(many=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def hello():
	# return 'sqlite:///' + os.path.join(basedir, 'app.db')
    return render_template('popo/index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
	if current_user.is_authenticated:
		return render_template('popo/login.html')
	form = RegistrationForm()
	if form.validate_on_submit():
		try:
			user = User(username=form.username.data, email=form.email.data)
			user.set_password(form.password.data)
			db.session.add(user)
			db.session.commit()
			flash("Congrats you are registered.")
			return render_template('popo/index.html')
		except:
			return render_template('register.html', form=form,error="username or email already been used please use another")		
	return render_template('register.html', form=form,error="")

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template('popo/index.html',errorUser="wrong username or password")
        isValidPassword = user.check_password(password)
        if not isValidPassword:
             return render_template('popo/index.html',errorUser="wrong password")
        login_user(user)
        return render_template('popo/login.html')
    return render_template('popo/index.html')

@app.route('/user/<username>', methods=['GET'])
@login_required
def user(username):	
	user = User.query.filter_by(username=username).first_or_404()
	return render_template('popo/user-profile.html', user=user)
# IGQVJYekxxbmJXMFAySHpWWWluUUNkU24zUXlQNTZAGTHR5b2JPdG5ITVdyVXIxNm1OVVBEWGgtb09FLUVNYVl2aGVtRGt4Mkdpbl9XRklTcEJIRHdLa0h2ckFVMER0S3h6c1lVODNQZADJzZADJabkJveQZDZD
@app.route('/instagram', methods=['GET'])
def instagram():	
	token="IGQVJYekxxbmJXMFAySHpWWWluUUNkU24zUXlQNTZAGTHR5b2JPdG5ITVdyVXIxNm1OVVBEWGgtb09FLUVNYVl2aGVtRGt4Mkdpbl9XRklTcEJIRHdLa0h2ckFVMER0S3h6c1lVODNQZADJzZADJabkJveQZDZD"
	# link2="https://graph.instagram.com/me?fields=id,username&access_token="+token
	link="https://graph.instagram.com/me/media?fields=permalink,media_url&access_token="+token
	r = requests.get(link, timeout=15)
	return r.json()
@app.route('/explore', methods=['GET'])
@login_required
def page3():	
	return render_template('popo/login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return render_template('popo/index.html')



@app.errorhandler(404)
def not_found_error(error):
	return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
	db.session.rollback()
	return render_template('500.html'), 500



@app.route('/ask_for_movie_recommendation', methods=['POST'])
def ask_for_movie_recommendation():
	post_data = request.get_json() or request.form
	mg = post_data['movie_genre']
	mn = post_data['movie_name']
	md = post_data['movie_description']
	mm = None
	# if request.files:
	# 	mm = request.files['movie_image']
	imagename=post_data['movie_image']
	# if mm:
	# 	imagename = secure_filename(mm.filename)
	# 	mm.save(os.path.join(app.config['UPLOAD_FOLDER'], imagename))	
	ui = post_data['user_name']
	user = User.query.filter_by(username=ui).first()
	post = Movie(name=mn, description=md, genre=mg, image=imagename, user_id=user.id, username=ui)
	db.session.add(post)
	db.session.commit()
	data = get_update_movies(ui)
	print(data)
	return data

@app.route('/accept_recommendation/', methods=['POST'])
def accept_recommendation():
	data = request.get_json()
	rec_id = data['id']
	rec=Recommendation.query.filter_by(id=rec_id).first() 
	rec.accepted = True
	rec.recommended = True
	db.session.commit()
	return "accepted"

@app.route('/delete_post/', methods=['POST'])
def delete_post():
	data = request.get_json()
	_id = data['id']
	rec=Movie.query.filter_by(id=_id).first()
	db.session.delete(rec)
	db.session.commit()
	return "deleted"

@app.route('/reject_recommendation/', methods=['POST'])
def reject_recommendation():
	data = request.get_json()
	_id = data['id']
	rec=Recommendation.query.filter_by(id=_id).first()
	rec.recommended=True
	db.session.delete(rec)
	db.session.commit()
	return "deleted"

@app.route('/get_my_movies', methods=['POST'])
def get_my_movies():
	response_object = {'status': 'success'}
	param = request.get_json()
	user = param['user']
	movi = User.query.filter_by(username=user).first()
	user_schema = UserSchema()
	result = user_schema.dump(movi).data
	response_object['books'] = result
	return jsonify(response_object)


def get_update_movies(user):
	print('get update called')
	response_object = {'status': 'success'}
	param = request.get_json()
	user = user
	movi = User.query.filter_by(username=user).first()
	user_schema = UserSchema()
	result = user_schema.dump(movi).data
	response_object['books'] = result
	return jsonify(response_object)

@app.route('/get_all_movies', methods=['GET'])
def get_all_movies():
	response_object = {'status': 'success'}
	movi = Movie.query.order_by(Movie.id.desc()).all()
	if request.args.get("user_id"):
		movi=Movie.query.order_by(Movie.id.desc()).filter_by(user_id=request.args.get("user_id"))
	rec = User.query.all()
	rr = Recommendation.query.all()
	movie_schema = MovieSchema(many=True)
	gs = users_schema.dump(rec).data
	result = movies_schema.dump(movi).data
	response_object['books'] = result
	return jsonify(response_object)

@app.route('/get_by_genre', methods=['GET'])
def get_by_genre():
	response_object = {'status': 'success'}
	genre = request.args.get('genre', '')
	movi = Movie.query.filter_by(genre=genre)
	movie_schema = MovieSchema(many=True)
	result = movies_schema.dump(movi).data
	response_object['books'] = result
	return jsonify(response_object)

@app.route('/recommend_movie', methods=['POST'] )
def recommend_movie():
	param = request.get_json()
	movie_id = param['movie_id']
	recommended_by = param['recommender_name']
	movie_title = param['movie_recommendation']
	description = param['movie_description'] if param['movie_description'] else ""
	image = param['image'] if param["image"] else None
	user_id = User.query.filter_by(username=recommended_by).first()
	movie=Movie.query.get(movie_id)
	rec=Recommendation(movie_id=movie_id,recommended_by=recommended_by,recommender_id=user_id.id,movie_title=movie_title,description=description,image=image)
	movie.recommendation.append(rec)
	db.session.add(movie)
	db.session.commit()
	return "recommendation was sent to user"

# Reset links

@app.route('/reset')
def reset():
    return render_template('reset.html')


@app.route('/send_pass/', methods = ['POST','GET'])
def send_pass():
    if request.method =='POST':
        print("In POst")
        var={}
        for i,j in zip(request.form.keys(),request.form.values()):
            var[i]=j
        print(var)
        conn = sqlite3.connect('app.db')
        cur = conn.cursor()
        cur.execute('SELECT * from user WHERE email="{}"'.format(var['email']))
        data = pd.DataFrame(cur.fetchall())
        if len(data)<1:
                   return "* Wrong email"
        msg = Message('Password Reset', sender = 'ticketdropper23@gmail.com', recipients = [var['email']])
        
        rand_token = str(uuid4())
        session['token'] = rand_token
        
        print(session['token'])
        url = 'http://127.0.0.1:5000'+ url_for('reset_password',email=var['email'],token=rand_token)
        print('url:', url)
        msg.html = render_template('reset_password.html', username=var['email'], link=url)
        #msg.html = render_template('reset_password.html', username=var['email'], link=url_for('reset_password',email=var['email'],token=rand_token))

        
        mail.send(msg)
        return "Password was sent to your email"

@app.route('/reset_password/', methods=['GET',"POST"])
def reset_password():
    email = request.args.get('email')
    token = request.args.get('token')
    
    if session['token'] == token:
        if request.method == 'POST':
            var={}
            for i,j in zip(request.form.keys(),request.form.values()):
                var[i]=j
            print(var)
            conn = sqlite3.connect('app.db')
            cur = conn.cursor()
            cur.execute('UPDATE user SET password="{}" WHERE email = "{}"'.format(generate_password_hash(var['new_password']), email))
            # To reset the pass db
            conn.commit()
            conn.close()
            # To reset the pass db
            
            return redirect(url_for('clear'))
        return render_template('new_password.html')
@app.route('/clear/')
def clear():
    session.clear()
    try:
        print('session',session['token'])
    except:
        pass
    return redirect(url_for('hello'))

if __name__=='__main__':
    app.run(debug=False)




@login_manager.unauthorized_handler
def unauthorized():
	return redirect('/login')



if __name__ == "__main__":
  db.create_all()
  app.run(debug=True,host='0.0.0.0')
#   app.run()