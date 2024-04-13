from flask import Flask, render_template, redirect, url_for, request, send_file, session
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

# Connect to AWS S3
s3 = boto3.client('s3', aws_access_key_id=s3_access_key, aws_secret_access_key=s3_secret_key)

app.config['MONGO_URI'] = os.getenv('MONGO_URI')

mongo = MongoClient(app.config['MONGO_URI'])
db_name = os.getenv('MONGO_DB_NAME')
db = mongo[db_name]

user_collection = db['users']
posts_collection = db['posts']
blacklist_collection = db['blacklist']




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
    return render_template('error.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = user_collection.find_one({'username': username, 'password': password})
        blacklist = blacklist_collection.find_one({'username': username, 'password': password})

        if blacklist:
            return 'You have been blacklisted. Contact the admin for further information.'
        
        if user:
            if user['username'] == username and user['password'] == password:
                user_obj = User()
                user_obj.id = username
                login_user(user_obj)
                session['name'] = user['full_name']
                session['id'] = user['username']
                session['profile_picture'] = user['profile_picture_s3_key']
                return redirect(url_for('materials'))
        else:
            return 'Invalid username or password'
        
    return render_template('login.html')


@app.route('/register-page')
def register_page():
    return render_template('register.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        forbidden_names = []

        f = open("bad_usernames.json")
        data = json.load(f)

        for line in data["usernames"]:
            print("line: ", line)
            forbidden_names.append(line)


        full_name = request.form.get('full_name')
        phone_number = request.form.get('phone_number')
        roll_number = request.form.get('roll_number')
        password = request.form.get('password')
        username = request.form.get('username')

        user = user_collection.find_one({'username': username})
        if user:
            return 'User already exists'
        
        if username in forbidden_names:
            return 'Username is not allowed'

        if 'profile_picture' in request.files:
            profile_picture = request.files['profile_picture']
            if profile_picture.filename != '':
                file_key = f"Profile pictures/{username.lower()}"
                s3.upload_fileobj(profile_picture, s3_bucket_name, file_key)
                profile_picture_s3_key = f"Profile pictures/{username}"
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
            'username': username
        }
        user_collection.insert_one(user_data)

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/upload_material_page')
@login_required
def upload_material_page():
    return render_template('add_material.html',session=session,
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )

@app.route('/upload_material', methods=['POST'])
@login_required
def upload_material():
    if request.files:
        material = request.files['material_file']
        if material.filename != '':
            file_key = f"materials/{material.filename}.pdf"
            s3.upload_fileobj(material, s3_bucket_name, file_key)

    print(request.form)

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
            materials.append({'title': title})

    return render_template('materials.html', materials=materials,session=session,
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )



@app.route('/download', methods=['POST', 'GET'])
def download():
    filename = request.args.get('filename')
    print("filename: ", filename)
    file_url = f"https://{s3_bucket_name}.s3.amazonaws.com/materials/{filename}"
    return redirect(file_url)


@app.route('/create_post_page')
@login_required
def create_post_page():
    return render_template('create_post.html',session=session,
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )

@app.route('/create_post', methods=['POST'])
@login_required
def create_post():
    title = request.form.get('post_title')
    content = request.form.get('post_text')
    author = session['name']
    post_id = posts_collection.count_documents({}) + 1
    date = datetime.datetime.now().strftime("%Y-%m-%D %H:%M")
    profile_picture = session['profile_picture']

    if profanity.contains_profanity(content) or profanity.contains_profanity(title):
        blacklist_collection.insert_one({'title': title,
                                        'content': content,
                                        'author': author,
                                        'profile_picture': profile_picture,
                                        'date': date,
                                        'reason for blacklist': 'Profanity is not allowed'
                                    })
        return 'Profanity is not allowed'

    post_data = {
        'title': title,
        'content': content,
        'author': author,
        'username': session['name'],
        'profile_picture': profile_picture,
        'date': date,
        'post_id': post_id

    }

    user = user_collection.find_one({'full_name': author})
    user['post_count'] = user.get('post_count', 0) + 1
    user_collection.update_one({'full_name': author}, {'$set': user})

    user['posts'] = user.get('posts', [])
    user['posts'].append(post_id)
    user_collection.update_one({'full_name': author}, {'$set': user})


    posts_collection.insert_one(post_data)

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
        else:
            post['comments'] = [{
                'comment': comment,
                'author': author
            }]
        posts_collection.update_one({'post_id': int(post_id)}, {'$set': post})

    return redirect(url_for('view_posts'))


@app.route('/posts')
@login_required
def view_posts():
    posts = posts_collection.find()

    posts = list(posts_collection.find())

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
    print("user: ", user)
    return render_template('profile.html', user=user, session=session,
                           builder_url=f"https://{s3_bucket_name}.s3.amazonaws.com/",
                           profile_picture_url= f"https://{s3_bucket_name}.s3.amazonaws.com/{session['profile_picture']}" if session.get('profile_picture') else None
                           )

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

    for post in posts:
        # check if currrent username is the author of the post
        if post['author'] == session['name']:
            if post['post_id'] == int(post_id):
                posts_collection.delete_one({'post_id': int(post_id)})
                return redirect(url_for('view_posts'))

if __name__ == '__main__':
    app.run(debug=True)