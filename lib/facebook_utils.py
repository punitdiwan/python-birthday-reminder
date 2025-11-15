import json
import os
import requests
from lib.db_manager import execute_query

PAGES_ENV_KEY = "FB_PAGES_JSON"   # will store all pages JSON as a string


def _fetch_pages_from_facebook() -> dict:
    """Fetch pages from Facebook Graph API and return JSON dict."""
    user_access_token = os.getenv("ACCESS_TOKEN")
    if not user_access_token:
        raise Exception("❌ ACCESS_TOKEN not found in environment variables")

    fb_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_access_token}"
    response = requests.get(fb_url)
    response.raise_for_status()

    return response.json()


def _load_pages_data() -> list:
    """
    Load pages JSON from environment variable.
    If not present, fetch from Facebook and store in env.
    """

    pages_str = os.getenv(PAGES_ENV_KEY)

    # 1️⃣ If not in env, fetch & store
    if not pages_str:
        print("📥 Fetching Facebook pages from API...")
        pages_json = _fetch_pages_from_facebook()
        os.environ[PAGES_ENV_KEY] = json.dumps(pages_json)   # store in env
        pages_str = os.environ[PAGES_ENV_KEY]

    # 2️⃣ Parse JSON
    pages_data = json.loads(pages_str).get("data", [])
    return pages_data


def clear_facebook_env_cache():
    """Clean environment variable once pipeline finishes."""
    if PAGES_ENV_KEY in os.environ:
        del os.environ[PAGES_ENV_KEY]
        print("🧹 Cleared Facebook pages environment cache.")


def get_page_access_token(school_id: str):
    """
    Fetch the Facebook Page ID from configurations and find it in the pages list stored in env.
    """

    # 1️⃣ Get the facebook_page_id from DB
    query = """
        SELECT config_value AS facebook_page_id
        FROM {0}.configurations
        WHERE config_key = 'facebook_page_id'
        AND _school = %s
        LIMIT 1
    """.format(school_id)

    result = execute_query(query, (school_id,))
    if not result:
        raise Exception(f"No facebook_page_id found for {school_id}")

    page_id = str(result[0]["facebook_page_id"])

    # 2️⃣ Load pages data from env (auto-fetch if needed)
    pages_data = _load_pages_data()

    # 3️⃣ Find matching page
    page = next((p for p in pages_data if p["id"] == page_id), None)
    if not page:
        raise Exception(f"Page ID {page_id} not found in environment pages")

    print(f"✅ Found Page: {page['name']} ({page['id']})")

    return page["id"], page["access_token"]



def school_has_facebook_page(school_id: str) -> bool:
    """Return True if school has a page ID in DB."""
    query = """
        SELECT config_value AS facebook_page_id
        FROM {0}.configurations
        WHERE config_key = 'facebook_page_id'
        AND _school = %s
        LIMIT 1
    """.format(school_id)

    result = execute_query(query, (school_id,))
    return bool(result and result[0]["facebook_page_id"])

