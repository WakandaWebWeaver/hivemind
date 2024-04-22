from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
import boto3
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import datetime
import json
from better_profanity import profanity

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
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )

# for any error, return the error.html
@app.errorhandler(Exception)
def page_not_found(e):
    print(e)
    error_message = str(e)[:500]  
    return render_template('error.html', error = error_message)

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
    
                    return redirect(url_for('index'))
        except Exception as e:
            print(e)
        
        else:
            return 'Invalid username or password'
        
    return render_template('login.html', grec_sitekey=grec_sitekey)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        forbidden_names = []

        f = open("bad_usernames.json")
        data = json.load(f)

        for line in data["usernames"]:
            forbidden_names.append(line)


        full_name = request.form.get('full_name')
        phone_number = request.form.get('phone_number')
        roll_number = request.form.get('roll_number')
        password = request.form.get('password')
        username = request.form.get('username').strip()
        college_name = request.form.get('college_name')

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
            'phone_number': phone_number,
            'roll_number': roll_number,
            'profile_picture_s3_key': profile_picture_s3_key,
            'password': password, 
            'username': username,
            'college_name': college_name,
        }
        user_collection.insert_one(user_data)

        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/upload_material_page')
@login_required
def upload_material_page():
    return render_template('add_material.html',session=session, grec_sitekey=grec_sitekey,
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )

@app.route('/upload_material', methods=['POST'])
@login_required
def upload_material():
    if request.files:
        # Get the 'year' from the dropdown menu in the form
        year = request.form.get('year')
        material = request.files['material_file']
        if material.filename != '':
            file_key = f"materials/{material.filename}.pdf"
            job = s3.upload_fileobj(material, s3_bucket_name, file_key, ExtraArgs={'Metadata': {'year': year}})

            if job:
                return 'Material uploaded successfully'
            else:
                return 'Material upload failed'

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
        if key.endswith('.pdf'):  # You can adjust the file extension as needed
            title = os.path.basename(key)
            # Get metadata from S3 object
            metadata_response = s3.head_object(Bucket=s3_bucket_name, Key=key)
            year = metadata_response['ResponseMetadata']['HTTPHeaders']['x-amz-meta-year']
            materials.append({'title': title, 'year': int(year)})

    return render_template('materials.html', materials=materials, session=session,
                           profile_picture_url=f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None)



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

@app.route('/create_post', methods=['POST'])
@login_required
def create_post():
    title = request.form.get('post_title')
    content = request.form.get('post_text')
    author = session['name']
    post_id = posts_collection.count_documents({}) + 1
    date = datetime.date.today().strftime("%d/%m/%Y")
    time = datetime.datetime.now().strftime("%H:%M")

    profile_picture = session['profile_picture']

    if profanity.contains_profanity(content) or profanity.contains_profanity(title):
        blacklist_collection.insert_one({'title': title,
                                        'content': content,
                                        'author': author,
                                        'username': session['id'],
                                        'profile_picture': profile_picture,
                                        'date': date,
                                        'time': time,
                                        'reason': 'Profanity while making a post.'
                                    })
        return 'Profanity is not allowed'
    
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
        'anonymous': anonymous

    }

    user = user_collection.find_one({'full_name': author})
    user['post_count'] = user.get('post_count', 0) + 1
    user_collection.update_one({'full_name': author}, {'$set': user})

    user['posts'] = user.get('posts', [])
    user['posts'].append(post_id)
    user_collection.update_one({'full_name': author}, {'$set': user})


    posts_collection.insert_one(post_data)

    return redirect(url_for('view_posts'))


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
                                        'date': date,
                                        'reason for blacklist': 'Profanity is not allowed'
                                    })
        return 'Profanity is not allowed'

    if post:
        if 'comments' in post:
            post['comments'].append({
                'comment': comment,
                'author': author
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

    for post in posts:
        if post['post_id'] == post_id:
            post['comments'] = post.get('comments', [])
            post['comments'].append({
                'comment': comment,
                'author': author,
                'date': date
            })
            rooms_collection.update_one({'room_id': room_id}, {'$set': room})
            post_author = user_collection.find_one({'username': post['username']})
            notification = {

                'message': 'A comment has been made on your post by ' + session['name'] + 'on your post: ' + post['date'],
                'unread': True,
                'id': str(post_id) + 'comment' + str(len(post['comments']))
            }
            post_author['notifications'] = post_author.get('notifications', [])
            post_author['notifications'].append(notification)
            user_collection.update_one({'username': post['username']}, {'$set': post_author})
            return redirect(url_for('hive_room', room_id=room_id, session=session,
                                   builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                   profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,))
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
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,))
    return 'Comment not found'




@app.route('/posts')
@login_required
def view_posts():
    posts = posts_collection.find()

    posts = list(posts_collection.find())

    for post in posts:
        if post['anonymous']:
            post['author'] = 'Anonymous'


    comments = []
    for post in posts:
        if 'comments' in post:
            for comment in post['comments']:
                comments.append({
                    'comment': comment['comment'],
                    'author': comment['author']
                })

    sorted_posts = sorted(posts, key=lambda x: x['post_id'], reverse=True)

    return render_template('posts.html', posts=sorted_posts, 
                           session=session,
                           comments=comments,
                            builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
    )

@app.route('/view_profile/<username>', methods=['GET'])
def view_profile(username):
    user = user_collection.find_one({'username': username})

    return render_template('profile.html', user=user, session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
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

    # Return 200 status code
    return redirect(url_for('view_profile', username=username))



@app.route('/update_profile', methods=['POST', 'GET'])
@login_required
def update_profile():
    if request.method == 'POST':
        name = session['name']

        bio = request.form.get('bio')
        username = request.form.get('username')

        if bio != '':
            user['bio'] = bio

        if username != '':
            posts = posts_collection.find()
            for post in posts:
                if post['author'] == name:
                    post['author'] = username
                    posts_collection.update_one({'post_id': post['post_id']}, {'$set': post})

            user['username'] =  username
        else:
            username = session['id']


        name = session['name']


        if request.files:
            profile_picture = request.files['profile_picture']
            if profile_picture.filename != '':
                file_key = f"Profile pictures/{name.strip().lower()}.jpeg"
                job = s3.upload_fileobj(profile_picture, s3_bucket_name, file_key)

                if job:
                    print('Profile picture uploaded successfully')

                profile_picture_s3_key = file_key
                session['profile_picture'] = profile_picture_s3_key

                posts = posts_collection.find()
                for post in posts:
                    if post['author'] == session['name']:
                        post['profile_picture'] = profile_picture_s3_key
                        posts_collection.update_one({'post_id': post['post_id']}, {'$set': post})

            else:
                profile_picture_s3_key = session['profile_picture']

        user = user_collection.find_one({'full_name': name})

        user['profile_picture_s3_key'] = profile_picture_s3_key

        user_collection.update_one({'full_name': name}, {'$set': user})

        return redirect(url_for('view_profile', username=username))
    
    return render_template('account_settings.html', session=session,
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )

@app.route('/check_username/<username>', methods=['GET'])
def check_username(username):
    username = request.form.get('username')
    user = user_collection.find_one({'username': username})

    if user:
        available = False
    else:
        available = True

    return jsonify({'available': available})

@app.route('/update_bio', methods=['POST'])
@login_required
def update_bio():
    bio = request.form.get('bio')
    username = session['id']
    user = user_collection.find_one({'username': username})
    user['bio'] = bio
    user_collection.update_one({'username': username}, {'$set': user})
    return redirect(url_for('view_profile', username=username))

@app.route('/delete_post', methods=['POST'])
@login_required
def delete_post():
    post_id = request.form.get('post_id')
    posts = posts_collection.find()
    users = user_collection.find()

    for user in users:
        if user['full_name'] == session['name']:
            user['post_count'] = user.get('post_count', 0) - 1
            user_collection.update_one({'full_name': session['name']}, {'$set': user})
            user['posts'] = user.get('posts', [])
            user['posts'].remove(int(post_id))
            user_collection.update_one({'full_name': session['name']}, {'$set': user})

    for post in posts:
        # check if currrent username is the author of the post
        if post['author'] == session['name']:
            if post['post_id'] == int(post_id):
                posts_collection.delete_one({'post_id': int(post_id)})
                return redirect(url_for('view_posts'))
            
@app.route('/delete_hive_post', methods=['POST'])
@login_required
def delete_hive_post():
    post_id = request.form.get('post_id')
    room_id = request.form.get('room_id')
    room = rooms_collection.find_one({'room_id': room_id})
    posts = room['posts']

    for post in posts:
        if post['author'] == session['id']:
            if post['post_id'] == post_id:
                posts.remove(post)
                rooms_collection.update_one({'room_id': room_id}, {'$set': room})
                return redirect(url_for('hive_room', room_id=room_id, session=session,
                               builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,))
    return 'Post not found'


@app.route('/hives')
def hives():
    rooms = rooms_collection.find()
    return render_template('hives.html', rooms=rooms,session=session,
                               builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,)

@app.route('/hives/<room_id>')
@login_required
def hive_room(room_id):
    room = rooms_collection.find_one({'room_id': room_id})
    application = applications_collection.find_one({'user_id': session['id']})

    if application:
        if application['status'] == 'pending':
            is_member = False
    else:
        is_member = True

    # if room['owner'] == session['id']:
    #     is_owner = True

    # Get the posts for the room
    posts = room['posts']

    return render_template('hive_room.html',session=session,
                            builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/", posts=posts,
                                profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,
                            room=room, is_member=is_member)
    

@app.route('/create_hive_post', methods=['POST'])
@login_required
def create_hive_post():
    room_id = request.form.get('room_id')
    post = request.form.get('post_text')
    author = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    post_id = author+str(rooms_collection.count_documents({}))

    room = rooms_collection.find_one({'room_id': room_id})
    if room:
        if author in room['members']:
            room['posts'].append({
                'author': author,
                'content': post,
                'post_id': post_id,
                'profile_picture': session['profile_picture'],
                'date': date
            })
            rooms_collection.update_one({'room_id': room_id}, {'$set': room})

            return redirect(url_for('hive_room', room_id=room_id, session=session, room=room,
                               builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None ))
        else:
            return 'You are not a member of this room'
    else:
        return 'Hive not found', 404
    

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
    return redirect(url_for('hive_room', room_id=room_id, session=session,
                               builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,))

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
        'posts': []
    }
    rooms_collection.insert_one(room)
    return redirect(url_for('hives'))

@app.route('/post_message', methods=['POST'])
@login_required
def post_message():
    room_id = request.form.get('room_id')
    message = request.form.get('message')
    author = session['id']
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    room = rooms_collection.find_one({'room_id': room_id})
    if room:
        if author in room['members']:
            room['posts'].append({
                'author': author,
                'content': message,
                'date': date
            })
            rooms_collection.update_one({'room_id': room_id}, {'$set': room})
            return redirect(url_for('hive_room', room_id=room_id,session=session,
                               builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,))
        else:
            return 'You are not a member of this room'
    else:
        return 'Hive not found', 404
    

@app.route('/send_direct_message', methods=['POST'])
@login_required
def send_direct_message():
    message = request.form.get('direct_message')
    sender = request.form.get('sender')
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    recipient = request.form.get('recipient')

    recipient = user_collection.find_one({'username': recipient})

    recipient['direct_messages'] = recipient.get('direct_messages', [])

    recipient['direct_messages'].append({
        'message': message,
        'sender': sender,
        'date': date
    })


@app.route('/direct_messaging')
@login_required
def direct_messages():
    return render_template('direct_messages.html',
                           session=session,
                            profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,
                            builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           )


@app.route('/create_room_page')
@login_required
def create_room_page():
    return render_template('create_hive.html', session=session,
                               builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                                 profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None,)

if __name__ == '__main__':
    app.run(debug=True)