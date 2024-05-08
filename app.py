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

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
login_manager = LoginManager(app)

# Load environment variables
load_dotenv()

# AWS S3 configuration
s3_access_key = os.getenv("AWS_ACCESS_KEY_ID")
s3_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
s3_bucket_name = os.getenv("AWS_BUCKET_NAME")

grec_sitekey = os.getenv("GREC_SITEKEY")

# Connect to AWS S3
s3 = boto3.client('s3', aws_access_key_id=s3_access_key, aws_secret_access_key=s3_secret_key)

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
                               'profile_picture') else None
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
]


@app.route('/debug')
@login_required
def debug():
    if session['name'] != "Esvin Joshua":
        return redirect(url_for('index'))

    user_info = user_collection.find()
    s3_files = s3.list_objects_v2(Bucket=s3_bucket_name)['Contents']
    folders = []
    username = session['id']
    os_info = platform.system()
    release = platform.release()
    version = platform.version()
    time = datetime.datetime.now()
    currenttime = time.strftime("%I:%M:%S %p")

    for file in s3_files:
        if file['Key'].endswith('/'):
            folders.append(file['Key'])

    return render_template('debug.html', user_info=user_info, s3_files=s3_files, folders=folders,
                           session=session, os_info=os_info, release=release, version=version, currenttime=currenttime,
                           username=username,
                           current_dir=os.getcwd(), bucket_name=s3_bucket_name,
                           files=os.listdir(), )


@app.route('/admin/<action>/<username>', methods=['POST', 'GET'])
@login_required
def admin(action, username):
    print(action, username)
    user = user_collection.find_one({'username': username})
    if action == 'verify':
        user['verified'] = True
        user_collection.update_one({'username': username}, {'$set': user})
    elif action == 'unverify':
        user['verified'] = False
        user_collection.update_one({'username': username}, {'$set': user})

    return {'success': True}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']

            user = user_collection.find_one({'username': username, 'password': password})
            blacklist = blacklist_collection.find_one({'username': username})

            if blacklist:
                return render_template('blacklist.html', blacklist=blacklist)

            if user:
                if user['username'] == username and user['password'] == password:
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
                                            user=user_collection.find_one({'username': session['id']})
                                            ))
        except Exception as e:
            return render_template('error.html')

        else:
            return 'Invalid username or password'

    return render_template('login.html', grec_sitekey=grec_sitekey)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        college = colleges_collection.find_one({'college_name': request.form.get('college_name').lower()})
        if college:
            pass
        else:
            colleges_collection.insert_one({'college_name': request.form.get('college_name').lower()},
                                           {'$set': {'college_name': request.form.get('college_name').lower()}})

        forbidden_names = []

        f = open("bad_usernames.json")
        data = json.load(f)

        for line in data["usernames"]:
            forbidden_names.append(line)

        full_name = request.form.get('full_name')
        phone_number = request.form.get('phone_number')
        roll_number = request.form.get('roll_number')
        password = request.form.get('password')
        username = request.form.get('username').strip().lower()
        college_name = request.form.get('college_name').lower()
        country_code = request.form.get('country_code')

        user = user_collection.find_one({'username': username})

        if user:
            return 'User already exists'

        if username in forbidden_names:
            return 'Username is not allowed'

        if request.files:
            profile_picture = request.files['profile_picture']
            if profile_picture.filename != '':
                file_key = f"Profile pictures/{username.lower()}.jpeg"
                job = s3.upload_fileobj(profile_picture, s3_bucket_name, file_key)

                if job:
                    print('Profile picture uploaded successfully')

                profile_picture_s3_key = file_key
            else:
                profile_picture_s3_key = "Profile pictures/avatar_default.jpeg"
        else:
            profile_picture_s3_key = "Profile pictures/avatar_default.jpeg"

        user_data = {
            'full_name': full_name,
            'phone_number': country_code + ' ' + phone_number,
            'roll_number': roll_number,
            'profile_picture_s3_key': profile_picture_s3_key,
            'password': password,
            'username': username,
            'verified': False,
            'college_name': college_name,
        }

        user_collection.insert_one(user_data)
        user = user_collection.find_one({'username': username})

        user['badges'] = user.get('badges', [])
        user['badges'].append('Welcome aboard: Make a HiveMind account')

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/upload_material_page')
@login_required
def upload_material_page():
    return render_template('add_material.html', session=session, grec_sitekey=grec_sitekey,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/upload_material', methods=['POST'])
@login_required
def upload_material():
    if request.files:
        year = request.form.get('year')
        material = request.files['material_file']

        if material.filename != '':
            file_key = f"materials/{material.filename}.pdf"
            job = s3.upload_fileobj(material, s3_bucket_name, file_key,
                                    ExtraArgs={'Metadata': {'year': year, 'college': session['college_name']}})

            if scan.check_image_for_profanity(file_key):
                blacklist_collection.insert_one({'title': material.filename,
                                                 'author': session['name'],
                                                 'username': session['id'],
                                                 'date': datetime.datetime.now().strftime("%Y-%m-%D %H:%M"),
                                                 'reason': 'Profanity in material',
                                                 'college_name': session['college_name']
                                                 })
                s3.delete_object(Bucket=s3_bucket_name, Key=file_key)
                logout_user()
                return {'profanity': True}
            else:
                return {'success': True}

    return redirect(url_for('materials'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/materials')
def materials():
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


@app.route('/block_user', methods=['POST'])
@login_required
def block_user():
    username_to_block = request.form.get('username')
    current_user_id = session['id']

    current_user = user_collection.find_one({'username': current_user_id})
    if current_user:
        if 'blocked' not in current_user:
            current_user['blocked'] = []
        current_user['blocked'].append(username_to_block)
        user_collection.update_one({'username': current_user_id}, {'$set': current_user})

    user_to_block = user_collection.find_one({'username': username_to_block})
    if user_to_block:
        if 'blocked_by' not in user_to_block:
            user_to_block['blocked_by'] = []
        user_to_block['blocked_by'].append(current_user_id)
        user_collection.update_one({'username': username_to_block}, {'$set': user_to_block})

    return redirect(url_for('profile', username=username_to_block))


@app.route('/unblock_user', methods=['POST'])
@login_required
def unblock_user():
    username_to_unblock = request.form.get('username')
    current_user_id = session['id']

    current_user = user_collection.find_one({'username': current_user_id})
    if current_user and 'blocked' in current_user:
        if username_to_unblock in current_user['blocked']:
            current_user['blocked'].remove(username_to_unblock)
            user_collection.update_one({'username': current_user_id}, {'$set': current_user})

    user_to_unblock = user_collection.find_one({'username': username_to_unblock})
    if user_to_unblock and 'blocked_by' in user_to_unblock:
        if current_user_id in user_to_unblock['blocked_by']:
            user_to_unblock['blocked_by'].remove(current_user_id)
            user_collection.update_one({'username': username_to_unblock}, {'$set': user_to_unblock})

    return redirect(url_for('profile', username=username_to_unblock))


@app.route('/download', methods=['POST', 'GET'])
def download():
    filename = request.args.get('filename')
    file_url = f"https://{s3_bucket_name}.s3.amazonaws.com/materials/{filename}"
    return redirect(file_url)


@app.route('/tos_prp')
def tos_prp():
    return render_template('tos_prp.html')


@app.route('/create_post', methods=['POST', 'GET'])
@login_required
def create_post():
    title = request.form.get('post_title')
    content = request.form.get('post_text')
    post_picture = request.files['post_image']
    author = session['name']
    user = user_collection.find_one({'full_name': author})
    post_id = posts_collection.count_documents({}) + 1
    date = datetime.date.today().strftime("%d/%m/%y")
    time = datetime.datetime.now().strftime("%H:%M")
    profile_picture = session['profile_picture']
    post_image_s3_key = ''
    contains_image = False

    if user['verified'] == False:
        return redirect(url_for('verify_id_page'))
    
    if profanity.contains_profanity(content) or profanity.contains_profanity(title):
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

    if post_picture:
        contains_image = True
        post_image = request.files['post_image']
        if post_image.filename != '':
            file_key = f"Post images/{post_id}.jpeg"
            job = s3.upload_fileobj(post_image, s3_bucket_name, file_key)
            if job:
                print('Post image uploaded successfully')

            post_image_s3_key = file_key

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
        'contains_image': contains_image,
        'post_image': post_image_s3_key,
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


@app.route('/delete_comment', methods=['POST'])
@login_required
def delete_comment():
    comment = request.form.get('comment')
    author = request.form.get('comment_author')
    posts = posts_collection.find()

    for post in posts:
        if 'comments' in post:
            for c in post['comments']:
                if c['comment'] == comment and c['author'] == author:
                    post['comments'].remove(c)
                    posts_collection.update_one({'post_id': post['post_id']}, {'$set': post})

    return redirect(url_for('view_posts'))


@app.route('/hive_comment', methods=['POST'])
@login_required
def hive_comment():
    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    blacklist = blacklist_collection.find()

    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': room_id})
    posts = room['posts']

    if profanity.contains_profanity(comment):
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
            return redirect(url_for('hive_room', room_id=room_id, session=session,
                                    builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                    profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                        'profile_picture') else None, ))
    return 'Post not found'


@app.route('/comment', methods=['POST'])
@login_required
def comment():
    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = session['name']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")

    post = posts_collection.find_one({'post_id': int(post_id)})

    if profanity.contains_profanity(comment):
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

            post_author = user_collection.find_one({'username': post['username']})
            notification = {
                'message': 'A comment has been made on your post by ' + session['name'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one({'username': post['username']}, {'$set': post_author})

        else:
            post['comments'] = [{
                'comment': comment,
                'author': author
            }]

            post_author = user_collection.find_one({'username': post['username']})
            notification = {
                'message': 'A comment has been made on your post by ' + session['name'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one({'username': post['username']}, {'$set': post_author})
        posts_collection.update_one({'post_id': int(post_id)}, {'$set': post})

    return redirect(url_for('view_posts'))


@app.route('/dashboard')
@login_required
def dashboard():
    college = colleges_collection.find_one({'college_name': session['college_name']})

    if college['user_count'] < 10:
        message = "It's a bit lonely here. Why not invite some friends to join?"
    else:
        message = None

    return render_template('dashboard.html',
                           session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           college=college, message=message, user=user_collection.find_one({'username': session['id']})
                           )


@app.route('/hive_post_comment', methods=['POST'])
@login_required
def hive_post_comment():
    post_id = request.form.get('post_id')
    comment = request.form.get('comment')
    author = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")

    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': room_id})

    posts = room['posts']

    if profanity.contains_profanity(comment):
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
            post_author = user_collection.find_one({'username': post['username']})
            notification = {

                'message': 'A comment has been made on your post by ' + session['name'] + 'on your post: ' + post[
                    'date'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one({'username': post['username']}, {'$set': post_author})
            return redirect(url_for('hive_room', room_id=room_id, session=session,
                                    builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                    profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                        'profile_picture') else None, ))
    return 'Post not found'


@app.route('/delete_hive_comment', methods=['POST'])
@login_required
def delete_hive_comment():
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
                    rooms_collection.update_one({'room_id': room_id}, {'$set': room})
                    return redirect(url_for('hive_room', room_id=room_id, session=session,
                                            builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                            profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                                'profile_picture') else None, ))
    return 'Comment not found'


@app.route('/posts')
@login_required
def view_posts():
    if session.get('id') is None:
        return redirect(url_for('login'))

    posts = posts_collection.find()

    posts = list(posts_collection.find())
    user_posts = []

    for post in posts:
        if post['anonymous']:
            post['author'] = 'Anonymous'
        if post['college_name'] == session['college_name']:
            user_posts.append(post)

    sorted_posts = sorted(user_posts, key=lambda x: x['post_id'], reverse=True)

    return render_template('posts.html', posts=sorted_posts,
                           session=session,
                           user=user_collection.find_one({'username': session['id']}),
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           content_placeholder=random.choice(content_placeholders),
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/serve_post/<post_id>', methods=['GET', 'POST'])
@login_required
def serve_post(post_id):
    post = posts_collection.find_one({'post_id': int(post_id)})
    user = user_collection.find_one({'username': session['id']})

    return render_template('post.html', post=post, session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/", user=user,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/mindspace')
@login_required
def mindspace():
    notes = notes_collection.find({'author': session['name']})

    return render_template('mindspace.html', session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, notes=notes if notes else None
                           )


@app.route('/note', methods=['POST'])
@login_required
def note():
    content = request.form.get('note_content')
    title = request.form.get('note_title')
    note_id = notes_collection.count_documents({}) + 1
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

    return redirect(url_for('mindspace'))


@app.route('/delete_note', methods=['POST'])
@login_required
def delete_note():
    note_id = request.form.get('note_id')
    note = notes_collection.find_one({'note_id': int(note_id)})

    if note:
        notes_collection.delete_one({'note_id': int(note_id)})
        return redirect(url_for('mindspace'))

    return redirect(url_for('mindspace'))

@app.route('/verify_id_page')
@login_required
def verify_id_page():
    return render_template('verify_id.html',
                           session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           user=user_collection.find_one({'username': session['id']})
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
        result = scan.find_matching_text(college_name, name, ht_number, file_key)

        if result:
            user['verified'] = True
            session['verified'] = True
            user_collection.update_one({'username': session['id']}, {'$set': user})
            return {'verified': True}
        else:
            return {'verified': False}

    except Exception as e:
        return {'verified': False, 'error': str(e)}


@app.route('/temp')
def temp():
    return render_template('temp.html')


@app.route('/view_profile/<username>', methods=['GET'])
def view_profile(username):
    user = user_collection.find_one({'username': username})

    return render_template('profile.html', user=user, session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/mark_notification_as_read', methods=['POST'])
@login_required
def mark_notification_as_read():
    notification_index = request.form.get('notification_id')
    username = session['id']
    user = user_collection.find_one({'username': username})

    for notification in user['notifications']:
        if notification['id'] == notification_index:
            notification['unread'] = False
            user_collection.update_one({'username': username}, {'$set': user})

    return redirect(url_for('view_profile', username=username))


@app.route('/update_profile', methods=['POST', 'GET'])
@login_required
def update_profile():
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
            user['bio_changed'] = 0
            user['bio'] = bio

        if username != '':
            posts = posts_collection.find()
            for post in posts:
                if post['author'] == name and post['anonymous'] == False:
                    post['author'] = username
                    posts_collection.update_one({'post_id': post['post_id']}, {'$set': post})
            user['username_changed'] = 0
            user['username'] = username
            user_collection.update_one({'full_name': name}, {'$set': user})
            session['id'] = username

        username = session['id']

        if request.files:
            profile_picture = request.files['profile_picture']
            if profile_picture.filename != '':
                file_key = f"Profile pictures/{username.lower()}.jpeg"
                job = s3.upload_fileobj(profile_picture, s3_bucket_name, file_key)

                if job:
                    print('Profile picture uploaded successfully')

                profile_picture_s3_key = file_key
                session['profile_picture'] = profile_picture_s3_key

                posts = posts_collection.find()
                for post in posts:
                    if post['author'] == session['name'] and post['anonymous'] == False:
                        post['profile_picture'] = profile_picture_s3_key
                        posts_collection.update_one({'post_id': post['post_id']}, {'$set': post})

            else:
                profile_picture_s3_key = session['profile_picture']

        user['profile_picture_s3_key'] = profile_picture_s3_key

        user_collection.update_one({'full_name': name}, {'$set': user})

        return redirect(url_for('view_profile', username=username))

    return render_template('account_settings.html', session=session, user=user,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None
                           )


@app.route('/check_college/<college_name>', methods=['GET'])
def check_college(college_name):
    college = colleges_collection.find_one({'college': college_name.lower()})

    if college:
        available = True
    else:
        available = False

    return jsonify({'available': available})


@app.route('/check_username/<username>', methods=['GET'])
def check_username(username):
    users = user_collection.find()

    forbidden_names = []

    f = open("bad_usernames.json")
    data = json.load(f)

    for line in data["usernames"]:
        forbidden_names.append(line)

    for user in users:
        if user['username'].lower() == username.lower():
            available = False
            break
        elif username in forbidden_names:
            available = False
            break
        else:
            available = True

    return jsonify({'available': available})


@app.route('/delete_post', methods=['POST'])
@login_required
def delete_post():
    post_id = request.form.get('post_id')
    post = posts_collection.find_one({'post_id': int(post_id)})
    users = user_collection.find_one({'full_name': session['name']})
    if post:
        if post['contains_image']:
            s3.delete_object(Bucket=s3_bucket_name, Key=post['post_image'])
        if post['author'] == session['name']:
            posts_collection.delete_one({'post_id': int(post_id)})
            users['post_count'] = users.get('post_count', 0) - 1
            user_collection.update_one({'full_name': session['name']}, {'$set': users})
            users['posts'] = users.get('posts', [])
            users['posts'].remove(int(post_id))
            user_collection.update_one({'full_name': session['name']}, {'$set': users})
            return redirect(url_for('view_posts'))
        else:
            return 'You are not the author of this post'

    return 'Post not found'


@app.route('/delete_hive_post', methods=['POST'])
@login_required
def delete_hive_post():
    post_id = request.form.get('post_id')
    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': str(room_id)})
    posts = room['posts']

    for post in posts:
        if post['author'] == session['name']:
            if post['post_id'] == post_id:
                posts.remove(post)
                rooms_collection.update_one({'room_id': room_id}, {'$set': room})
                return redirect(url_for('hive_room', room_id=room_id, session=session,
                                        builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                        profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                                            'profile_picture') else None, ))
    return 'Post not found'


@app.route('/hives')
def hives():
    rooms = rooms_collection.find()

    rooms = list(rooms)

    for room in rooms:
        if room['college_name'] != session['college_name']:
            rooms.remove(room)

    return render_template('hives.html', rooms=rooms, session=session,
                           user=user_collection.find_one({'username': session['id']}),
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, )


@app.route('/hives/<room_id>')
@login_required
def hive_room(room_id):
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
                           user=user_collection.find_one({'username': session['id']}),
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/", posts=posts,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None,
                           room=room, is_member=is_member, applied=applied)


@app.route('/create_hive_post', methods=['POST'])
@login_required
def create_hive_post():
    room_id = request.form.get('room_id')
    post = request.form.get('post_text')
    author = session['name']
    username = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    post_id = author + str(rooms_collection.count_documents({})) + '1'
    hive_post_image = request.files['post_image']
    contains_image = False
    post_image_s3_key = ''

    if hive_post_image:
        contains_image = True
        post_image = request.files['post_image']
        if post_image.filename != '':
            file_key = f"Hive post images/{post_id}.jpeg"
            job = s3.upload_fileobj(post_image, s3_bucket_name, file_key)
            if job:
                print('Post image uploaded successfully')

            post_image_s3_key = file_key

        if profanity.contains_profanity(post) or scan.check_image_for_profanity(post_image_s3_key):
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
                rooms_collection.update_one({'room_id': room_id}, {'$set': room})
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
    return render_template('create_hive.html', session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get(
                               'profile_picture') else None, )


if __name__ == '__main__':
    app.run(debug=True)
