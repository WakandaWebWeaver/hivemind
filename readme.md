# HiveMind

> Development paused. Might resume, idk :)

> Star the repository if you like the project, and feel free to contribute.

## Description

HiveMind is a college-specific platform that allows students to share study materials, ask questions, and discuss topics with their peers. The platform is designed to be user-friendly and easy to navigate, with features such as a profanity filter. Users can create posts, comment on posts, view/download study materials, upload study materials etc.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Features](#features)

## Installation

1. Clone the repository
   ```
   git clone https://github.com/WakandaWebWeaver/hivemind.git
   ```
2. Install the required packages
   ```
    pip install -r requirements.txt
   ```
3. Run the application
   ```
   python app.py
   ```

## Usage

1. Before you can use the application, you need to setup various services such as an amazon s3 bucket, a MongoDB database, and also update the environment variables in the .env file.
2. Once you have setup the services, you can run the application using the command `python app.py`

## Services Setup

Setting up your program to interact with the MongoDB can be quite painful and confusing, but you only need to change two things in the file:

1. The .env variables
2. The DB name

As for interacting with the AWS CS, this process is a little extensive.

1. Sign up for the AWS Console, and search for S3 in the search bar.
   > Follow the instructions on screen to continue to create a Storage Bucket.
2. Now, search for 'IAM' in the search bar

   > Proceed to create a new user in your organization which can interact with these databases.
   > When setting permissions, make sure to select the following
   > permissions:
   >
   > - AmazonS3FullAccess
   > - AmazonTextractFullAccess
   > - AmazonTextractServiceRole
   > - IAMUserChangePassword

3. Finally, copy the relevant data [AWS_ACCESS_KEY_ID and the AWS_SECRET_ACCESS_KEY] which can be found in the user information page, and also the region of your S3 bucket, and update the .env file.

Another service you need to setup is the Giphy API. This is a simple process, just sign up for a Giphy account and create a new app. You will be given an API key which you can use to interact with the Giphy API.

```env
The .env file should look something like this:

AWS_BUCKET_NAME=
AWS_ACCESS_KEY_ID=
AWS_REGION=
AWS_SECRET_ACCESS_KEY=
MONGO_URI=
MONGO_DB_NAME=
GREC_SITEKEY=
GIPHY_API_KEY=
```

> For information on creating, accessing and viewing your mongo dbs, [Mongo Docs](https://www.mongodb.com/docs/atlas/)

> For information on creating a reCaptcha key, check out [Google reCaptcha](https://www.google.com/recaptcha/about/)

> Info on AWS, [AWS S3 Setup Guide](https://aws.amazon.com/s3/getting-started/)

## Features

- Create Posts (Text, Image, Video & Audio)
- Comment on Posts
- View/Download Study Materials
- Upload Study Materials
- Search for Study Materials
- Profile Pages

## Additional Features

Here are some of the special features:

- reCaptcha
- User authentication
- User account creation
- Profanity filter
- Add songs to posts and profile

## Contributing

> To request features, report issues and bugs, please start a new issue in the issues tab.

> Don't forget to star the repository if you like the project
