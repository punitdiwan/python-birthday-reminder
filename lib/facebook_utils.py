import json
import os
import requests
from lib.db_manager import execute_query


def _fetch_pages(user_access_token: str) -> list[dict]:
    """Call Graph API once and return the list of pages."""
    fb_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_access_token}"
    resp = requests.get(fb_url)
    resp.raise_for_status()
    return resp.json()["data"]


def get_page_access_token(school_id: str) -> tuple[str, str]:
    """
    Return (page_id, page_access_token) for the given school.
    Pages are cached in the environment variable FB_PAGES_JSON.
    """
    # -------------------------------------------------
    # 1. Get the configured facebook_page_id
    # -------------------------------------------------
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

    # -------------------------------------------------
    # 2. Load / fetch pages into env var
    # -------------------------------------------------
    pages_json = os.getenv("FB_PAGES_JSON")
    if pages_json is None:
        user_token = os.getenv("ACCESS_TOKEN")
        if not user_token:
            raise Exception("ACCESS_TOKEN not found in environment variables")

        pages = _fetch_pages(user_token)
        os.environ["FB_PAGES_JSON"] = json.dumps(pages)   # store temporarily

    else:
        pages = json.loads(pages_json)

    # -------------------------------------------------
    # 3. Find the matching page
    # -------------------------------------------------
    page = next((p for p in pages if p["id"] == page_id), None)
    if not page:
        raise Exception(f"Page ID {page_id} not found in cached pages")

    print(f"Found Page: {page['name']} ({page['id']})")
    return page["id"], page["access_token"]


def cleanup_fb_pages() -> None:
    """Remove the temporary env-var after you are done."""
    os.environ.pop("FB_PAGES_JSON", None)