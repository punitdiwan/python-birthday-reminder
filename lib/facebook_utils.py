import json
import os
import requests
from lib.db_manager import execute_query

def get_page_access_token(school_id: str, pages_file="fb_pages.json"):
    """
    Fetch the Facebook Page ID from the configurations table, and get the matching access token
    from fb_pages.json. If fb_pages.json doesn't exist, create it by calling Graph API once.
    """
    # 1️⃣ Get the facebook_page_id from configurations
    query = """
        SELECT config_value AS facebook_page_id
        FROM {0}.configurations
        WHERE config_key = 'facebook_page_id'
        AND _school = %s
        LIMIT 1
    """.format(school_id)

    result = execute_query(query, (school_id,))
    if not result:
        raise Exception(f"No facebook_page_id found in configurations for {school_id}")

    page_id = str(result[0]["facebook_page_id"])

    # 2️⃣ If fb_pages.json doesn't exist, fetch it from Facebook Graph API
    if not os.path.exists(pages_file):
        print("📥 fb_pages.json not found. Fetching from Facebook Graph API...")
        user_access_token = os.getenv("ACCESS_TOKEN")
        if not user_access_token:
            raise Exception("❌ ACCESS_TOKEN not found in environment variables")

        fb_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_access_token}"
        response = requests.get(fb_url)
        response.raise_for_status()

        with open(pages_file, "w") as f:
            f.write(response.text)

        print("✅ fb_pages.json created successfully.")

    # 3️⃣ Load fb_pages.json
    with open(pages_file, "r") as f:
        pages_data = json.load(f)["data"]

    # 4️⃣ Find the matching page
    page = next((p for p in pages_data if p["id"] == page_id), None)
    if not page:
        raise Exception(f"Page ID {page_id} not found in {pages_file}")

    print(f"✅ Found Page: {page['name']} ({page['id']})")

    return page["id"], page["access_token"]
