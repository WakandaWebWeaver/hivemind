import boto3
from better_profanity import profanity
import os
from dotenv import load_dotenv
import re

load_dotenv()

bucket = os.getenv("AWS_BUCKET_NAME")
region = os.getenv("AWS_REGION")

client = boto3.client('textract' , region_name=region)


def clean_text(text, return_type):
    cleaned_text = []
    for item in text:
        item = re.sub(r'\x1b\[\d+m', '', item)
        item = re.sub(r'\x1b\[\d+m', '', item)
        cleaned_text.append(item)

    if return_type == "list":
        return cleaned_text
    else:
        cleaned_text = ' '.join(cleaned_text)
        return cleaned_text


def scan_web_url_image(url, return_text_type):
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

    if return_text_type == "clean":
        return clean_text(text, "string")
    else:
        return clean_text(text, "list")
    

def find_matching_text(college_name, name, ht_number, s3_image_url):
    try:
        result = scan_web_url_image(s3_image_url, "clean")
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
        result = scan_web_url_image(s3_image_url, "raw")
        print(result)
        for text in result:
            print(str(text.lower()))
            if profanity.contains_profanity(str(text.lower())):
                return True
            else:
                continue
        return False
    except Exception as e:
        print(f"Error: Could not check image for profanity: {e}")
        return False