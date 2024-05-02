import easyocr
import requests
from better_profanity import profanity


reader = easyocr.Reader(['en'], detector='dbnet18')

def scan_web_url_image(url):
  try:
    result = reader.readtext(url)

    text_strings = []
    for (bbox, text, prob) in result:
        text_strings.append(text)

    return text_strings

  except requests.exceptions.RequestException as e:
    print(f"Error: Could not fetch image from URL: {e}")
    return []


def find_matching_text(college_name, name, s3_image_url):
    try:
        result = scan_web_url_image(s3_image_url)
        for text in result:
            print(text)
            if college_name.lower() and name.lower() in str(text).lower():
                print(f"Found matching text: {text}")
                return True
              
    except Exception as e:
        print(f"Error: Could not find matching text: {e}")
        return False


def check_image_for_profanity(s3_image_url):
    try:
        result = scan_web_url_image(s3_image_url)
        for text in result:
            if profanity.contains_profanity(text):
                return True
            else:
                return False
    except Exception as e:
        print(f"Error: Could not check image for profanity: {e}")
        return False