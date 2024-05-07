import boto3
from better_profanity import profanity
import os
from dotenv import load_dotenv
import re

load_dotenv()

bucket = os.getenv("AWS_BUCKET_NAME")
region = os.getenv("AWS_REGION")

client = boto3.client('textract' , region_name=region)


def clean_text(text):
    cleaned_text = []
    for item in text:
        item = re.sub(r'\x1b\[\d+m', '', item)
        item = re.sub(r'\x1b\[\d+m', '', item)
        cleaned_text.append(item)

    cleaned_text = ' '.join(cleaned_text)

    return cleaned_text

def scan_web_url_image(url):
    response = client.detect_document_text(
        Document={
            'S3Object': {
                'Bucket': bucket,
                'Name': url
            }
        }
    )
    text = []
    for item in response["Blocks"]:
        if item["BlockType"] == "LINE":
             text.append('\033[94m' +  item["Text"] + '\033[0m')

    text = clean_text(text)
    return text

def find_matching_text(college_name, name, ht_number, s3_image_url):
    try:
        result = scan_web_url_image(s3_image_url)
        result = result.lower()
        if result.__contains__(college_name.lower()) and result.__contains__(name.lower()) and result.__contains__(ht_number.lower()):
            return True
        else:
            return False              
    except Exception as e:
        print(f"Error: Could not find matching text: {e}")
        return False

def check_image_for_profanity(s3_image_url):
    try:
        result = scan_web_url_image(s3_image_url)
        for text in result:
            if profanity.contains_profanity(text.lower()):
                return True
            else:
                continue
        return False
    except Exception as e:
        print(f"Error: Could not check image for profanity: {e}")
        return False