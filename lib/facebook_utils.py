import os
import requests
from lib.db_manager import execute_query

def get_page_access_token(school_id: str):
    """
    Fetch the Facebook Page ID from the configurations table, and get the matching access token
    by calling the Graph API.
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

    # 2️⃣ Fetch pages from Facebook Graph API
    print("📥 Fetching page details from Facebook Graph API...")
    user_access_token = os.getenv("ACCESS_TOKEN")
    if not user_access_token:
        raise Exception("❌ ACCESS_TOKEN not found in environment variables")

    fb_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_access_token}"
    response = requests.get(fb_url)
    response.raise_for_status()
    
    pages_data = response.json()["data"]

    # 3️⃣ Find the matching page
    page = next((p for p in pages_data if p["id"] == page_id), None)
    if not page:
        raise Exception(f"Page ID {page_id} not found for the user's pages.")

    print(f"✅ Found Page: {page['name']} ({page['id']})")

    return page["id"], page["access_token"]
