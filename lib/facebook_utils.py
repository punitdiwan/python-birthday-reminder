import json
import os
import requests
from lib.db_manager import execute_query

PAGES_ENV_KEY = "FB_PAGES_CACHE"   # single env variable to store JSON

def get_page_access_token(school_id: str):
    """
    Fetch the Facebook Page ID from DB config, then match with FB pages
    fetched from Graph API stored in environment variable instead of file.
    """

    # 1️⃣ Get page ID from database
    query = f"""
        SELECT config_value AS facebook_page_id
        FROM {school_id}.configurations
        WHERE config_key = 'facebook_page_id'
        AND _school = %s
        LIMIT 1
    """
    result = execute_query(query, (school_id,))
    if not result:
        raise Exception(f"No facebook_page_id found for {school_id}")

    page_id = str(result[0]["facebook_page_id"])

    # 2️⃣ Check if FB pages data is already in environment
    pages_json = os.getenv(PAGES_ENV_KEY)

    if pages_json:
        pages_data = json.loads(pages_json)["data"]
    else:
        # 3️⃣ Fetch fresh pages from Facebook Graph API
        user_access_token = os.getenv("ACCESS_TOKEN")
        if not user_access_token:
            raise Exception("ACCESS_TOKEN not found in environment variables")

        fb_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_access_token}"
        response = requests.get(fb_url)
        response.raise_for_status()

        pages_data = response.json()["data"]

        # 4️⃣ Store pages JSON temporarily in environment (not on disk)
        os.environ[PAGES_ENV_KEY] = json.dumps({"data": pages_data})
        print("🔐 FB pages stored safely in environment (not in file).")

    # 5️⃣ Find the matching page
    page = next((p for p in pages_data if p["id"] == page_id), None)
    if not page:
        raise Exception(f"Page ID {page_id} not found in the fetched Facebook pages list.")

    print(f"✅ Found Page: {page['name']} ({page['id']})")

    return page["id"], page["access_token"]


def clear_cached_facebook_pages():
    """Clear pages from environment after posting (optional)"""
    if PAGES_ENV_KEY in os.environ:
        del os.environ[PAGES_ENV_KEY]
        print("🧹 Cleared FB pages from environment memory.")
