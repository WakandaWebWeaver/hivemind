from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
import boto3
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import datetime
import json
from better_profanity import profanity
import random
import scan
import platform
import time
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy import Spotify
import random
from urllib import parse, request as urllib_request
from cryptography.fernet import Fernet
from flask_mail import Mail, Message

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
login_manager = LoginManager(app)


giphy_url = "http://api.giphy.com/v1/gifs/search"


key = os.getenv("FERNET_KEY").encode()
f = Fernet(key)


def encrypt(data):
    data = data.encode()
    encrypted = f.encrypt(data)
    return encrypted


def decrypt(data):
    decrypted = f.decrypt(data)
    return decrypted


# AWS S3 configuration
s3_access_key = os.getenv("AWS_ACCESS_KEY_ID")
s3_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
s3_bucket_name = os.getenv("AWS_BUCKET_NAME")


giphy_api_key = os.getenv("GIPHY_API_KEY")
grec_sitekey = os.getenv("GREC_SITEKEY")

# Connect to AWS S3
s3 = boto3.client('s3', aws_access_key_id=s3_access_key,
                  aws_secret_access_key=s3_secret_key)

app.config['MONGO_URI'] = os.getenv('MONGO_URI')

mongo = MongoClient(app.config['MONGO_URI'])
db_name = os.getenv('MONGO_DB_NAME')
db = mongo[db_name]

user_collection = db['users']
posts_collection = db['posts']
blacklist_collection = db['blacklist']
rooms_collection = db['rooms']
applications_collection = db['applications']
colleges_collection = db['colleges']
errors_collection = db['errors']
notes_collection = db['notes']


# User class for Flask-Login
class User(UserMixin):
    pass


@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.id = user_id
    return user


@app.route('/')
def index():
    return render_template('index.html',
                           session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, user=User
                           )


@app.errorhandler(Exception)
def error_page(e):
    if errors_collection.count_documents({}) > 30:
        errors_collection.drop()

    error = {
        'error': str(e),
        'date': datetime.datetime.now().strftime("%Y-%m-%D %H:%M"),
        'trigger url': request.url,
        'method': request.method,
        'complete request': f'{request.method} {request.url}',
        'client': request.headers.get('User-Agent'),
        'headers': dict(request.headers),
        'ip': request.remote_addr
    }
    errors_collection.insert_one(error)
    return render_template('error.html')


content_placeholders = [
    "time travel is real",
    "aliens are real",
    "what's on your mind?",
    "what's your favorite color?",
    "what's the tea?",
    "what's your favorite movie?",
    "type 'song: ' to make a song post",
    "type 'gif: ' to make a gif post",
    "Got a fun image to share?",
    "What's your favorite book?",
    "Been to any cool places lately?",
    "HELP ME",
    "i Am TrApPeD iN tHe InTeRnEt",
    "i aM a RoBoT",
    "erm what the sigma 🤓",
    "i am a bot, beep boop",
    "skibidi bop",
    "for real? 🤨 Just like that? 🤨🤨",
    "pls dont upload bad stuff",
    "all hail the mighty bot",
    "if you post bad stuff, you will be banned",
    "i am a bot, but i have feelings too",
    "mission: steal the homeless man's dog",
]


@app.route('/debug')
@login_required
def debug():
    if session['name'] != "Esvin Joshua" or session['id'] != "esvinjoshua":
        return redirect(url_for('index'))

    user_info = user_collection.find()
    s3_files = s3.list_objects_v2(Bucket=s3_bucket_name)['Contents']
    username = session['id']
    os_info = platform.system()
    release = platform.release()
    version = platform.version()
    currenttime = datetime.datetime.now().strftime("%I:%M:%S %p")
    timezone = time.tzname[1]
    current_dir = os.getcwd()
    files = os.listdir()

    folders = []

    # If there are any folders, navigate them and list their contents
    for file in files:
        if os.path.isdir(file):
            folder_data = {
                'folder': file,
                'contents': os.listdir(file)
            }
            folders.append(folder_data)

    return render_template('debug.html', user_info=user_info, s3_files=s3_files,
                           session=session, os_info=os_info, release=release, version=version, currenttime=currenttime,
                           username=username,
                           current_dir=current_dir, bucket_name=s3_bucket_name,
                           files=files,
                           folders=folders,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           url=f"https://{s3_bucket_name}.s3.amazonaws.com/", timezone=timezone
                           )


@app.route('/admin/<action>/<keyword>', methods=['POST', 'GET'])
@login_required
def admin(action, keyword):
    if session['name'] != "Esvin Joshua" or session['id'] != "esvinjoshua":
        return redirect(url_for('index'))

    user = user_collection.find_one({'username': keyword})

    if action == 'verify':
        user['verified'] = True
        user_collection.update_one({'username': keyword}, {'$set': user})
    elif action == 'unverify':
        user['verified'] = False
        user_collection.update_one({'username': keyword}, {'$set': user})
    elif action == 'blacklist':
        user['blacklist'] = True
        user['warnings'] = 4
        user_collection.update_one({'username': keyword}, {'$set': user})
        blacklist_collection.insert_one(
            {'username': keyword, 'reason': 'Blacklist by Admin'})
    elif action == 'unblacklist':
        user['blacklist'] = False
        user['warnings'] = 0
        user_collection.update_one({'username': keyword}, {'$set': user})
        blacklist_collection.delete_one({'username': keyword})
    elif action == 'delete':
        user_collection.delete_one({'username': keyword})
        posts_collection.delete_many({'username': keyword})
    elif action == 'delete_file':
        file_folder = keyword.split('_')[0]
        file_name = keyword.split('_')[1]
        file_key = f"{file_folder}/{file_name}"
        s3.delete_object(Bucket=s3_bucket_name, Key=file_key)
    elif action == 'rename_file':
        file_folder = keyword.split('_')[0]
        file_name = keyword.split('_')[1]
        new_name = keyword.split('_')[2]
        file_key = f"{file_folder}/{file_name}"
        new_key = f"{file_folder}/{new_name}"
        # s3.copy_object(Bucket=s3_bucket_name, CopySource=f"{s3_bucket_name}/{file_key}",
        #                Key=new_key)
        # s3.delete_object(Bucket=s3_bucket_name, Key=file_key)
        print(file_key, new_key)

    return {'success': True}


@app.route('/edit_user/<username>', methods=['POST'])
@login_required
def edit_user(username):
    blacklist = blacklist_collection.find_one({'username': username})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    user = user_collection.find_one({'username': username})
    user['full_name'] = request.form.get('full_name') if request.form.get(
        'full_name') else user['full_name']
    user['phone_number'] = request.form.get('phone_number') if request.form.get(
        'phone_number') else user['phone_number']
    user['roll_number'] = request.form.get('roll_number') if request.form.get(
        'roll_number') else user['roll_number']
    user['college_name'] = request.form.get('college_name') if request.form.get(
        'college_name') else user['college_name']
    user['password'] = request.form.get('password') if request.form.get(
        'password') else user['password']
    user['username'] = request.form.get('username') if request.form.get(
        'username') else user['username']

    user_collection.update_one({'username': username}, {'$set': user})

    return {'success': True}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']

            user = user_collection.find_one(
                {'username': username})
            blacklist = blacklist_collection.find_one({'username': username})

            if blacklist:
                return render_template('blacklist.html', blacklist=blacklist)

            if user:

                if user['username'] == username and decrypt(user['password']).decode() == password:
                    user_obj = User()
                    user_obj.id = username
                    login_user(user_obj)
                    session['name'] = user['full_name']
                    session['id'] = user['username']
                    session['profile_picture'] = user['profile_picture_s3_key']
                    session['default_profile_picture'] = 'Profile pictures/avatar_default.jpeg'
                    session['college_name'] = user['college_name']
                    session['ht_number'] = user['roll_number']

                    return redirect(url_for('dashboard',
                                            session=session,
                                            profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                                'profile_picture') else None,
                                            builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                            user=user_collection.find_one(
                                                {'username': session['id']})
                                            ))
        except Exception as e:
            print(e)
            return render_template('error.html')

        else:
            return 'Invalid username or password'

    return render_template('login.html', grec_sitekey=grec_sitekey)


@app.route('/create_user', methods=['POST'])
def create_user():
    college = request.json.get('college_name')
    full_name = request.json.get('full_name')
    phone_number = request.json.get('phone_number')
    roll_number = request.json.get('roll_number')
    password = request.json.get('password')
    username = request.json.get('username').strip().lower()
    college_name = request.json.get('college_name').lower()
    country_code = request.json.get('country_code')
    default_pfp = request.json.get('default_pfp')
    year_of_study = request.json.get('year_of_study')
    security_question = request.json.get('security_question')
    security_answer = request.json.get('security_answer')
    email = request.json.get('email')
    gender = request.json.get('gender')

    college = colleges_collection.find_one(
        {'college_name': college_name.lower()})

    if college:
        college['user_count'] = college.get('user_count', 0) + 1
        colleges_collection.update_one(
            {'college_name': college_name}, {'$set': college})
        pass
    else:
        colleges_collection.insert_one({'college_name': college_name})
        college['user_count'] = college.get('user_count', 0) + 1
        colleges_collection.update_one(
            {'college_name': college_name}, {'$set': college})

    user = user_collection.find_one({'username': username})

    if user:
        return {'is_exists': True}

    if request.files:
        profile_picture = request.files['profile_picture']
        if profile_picture.filename != '':
            file_key = f"Profile pictures/{username.lower()}.jpeg"
            job = s3.upload_fileobj(
                profile_picture, s3_bucket_name, file_key)

            if job:
                print('Profile picture uploaded successfully')

            profile_picture_s3_key = file_key
        else:
            profile_picture_s3_key = f"Profile pictures/{default_pfp}" if default_pfp != "" else "Profile pictures/avatar_default.jpeg"
    else:
        profile_picture_s3_key = f"Profile pictures/{default_pfp}" if default_pfp != "" else "Profile pictures/avatar_default.jpeg"

    user_data = {
        'full_name': full_name,
        'gender': gender,
        'phone_number': country_code + ' ' + phone_number,
        'email': email,
        'roll_number': roll_number,
        'profile_picture_s3_key': profile_picture_s3_key,
        'password': encrypt(password),
        'security_question': security_question,
        'security_answer': security_answer,
        'username': username,
        'verified': False,
        'college_name': college_name,
        'year_of_study': year_of_study,
        'following': [],
        'followers': [],
        'blacklist': False,
        'warnings': 0,
    }

    user_collection.insert_one(user_data)
    user = user_collection.find_one({'username': username})

    user['badges'] = user.get('badges', [])
    user['badges'].append('Welcome aboard: Make a HiveMind account')

    session['name'] = user['full_name']
    session['id'] = user['username']
    session['profile_picture'] = user['profile_picture_s3_key']
    session['default_profile_picture'] = 'Profile pictures/avatar_default.jpeg'
    session['college_name'] = user['college_name']
    session['ht_number'] = user['roll_number']

    user_obj = User()
    user_obj.id = username
    login_user(user_obj)

    return {'success': True}


@app.route('/register', methods=['GET', 'POST'])
def register():
    return render_template('register.html', grec_sitekey=grec_sitekey)


@app.route('/upload_material_page')
@login_required
def upload_material_page():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    return render_template('add_material.html', session=session, grec_sitekey=grec_sitekey,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/upload_material', methods=['POST'])
@login_required
def upload_material():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    if request.files:
        year = request.form.get('year')
        material = request.files['material_file']

        if material.filename != '':
            file_key = f"materials/{material.filename}.pdf"
            job = s3.upload_fileobj(material, s3_bucket_name, file_key,
                                    ExtraArgs={'Metadata': {'year': year, 'college': session['college_name']}})

            return {'success': True} if job else {'success': False}

    return redirect(url_for('materials'))


@app.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))


@app.route('/materials')
def materials():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    materials = []
    response = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix='materials/')
    for item in response.get('Contents', []):
        key = item['Key']
        if key.endswith('.pdf'):
            title = os.path.basename(key)
            metadata_response = s3.head_object(Bucket=s3_bucket_name, Key=key)
            year = metadata_response['ResponseMetadata']['HTTPHeaders']['x-amz-meta-year']
            college_name = metadata_response['ResponseMetadata']['HTTPHeaders']['x-amz-meta-college']
            if college_name == session['college_name']:
                materials.append({'title': title, 'year': int(year)})

    return render_template('materials.html', materials=materials, session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None)


@app.route('/error')
def error():
    return render_template('error.html')


@app.route('/block_user', methods=['POST'])
@login_required
def block_user():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    username_to_block = request.form.get('username')
    current_user_id = session['id']

    current_user = user_collection.find_one({'username': current_user_id})
    if current_user:
        if 'blocked' not in current_user:
            current_user['blocked'] = []
        current_user['blocked'].append(username_to_block)
        user_collection.update_one({'username': current_user_id}, {
                                   '$set': current_user})

    user_to_block = user_collection.find_one({'username': username_to_block})
    if user_to_block:
        if 'blocked_by' not in user_to_block:
            user_to_block['blocked_by'] = []
        user_to_block['blocked_by'].append(current_user_id)
        user_collection.update_one({'username': username_to_block}, {
                                   '$set': user_to_block})

    return redirect(url_for('profile', username=username_to_block))


@app.route('/unblock_user', methods=['POST'])
@login_required
def unblock_user():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    username_to_unblock = request.form.get('username')
    current_user_id = session['id']

    current_user = user_collection.find_one({'username': current_user_id})
    if current_user and 'blocked' in current_user:
        if username_to_unblock in current_user['blocked']:
            current_user['blocked'].remove(username_to_unblock)
            user_collection.update_one({'username': current_user_id}, {
                                       '$set': current_user})

    user_to_unblock = user_collection.find_one(
        {'username': username_to_unblock})
    if user_to_unblock and 'blocked_by' in user_to_unblock:
        if current_user_id in user_to_unblock['blocked_by']:
            user_to_unblock['blocked_by'].remove(current_user_id)
            user_collection.update_one({'username': username_to_unblock}, {
                                       '$set': user_to_unblock})

    return redirect(url_for('profile', username=username_to_unblock))


@app.route('/download', methods=['POST', 'GET'])
def download():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    filename = request.args.get('filename')

    file_url = f"https://{s3_bucket_name}.s3.amazonaws.com/materials/{filename}"
    return redirect(file_url)


@app.route('/tos_prp')
def tos_prp():

    return render_template('tos_prp.html')


@app.route('/create_post', methods=['POST', 'GET'])
@login_required
def create_post():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    title = request.form.get('post_title')
    content = request.form.get('post_text')
    post_picture = request.files['post_image']
    author = session['name']
    user = user_collection.find_one({'full_name': author})
    date = datetime.date.today().strftime("%d/%m/%y")
    time = datetime.datetime.now().strftime("%H:%M")

    posts = posts_collection.find()
    randomNum = random.randint(1, 999999)
    post_id = posts_collection.count_documents(
        {}) + 1 + user.get('post_count', 0) + int(datetime.date.today().strftime("%d%m%y")) + randomNum

    for post in posts:
        if post['post_id'] == post_id:
            randomNum = random.randint(1, 999999)
            post_id = posts_collection.count_documents(
                {}) + 1 + user.get('post_count', 0) + int(datetime.date.today().strftime("%d%m%y")) + randomNum
        else:
            break

    profile_picture = session['profile_picture']
    post_image_s3_key = ''
    contains_image = False

    if request.form.get('embed_url') is not None or request.form.get('embed_url') != '':
        pass

    if user['verified'] == False:
        return redirect(url_for('verify_id_page'))

    if profanity.contains_profanity(content) or profanity.contains_profanity(title):
        if user['warnings'] > 3:
            user['blacklist'] = True
            blacklist_collection.insert_one({'title': title,
                                            'content': content,
                                             'author': author,
                                             'username': session['id'],
                                             'profile_picture': profile_picture,
                                             'date': date,
                                             'time': time,
                                             'post_id': post_id,
                                             'reason': 'Profanity while making a post.',
                                             'college_name': session['college_name']
                                             })
            logout_user()
            return {'profanity': True}
        user['warnings'] = user.get('warnings', 0) + 1
        user_collection.update_one({'full_name': author}, {'$set': user})
        return {'warning': True}

    if post_picture:
        contains_image = True
        post_image = request.files['post_image']
        if post_image.filename != '':
            file_key = f"Post images/{post_id}.jpeg"
            job = s3.upload_fileobj(post_image, s3_bucket_name, file_key)
            if job:
                print('Post image uploaded successfully')

            post_image_s3_key = file_key

            img = s3.get_object(Bucket=s3_bucket_name,
                                Key=file_key)

            image_size = str(img['ContentLength'] / 1024)

        if scan.check_image_for_profanity(post_image_s3_key):
            blacklist_collection.insert_one({'title': title,
                                             'content': content,
                                             'author': author,
                                             'username': session['id'],
                                             'profile_picture': profile_picture,
                                             'date': date,
                                             'time': time,
                                             'post_id': post_id,
                                             'contains_image': contains_image,
                                             'post_image': post_image_s3_key if contains_image else None,
                                             'reason': 'Profanity while making a post.',
                                             'college_name': session['college_name']
                                             })

            s3.delete_object(Bucket=s3_bucket_name, Key=post_image_s3_key)

            logout_user()
            return {'profanity': True}

    anonymous = False
    if 'anonymous' in request.form:
        anonymous = True

    post_data = {
        'title': title,
        'content': content,
        'author': author,
        'username': session['id'],
        'profile_picture': profile_picture if not anonymous else 'Profile pictures/avatar_default.jpeg',
        'date': date,
        'post_id': post_id,
        'song_url': '',
        'contains_image': contains_image,
        'post_image': post_image_s3_key,
        'image_size': image_size[0:6] + " KB" if contains_image else None,
        'anonymous': anonymous,
        'college_name': session['college_name']
    }

    user['post_count'] = user.get('post_count', 0) + 1
    user_collection.update_one({'full_name': author}, {'$set': user})

    user['posts'] = user.get('posts', [])
    user['posts'].append(post_id)
    user_collection.update_one({'full_name': author}, {'$set': user})

    posts_collection.insert_one(post_data)

    return {'success': True}


@app.route('/add_song_to_post', methods=['POST'])
@login_required
def add_song_to_post():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    song_url = request.json.get('song_url')

    author = session['name']
    user = user_collection.find_one({'full_name': author})
    date = datetime.date.today().strftime("%d/%m/%y")

    posts = posts_collection.find()
    randomNum = random.randint(1, 999999)
    post_id = posts_collection.count_documents(
        {}) + 1 + user.get('post_count', 0) + int(datetime.date.today().strftime("%d%m%y")) + randomNum

    for post in posts:
        if post['post_id'] == post_id:
            randomNum = random.randint(1, 999999)
            post_id = posts_collection.count_documents(
                {}) + 1 + user.get('post_count', 0) + int(datetime.date.today().strftime("%d%m%y")) + randomNum
        else:
            break
    date = datetime.date.today().strftime("%d/%m/%y")
    profile_picture = session['profile_picture']

    post_data = {
        'title': request.json.get('title') if request.json.get('title') else '',
        'content': '',
        'author': author,
        'username': session['id'],
        'profile_picture': profile_picture,
        'date': date,
        'post_id': post_id,
        'contains_image': False,
        'post_image': None,
        'song_url': f"https://open.spotify.com/embed/track/{song_url}",
        'anonymous': False,
        'college_name': session['college_name']
    }

    user['post_count'] = user.get('post_count', 0) + 1
    user['posts'] = user.get('posts', []) + [post_id]
    user_collection.update_one({'full_name': author}, {'$set': user})
    posts_collection.insert_one(post_data)

    return {'success': True}


@app.route('/add_song', methods=['POST'])
@login_required
def add_song():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    song_url = request.json.get('embed_url')
    user = user_collection.find_one({'username': session['id']})
    user['profile_song'] = f"https://open.spotify.com/embed/track/{song_url}"

    user_collection.update_one({'username': session['id']}, {'$set': user})

    return {'success': True}


@app.route('/search_gif', methods=['POST'])
@login_required
def search_gif():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    search_query = request.json.get('search_query')

    params = parse.urlencode({
        "q": search_query,
        "api_key": giphy_api_key,
        "limit": "5"
    })

    with urllib_request.urlopen("".join((giphy_url, "?", params))) as response:
        data = json.loads(response.read())

    gifs = []
    for gif in data['data']:
        gif_data = {
            'url': gif['images']['original']['url'],
            'title': gif['title'],
            'optimized_url': gif['images']['preview_gif']['url']
        }
        gifs.append(gif_data)

    return {'gifs': gifs}


@app.route('/add_gif_to_post', methods=['POST'])
@login_required
def add_gif_to_post():
    gif_url = request.json.get('url')
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    author = session['name']
    user = user_collection.find_one({'full_name': author})
    date = datetime.date.today().strftime("%d/%m/%y")
    posts = posts_collection.find()
    randomNum = random.randint(1, 999999)
    post_id = posts_collection.count_documents(
        {}) + 1 + user.get('post_count', 0) + int(datetime.date.today().strftime("%d%m%y")) + randomNum

    for post in posts:
        if post['post_id'] == post_id:
            randomNum = random.randint(1, 999999)
            post_id = posts_collection.count_documents(
                {}) + 1 + user.get('post_count', 0) + int(datetime.date.today().strftime("%d%m%y")) + randomNum
        else:
            break

    date = datetime.date.today().strftime("%d/%m/%y")

    post_data = {
        'title': request.json.get('title') if request.json.get('title') else '',
        'content': '',
        'author': author,
        'username': session['id'],
        'profile_picture': session['profile_picture'],
        'date': date,
        'post_id': post_id,
        'contains_image': False,
        'post_image': None,
        'gif_url': gif_url,
        'anonymous': False,
        'college_name': session['college_name']
    }
    posts_collection.insert_one(post_data)

    user['post_count'] = user.get('post_count', 0) + 1
    user['posts'] = user.get('posts', []) + [post_id]
    user_collection.update_one({'full_name': author}, {'$set': user})

    return {'success': True}


@app.route('/search_song', methods=['POST'])
@login_required
def search_song():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=os.getenv('SPOTIFY_CLIENT_ID'),
        client_secret=os.getenv('SPOTIFY_CLIENT_SECRET')
    ))

    song_name = request.json.get('search_query')

    results = sp.search(q=song_name, limit=3)

    songs = []
    for song in results['tracks']['items']:
        song_data = {
            'song_name': song['name'],
            'artist_name': song['artists'][0]['name'],
            'album_name': song['album']['name'],
            'album_image': song['album']['images'][0]['url'],
            'embed_url': song['external_urls']['spotify']
        }
        songs.append(song_data)

    return {'songs': songs}


@app.route('/delete_comment', methods=['POST'])
@login_required
def delete_comment():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    comment = request.form.get('comment')
    author = request.form.get('comment_author')
    posts = posts_collection.find()

    for post in posts:
        if 'comments' in post:
            for c in post['comments']:
                if c['comment'] == comment and c['author'] == author:
                    post['comments'].remove(c)
                    posts_collection.update_one(
                        {'post_id': post['post_id']}, {'$set': post})

    return redirect(url_for('view_posts'))


@app.route('/hive_comment', methods=['POST'])
@login_required
def hive_comment():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    user = user_collection.find_one({'username': author})

    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': room_id})
    posts = room['posts']

    if profanity.contains_profanity(comment):
        if user['warnings'] > 3:
            blacklist_collection.insert_one({'post_id': post_id,
                                            'comment': comment,
                                             'author': author,
                                             'username': session['id'],
                                             'date': date,
                                             'reason': 'Profanity while making comment',
                                             'college_name': session['college_name']
                                             })
        return 'Profanity is not allowed.'

    for post in posts:
        if post['post_id'] == post_id:
            post['comments'] = post.get('comments', [])
            post['comments'].append({
                'comment': comment,
                'author': author,
                'date': date,
                'college_name': session['college_name']
            })
            rooms_collection.update_one({'room_id': room_id}, {'$set': room})
            return redirect(url_for('hive_room', room_id=room_id, session=session,
                                    builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                    profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                        'profile_picture') else None, ))
    return 'Post not found'


@app.route('/comment', methods=['POST'])
@login_required
def comment():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = session['name']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    user = user_collection.find_one({'username': session['id']})

    post = posts_collection.find_one({'post_id': int(post_id)})

    if profanity.contains_profanity(comment):
        if user['warnings'] > 3:
            blacklist_collection.insert_one({'post_id': post_id,
                                            'comment': comment,
                                             'author': author,
                                             'username': session['id'],
                                             'date': date,
                                             'reason': 'Profanity while making comment',
                                             'college_name': session['college_name']
                                             })
        return 'Profanity is not allowed'

    if post:
        if 'comments' in post:
            post['comments'].append({
                'comment': comment,
                'author': author,
            })

            post_author = user_collection.find_one(
                {'username': post['username']})
            notification = {
                'message': 'A comment has been made on your post by ' + session['name'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one(
                {'username': post['username']}, {'$set': post_author})

        else:
            post['comments'] = [{
                'comment': comment,
                'author': author
            }]

            post_author = user_collection.find_one(
                {'username': post['username']})
            notification = {
                'message': 'A comment has been made on your post by ' + session['name'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one(
                {'username': post['username']}, {'$set': post_author})
        posts_collection.update_one({'post_id': int(post_id)}, {'$set': post})

    return redirect(url_for('view_posts'))


@app.route('/dashboard')
@login_required
def dashboard():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    college = colleges_collection.find_one(
        {'college_name': session['college_name']})

    if college['user_count'] < 10:
        message = "It's a bit lonely here. Why not invite some friends to join?"
    else:
        message = None

    return render_template('dashboard.html',
                           session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           college=college, message=message, user=user_collection.find_one(
                               {'username': session['id']})
                           )


@app.route('/hive_post_comment', methods=['POST'])
@login_required
def hive_post_comment():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    user = user_collection.find_one({'username': author})

    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': room_id})

    posts = room['posts']

    if profanity.contains_profanity(comment):
        if user['warnings'] > 3:
            blacklist_collection.insert_one({'post_id': post_id,
                                            'comment': comment,
                                             'author': author,
                                             'username': session['id'],
                                             'date': date,
                                             'reason': 'Profanity while making comment',
                                             'college_name': session['college_name']
                                             })
        return 'Profanity is not allowed'

    for post in posts:
        if post['post_id'] == post_id:
            post['comments'] = post.get('comments', [])
            post['comments'].append({
                'comment': comment,
                'author': author,
                'date': date,
                'college_name': session['college_name']
            })
            rooms_collection.update_one({'room_id': room_id}, {'$set': room})
            post_author = user_collection.find_one(
                {'username': post['username']})
            notification = {

                'message': 'A comment has been made on your post by ' + session['name'] + 'on your post: ' + post[
                    'date'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one(
                {'username': post['username']}, {'$set': post_author})
            return redirect(url_for('hive_room', room_id=room_id, session=session,
                                    builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                    profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                        'profile_picture') else None, ))
    return 'Post not found'


@app.route('/delete_hive_comment', methods=['POST'])
@login_required
def delete_hive_comment():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = request.form.get('comment_author')
    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': room_id})
    posts = room['posts']

    for post in posts:
        if post['post_id'] == post_id:
            for c in post['comments']:
                if c['comment'] == comment and c['author'] == author:
                    post['comments'].remove(c)
                    rooms_collection.update_one(
                        {'room_id': room_id}, {'$set': room})
                    return redirect(url_for('hive_room', room_id=room_id, session=session,
                                            builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                            profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                                'profile_picture') else None, ))
    return 'Comment not found'


@app.route('/posts')
@login_required
def view_posts():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    if session.get('id') is None:
        return redirect(url_for('login'))

    posts = posts_collection.find()

    user_posts = []

    for post in posts:
        if post['anonymous']:
            post['author'] = 'Anonymous'
        if post['college_name'] == session['college_name']:
            user_posts.append(post)

    sorted_posts = sorted(user_posts, key=lambda x: x['_id'], reverse=True)

    return render_template('posts.html', posts=sorted_posts,
                           session=session,
                           user=user_collection.find_one(
                               {'username': session['id']}),
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           content_placeholder=random.choice(
                               content_placeholders),
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/serve_post/<post_id>', methods=['GET', 'POST'])
@login_required
def serve_post(post_id):
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post = posts_collection.find_one({'post_id': int(post_id)})
    user = user_collection.find_one({'username': session['id']})

    return render_template('post.html', post=post, session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/", user=user,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/Diary')
@login_required
def Diary():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    notes = notes_collection.find({'author': session['name']})

    return render_template('Diary.html', session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, notes=notes if notes else None
                           )


@app.route('/note', methods=['POST'])
@login_required
def note():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    content = request.form.get('note_content')
    title = request.form.get('note_title')
    note_id = notes_collection.count_documents(
        {}) + 1 + int(date[0]) + random.randint(1, 1000)
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    author = session['name']

    note_data = {
        'content': content,
        'title': title,
        'note_id': note_id,
        'date': date,
        'author': author
    }

    notes_collection.insert_one(note_data)

    return redirect(url_for('Diary'))


@app.route('/delete_note', methods=['POST'])
@login_required
def delete_note():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    note_id = request.form.get('note_id')
    note = notes_collection.find_one({'note_id': int(note_id)})

    if note:
        notes_collection.delete_one({'note_id': int(note_id)})
        return redirect(url_for('Diary'))

    return redirect(url_for('Diary'))


@app.route('/verify_id_page')
@login_required
def verify_id_page():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    return render_template('verify_id.html',
                           session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           user=user_collection.find_one(
                               {'username': session['id']})
                           )


@app.route('/verify_id_card', methods=['POST'])
def verify_id_card():
    try:
        user = user_collection.find_one({'username': session['id']})
        id_card = request.files['id_card']
        college_name = user['college_name']
        name = user['full_name']
        ht_number = user['roll_number']

        file_key = f"ID cards/{name}.jpeg"
        job = s3.upload_fileobj(id_card, s3_bucket_name, file_key)
        result = scan.find_matching_text(
            college_name, name, ht_number, file_key)

        if result:
            user['verified'] = True
            session['verified'] = True
            user_collection.update_one(
                {'username': session['id']}, {'$set': user})
            return {'verified': True}
        else:
            return {'verified': False}

    except Exception as e:
        print(e)
        return {'verified': False, 'error': str(e)}


@app.route('/temp')
def temp():
    return render_template('temp.html')


@app.route('/view_profile/<username>', methods=['GET'])
def view_profile(username):
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    user = user_collection.find_one({'username': username})
    follower_count = user.get('followers', [])
    following_count = user.get('following', [])
    post_count = user.get('post_count', 0)

    return render_template('profile.html', user=user, session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, follower_count=len(follower_count), following_count=len(following_count), post_count=post_count
                           )


@app.route('/follow_user', methods=['POST'])
@login_required
def follow_user():
    try:
        user_to_follow = request.json.get('username')
        current_user_id = session['id']

        current_user = user_collection.find_one({'username': current_user_id})
        user_to_follow = user_collection.find_one({'username': user_to_follow})

        if user_to_follow:
            if 'following' not in current_user:
                current_user['following'] = []
            if 'followers' not in user_to_follow:
                user_to_follow['followers'] = []

            if user_to_follow['username'] not in current_user['following']:
                current_user['following'].append(user_to_follow['username'])
                user_to_follow['followers'].append(current_user['username'])
                user_to_follow['reach'][0] += 1
                current_user['reach'][1] += 1

                user_collection.update_one(
                    {'username': current_user_id}, {'$set': current_user})
                user_collection.update_one(
                    {'username': user_to_follow['username']}, {'$set': user_to_follow})

                return {'success': True}

        else:
            return {'success': False}
    except Exception as e:
        print(e)
        return {'success': False, 'error': str(e)}


@app.route('/unfollow_user', methods=['POST'])
@login_required
def unfollow_user():
    try:
        user_to_unfollow = request.json.get('username')
        current_user_id = session['id']

        current_user = user_collection.find_one({'username': current_user_id})
        user_to_unfollow = user_collection.find_one(
            {'username': user_to_unfollow})

        if user_to_unfollow:
            if user_to_unfollow['username'] in current_user['following']:
                current_user['following'].remove(user_to_unfollow['username'])
                user_to_unfollow['followers'].remove(current_user['username'])

                user_to_unfollow['reach'][0] -= 1
                current_user['reach'][1] -= 1

                user_collection.update_one(
                    {'username': current_user_id}, {'$set': current_user})
                user_collection.update_one(
                    {'username': user_to_unfollow['username']}, {'$set': user_to_unfollow})

                return {'success': True}

            else:
                return {'success': False}
        else:
            return {'success': False}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.route('/notif_action', methods=['POST'])
@login_required
def notif_action():
    try:
        notif_id = request.json.get('notif_id')
        action = request.json.get('action')

        user = user_collection.find_one({'username': session['id']})

        if action == 'mark_read':
            for notif in user['notifications']:
                if notif['id'] == notif_id:
                    notif['unread'] = False
                    user_collection.update_one(
                        {'username': session['id']}, {'$set': user})
                    return {'success': True}

        elif action == 'delete':
            for notif in user['notifications']:
                if notif['id'] == notif_id:
                    user['notifications'].remove(notif)
                    user_collection.update_one(
                        {'username': session['id']}, {'$set': user})
                    return {'success': True}

        else:
            return {'success': False}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.route('/update_profile', methods=['POST', 'GET'])
@login_required
def update_profile():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    user = user_collection.find_one({'full_name': session['name']})

    if request.method == 'POST':
        name = request.form.get('name')
        year = request.form.get('year')

        if name != '' and name != None:
            user['full_name'] = name
            session['name'] = name

        name = session['name']

        bio = request.form.get('bio')
        username = request.form.get('username')

        if year != '' and year != None:
            user['year'] = year

        if bio != '' and bio != None:
            user['bio'] = bio

        if username != '':
            posts = posts_collection.find()
            for post in posts:
                if post['author'] == name and post['anonymous'] == False:
                    post['author'] = username
                    posts_collection.update_one(
                        {'post_id': post['post_id']}, {'$set': post})
            user['username'] = username
            user_collection.update_one({'full_name': name}, {'$set': user})
            session['id'] = username

        username = session['id']

        if request.files:
            profile_picture = request.files['profile_picture']
            if profile_picture.filename != '':
                if session['profile_picture'] != 'Profile pictures/avatar_default.jpeg':
                    s3.delete_object(
                        Bucket=s3_bucket_name, Key=session['profile_picture'])

                file_key = f"Profile pictures/{username.lower()}.jpeg"
                job = s3.upload_fileobj(
                    profile_picture, s3_bucket_name, file_key)

                if job:
                    print('Profile picture uploaded successfully')

                profile_picture_s3_key = file_key
                session['profile_picture'] = profile_picture_s3_key

                posts = posts_collection.find()
                for post in posts:
                    if post['author'] == session['name'] and post['anonymous'] == False:
                        post['profile_picture'] = profile_picture_s3_key
                        posts_collection.update_one(
                            {'post_id': post['post_id']}, {'$set': post})

                user['profile_picture_s3_key'] = profile_picture_s3_key
                user_collection.update_one(
                    {'full_name': name}, {'$set': user})

            else:
                profile_picture_s3_key = session['profile_picture']

        user['profile_picture_s3_key'] = profile_picture_s3_key

        user_collection.update_one({'full_name': name}, {'$set': user})

        return redirect(url_for('view_profile', username=username))

    return render_template('account_settings.html', session=session, user=user,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/check_college', methods=['POST'])
def check_college():
    college_name = request.json.get('college_name')

    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    college = colleges_collection.find_one({'college': college_name.lower()})

    if college:
        available = True
    else:
        available = False

    return jsonify({'available': available})


@app.route('/check_item', methods=['POST'])
def check_item():
    check_item = request.json.get('check_item')
    item = request.json.get('item')

    if item == "username":
        users = user_collection.find()

        forbidden_names = []

        f = open("bad_usernames.json")
        data = json.load(f)

        for line in data["usernames"]:
            forbidden_names.append(line)

        for user in users:
            if user['username'].lower() == check_item.lower():
                available = False
                break
            elif check_item in forbidden_names:
                available = False
                break
            else:
                available = True

        return jsonify({'available': available})

    elif item == "name":
        users = user_collection.find()

        for user in users:
            if user['full_name'].lower() == check_item.lower():
                available = False
                break
            else:
                available = True

        return jsonify({'available': available})

    elif item == "phone":
        users = user_collection.find()

        for user in users:
            if user['phone_number'] in check_item:
                available = False
                break
            else:
                available = True

        return jsonify({'available': available})


@app.route('/delete_post', methods=['POST'])
@login_required
def delete_post():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post_id = request.json.get('post_id')
    post = posts_collection.find_one({'post_id': int(post_id)})
    users = user_collection.find_one({'full_name': session['name']})
    if post:
        if post['contains_image']:
            s3.delete_object(Bucket=s3_bucket_name, Key=post['post_image'])
        if post['author'] == session['name']:
            posts_collection.delete_one({'post_id': int(post_id)})
            users['post_count'] = users.get('post_count', 0) - 1
            user_collection.update_one(
                {'full_name': session['name']}, {'$set': users})
            users['posts'] = users.get('posts', [])
            users['posts'].remove(int(post_id))
            user_collection.update_one(
                {'full_name': session['name']}, {'$set': users})
            return {'success': True}
        else:
            return {'success': False}

    return {'success': False}


@app.route('/delete_hive_post', methods=['POST'])
@login_required
def delete_hive_post():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    post_id = request.form.get('post_id')
    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': str(room_id)})
    posts = room['posts']

    for post in posts:
        if post['author'] == session['name']:
            if post['post_id'] == post_id:
                posts.remove(post)
                rooms_collection.update_one(
                    {'room_id': room_id}, {'$set': room})
                return redirect(url_for('hive_room', room_id=room_id, session=session,
                                        builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                        profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                            'profile_picture') else None, ))
    return 'Post not found'


@app.route('/hives')
def hives():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    rooms = rooms_collection.find()

    rooms = list(rooms)

    for room in rooms:
        if room['college_name'] != session['college_name']:
            rooms.remove(room)

    return render_template('hives.html', rooms=rooms, session=session,
                           user=user_collection.find_one(
                               {'username': session['id']}),
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, )


@app.route('/hives/<room_id>')
@login_required
def hive_room(room_id):
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    room = rooms_collection.find_one({'room_id': room_id})
    application = applications_collection.find_one({'user_id': session['id']})

    if application:
        if application['status'] == 'pending':
            applied = True
            is_member = False
    else:
        if room['members']:
            if session['id'] in room['members']:
                applied = False
                is_member = True
            else:
                applied = False
                is_member = False
        else:
            applied = False
            is_member = False

    posts = room['posts']

    return render_template('hive_room.html', session=session,
                           user=user_collection.find_one(
                               {'username': session['id']}),
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/", posts=posts,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           room=room, is_member=is_member, applied=applied)


@app.route('/search_user/<username>', methods=['POST', 'GET'])
def search_user(username):
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    users = user_collection.find()
    user_list = []
    names = []

    collegeSpecific = username.split('_')[1]
    username = username.split('_')[0]

    if collegeSpecific:
        for user in users:
            if user['college_name'] == session['college_name']:
                if username.lower() in user['username'].lower() or username.lower() in user['full_name'].lower():
                    user_list.append(user['username'])
                    names.append(user['full_name'])
    else:
        for user in users:
            if username.lower() in user['username'].lower() or username.lower() in user['full_name'].lower():
                user_list.append(user['username'])
                names.append(user['full_name'])

    return {'users': user_list, 'names': names}


@app.route('/create_hive_post', methods=['POST'])
@login_required
def create_hive_post():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    room_id = request.form.get('room_id')
    post = request.form.get('post_text')
    author = session['name']
    username = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    post_id = author + str(rooms_collection.count_documents({})) + '1'
    hive_post_image = request.files['post_image']
    contains_image = False
    post_image_s3_key = ''
    user = user_collection.find_one({'username': username})

    if profanity.contains_profanity(post):
        if user['warnings'] > 3:
            user['blacklist'] = True
            blacklist_collection.insert_one({'post_id': post_id,
                                            'content': post,
                                             'author': author,
                                             'username': username,
                                             'date': date,
                                             'reason': 'Profanity while making post',
                                             'college_name': session['college_name']
                                             })
            logout_user()
            return {'profanity': True}
        return {'warning': True}

    if hive_post_image:
        contains_image = True
        post_image = request.files['post_image']
        if post_image.filename != '':
            file_key = f"Hive post images/{post_id}.jpeg"
            job = s3.upload_fileobj(post_image, s3_bucket_name, file_key)
            if job:
                print('Post image uploaded successfully')

            post_image_s3_key = file_key

        if scan.check_image_for_profanity(post_image_s3_key):
            blacklist_collection.insert_one({'post_id': post_id,
                                             'content': post,
                                             'author': author,
                                             'username': username,
                                             'date': date,
                                             'reason': 'Profanity while making post',
                                             'college_name': session['college_name']
                                             })
            s3.delete_object(Bucket=s3_bucket_name, Key=post_image_s3_key)

            logout_user()
            return {'profanity': True}

    room = rooms_collection.find_one({'room_id': room_id})
    if room:
        if username in room['members']:
            room['posts'].append({
                'author': author,
                'username': username,
                'content': post,
                'post_id': post_id,
                'profile_picture': session['profile_picture'],
                'date': date,
                'contains_image': contains_image,
                'post_image': post_image_s3_key
            })
            rooms_collection.update_one({'room_id': room_id}, {'$set': room})

            return {'success': True}
        else:
            return {'success': False, 'message': 'You are not a member of this room'}
    else:
        return {'success': False, 'message': f'Hive not found{room_id}'}


@app.route('/apply', methods=['POST'])
@login_required
def apply():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    rooms = rooms_collection.find()
    room_id = request.form.get('room_id')

    for room in rooms:
        if room['room_id'] == room_id:
            if session['id'] in room['members']:
                return 'You are already a member of this room'
            elif session['id'] in room['applicants']:
                return 'You have already applied to this room'
            else:
                room['applicants'].append(session['id'])
                rooms_collection.update_one(
                    {'room_id': room_id}, {'$set': room})
                break

    user_id = session['id']
    application = {
        'user_id': user_id,
        'room_id': room_id,
        'status': 'pending'
    }

    applications_collection.insert_one(application)
    return redirect(url_for('hive_room', room_id=room_id), session=session,
                    builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                    profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                        'profile_picture') else None, )


@app.route('/delete_notification', methods=['POST'])
@login_required
def delete_notification():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    notification_id = request.form.get('notification_id')
    username = session['id']
    user = user_collection.find_one({'username': username})

    for notification in user['notifications']:
        if notification['id'] == notification_id:
            user['notifications'].remove(notification)
            user_collection.update_one({'username': username}, {'$set': user})

    return redirect(url_for('view_profile', username=username))


@app.route('/create_hive', methods=['POST'])
@login_required
def create_hive():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    room_name = request.form.get('room_name')
    room_id = room_name.lower() + str(rooms_collection.count_documents({}) + 1)
    room_description = request.form.get('room_description')
    room = {
        'room_id': room_id,
        'name': room_name,
        'description': room_description,
        'members': [session['id']],
        'applicants': [],
        'posts': [],
        'college_name': session['college_name']
    }
    rooms_collection.insert_one(room)
    return redirect(url_for('hives'))


@app.route('/create_room_page')
@login_required
def create_room_page():
    blacklist = blacklist_collection.find_one({'username': session["id"]})

    if blacklist:
        return render_template('blacklist.html', blacklist=blacklist)

    return render_template('create_hive.html', session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, )


if __name__ == '__main__':
    app.run(debug=True)
