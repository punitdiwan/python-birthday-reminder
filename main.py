from fastapi import FastAPI, UploadFile, File, Form
import logging
import os
import requests
import shutil
from lib.process_imag import replace_circle, capitalize_name, post_on_facebook, reset_output_folder 
from lib.db_manager import execute_query
from dotenv import load_dotenv
from lib.facebook_utils import get_page_access_token
import sys
import json # Add to imports

# Load variables from .env file into environment
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Download photo from URL and save locally
def _downloadPhoto(school_id:str, photo_id: str):
    url = f"https://schoolerp-bucket.blr1.cdn.digitaloceanspaces.com/supa-img/{school_id}/students/{photo_id}?1758114330329"
    logger.info(f"Downloading image from URL: {url}")
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(os.path.join(UPLOAD_DIR, photo_id), 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        logger.info("Image downloaded successfully.")
    else:
        logger.error("Failed to download image.")


def fetch_and_store_pages(user_access_token: str, output_file="fb_pages.json"):
    """
    Fetch all pages the user manages and store the response to a JSON file.
    This should be done only once (or periodically).
    """
    fb_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_access_token}"
    response = requests.get(fb_url)
    response.raise_for_status()

    with open(output_file, "w") as f:
        f.write(response.text)

    print(f"✅ Facebook pages stored in {output_file}")
    return response.json()


async def _get_photos(school_id: str = Form(...)) -> dict:
    logger.info(f"Received request with school_id: {school_id}")

    # fee_categories = execute_query("SELECT _uid, batches, category_name FROM thekatarahillsschool.finance_fee_categories WHERE is_deleted = %s", (False,))  
    students = execute_query(f"select full_name, photo, dob from {school_id}.students where is_deleted = false and length(photo) > 0 and TO_CHAR(CAST(dob AS DATE), 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')")
    for student in students:
        logger.info(f" Student FullName: {student['full_name']}, Student Photo: {student['photo']}, DOB : {student['dob']}")
        _downloadPhoto(school_id, student['photo'])

    return {"output": students}

# API endpoint to replace circle in image
@app.post("/replace-circle/")
async def replace_circle_api(school_id: str = Form(...),  poster: UploadFile = File(...), old_text:str = Form("Student")) -> dict:
    logger.info(f"Received request with school_id: {school_id}, old_text: {old_text}")
    
    reset_output_folder(OUTPUT_DIR)

     # Save base image
    with open(f"{UPLOAD_DIR}/saved_{poster.filename}", "wb") as f:
        shutil.copyfileobj(poster.file, f)

    # Fetch Students image who has birthday today
    students = await _get_photos(school_id)
    if not students['output']:
        return {"output": "No students with birthdays today."}
  
    # Process each student photo
    results = []
    print(f"Students with birthdays today: {os.path.join(UPLOAD_DIR,students['output'][0]['photo'])}")
    for student in students['output']:
         student_photo_path = os.path.join(UPLOAD_DIR, student['photo'])
         try:
            result = replace_circle(
                student_photo_path,
                f"{UPLOAD_DIR}/saved_{poster.filename}",
                OUTPUT_DIR,
                old_text,
                capitalize_name(student['full_name'])
            )
            results.append({"student": student['full_name'], "result": result})
         except Exception as e:
             logger.error(f"Error processing {student['photo']}: {e}")
             results.append({"student": student['full_name'], "error": str(e)})
    
    return {"output": results}

@app.post("/post-on-facebook/")
async def post_on_facebook_api() -> dict:
    logger.info("Received request to post on Facebook")
    try:
        results = post_on_facebook()          # <-- now returns list of dicts
        return {"output": results}
    except Exception as e:
        logger.error(f"Error posting on Facebook: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    from lib.process_imag import replace_circle, capitalize_name, post_on_facebook
    from lib.db_manager import execute_query
    from lib.facebook_utils import get_page_access_token   

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_birthday_pipeline", action="store_true")
    parser.add_argument("--schools_list", type=str)
    args = parser.parse_args()

    if args.run_birthday_pipeline:
        # 1. Load school list
        school_list = []
        if args.schools_list and os.path.exists(args.schools_list):
            with open(args.schools_list, "r") as f:
                school_list = [line.strip() for line in f if line.strip()]
        elif os.getenv("SCHOOL_ID"):
            school_list = [os.getenv("SCHOOL_ID")]
        else:
            print("❌ No schools found. Provide --schools_list.")
            sys.exit(1)

        # ─────────────────────────────────────────────────────────────
        # 2. VALIDATE FACEBOOK TOKEN ONCE — fail the entire pipeline
        #    immediately if the token is expired/invalid.
        # ─────────────────────────────────────────────────────────────
        user_access_token = os.getenv("FB_USER_ACCESS_TOKEN")
        if not user_access_token:
            print("❌ FB_USER_ACCESS_TOKEN env var is not set.")
            sys.exit(1)

        print("🔑 Validating Facebook user access token...")
        token_check = requests.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={"access_token": user_access_token}
        )
        if token_check.status_code != 200:
            fb_error = token_check.json().get("error", {})
            print(f"❌ Facebook token is invalid or expired!")
            print(f"   Code: {fb_error.get('code')} | Message: {fb_error.get('message')}")
            print("   👉 Renew the token and update the GitHub secret FB_USER_ACCESS_TOKEN.")
            sys.exit(1)  

        all_fb_pages = token_check.json()
        print(f"✅ Token valid. Found {len(all_fb_pages.get('data', []))} FB pages.")

        # Save once for the session (facebook_utils can read this)
        with open("fb_pages.json", "w") as f:
            json.dump(all_fb_pages, f, indent=2)

        # ─────────────────────────────────────────────────────────────
        # 3. BULK FETCH all FB page configs in ONE DB query
        # ─────────────────────────────────────────────────────────────
        print(f"\n📦 Fetching Facebook page configs for all {len(school_list)} schools in one query...")

        # Build a single UNION ALL query across all school schemas
        union_parts = [
            f"""
            SELECT '{school_id}' AS school_id, config_value AS facebook_page_id
            FROM {school_id}.configurations
            WHERE config_key = 'facebook_page_id' AND _school = '{school_id}'
            LIMIT 1
            """
            for school_id in school_list
        ]
        bulk_query = " UNION ALL ".join(union_parts)

        try:
            fb_config_rows = execute_query(bulk_query)
            # Build a dict: school_id -> facebook_page_id
            fb_config_map = {
                row["school_id"]: row["facebook_page_id"]
                for row in fb_config_rows
                if row.get("facebook_page_id")
            }
        except Exception as e:
            print(f"❌ Failed to fetch FB configs from DB: {e}")
            sys.exit(1)

        print(f"✅ Got Facebook page configs for {len(fb_config_map)} schools.")

        # ─────────────────────────────────────────────────────────────
        # 4. Pipeline
        # ─────────────────────────────────────────────────────────────
        ARTIFACTS_ROOT = "birthday-posts"
        FAILURE_LOG_FILE = "school-failures.json"

        if os.path.exists(ARTIFACTS_ROOT):
            shutil.rmtree(ARTIFACTS_ROOT)
        os.makedirs(ARTIFACTS_ROOT, exist_ok=True)

        failed_schools = []
        success_count = 0

        for school_id in school_list:
            print("\n" + "="*50)
            print(f"🏫 Processing school: {school_id}")
            print("="*50)

            # Skip schools with no FB page config (no DB call needed)
            if school_id not in fb_config_map:
                print(f"⚠️ Skipping {school_id}: No facebook_page_id configured in DB.")
                continue

            school_output_dir = os.path.join(ARTIFACTS_ROOT, school_id)
            os.makedirs(school_output_dir, exist_ok=True)
            failure_record = {"school": school_id, "error": None}

            try:
                # Fetch today's birthdays (per-school query — unavoidable)
                students = execute_query(f"""
                    SELECT full_name, photo, dob 
                    FROM {school_id}.students
                    WHERE is_deleted = false 
                      AND photo IS NOT NULL AND length(photo) > 0
                      AND dob IS NOT NULL AND dob <> ''
                      AND EXTRACT(MONTH FROM dob::date) = EXTRACT(MONTH FROM CURRENT_DATE)
                      AND EXTRACT(DAY   FROM dob::date) = EXTRACT(DAY   FROM CURRENT_DATE)
                """)

                if not students:
                    print(f"ℹ️ No birthdays today for {school_id}")
                    os.rmdir(school_output_dir)
                    continue

                poster_path = "poster_template.jpg"
                posters_created = False

                for student in students:
                    print(f"🎂 Processing: {student['full_name']}")
                    try:
                        _downloadPhoto(school_id, student['photo'])
                        replace_circle(
                            f"uploads/{student['photo']}",
                            poster_path,
                            school_output_dir,
                            "Student",
                            capitalize_name(student['full_name'])
                        )
                        print(f"🖼️ Poster generated at: {school_output_dir}")
                        posters_created = True
                    except Exception as img_err:
                        print(f"❌ Image Error ({student['full_name']}): {img_err}")

                if posters_created:
                    print(f"📤 Uploading from {school_output_dir} to Facebook...")
                    post_on_facebook(output_folder=school_output_dir, school_id=school_id)
                    success_count += 1
                else:
                    if os.path.exists(school_output_dir) and not os.listdir(school_output_dir):
                        os.rmdir(school_output_dir)

            except Exception as e:
                logger.error(f"❌ CRITICAL FAILURE for {school_id}: {e}")
                failure_record["error"] = str(e)
                failed_schools.append(failure_record)

        # 5. Summary
        print("\n" + "#"*50)
        print(f"🏁 Pipeline Finished.")
        print(f"✅ Successful: {success_count}")
        print(f"❌ Failed: {len(failed_schools)}")

        with open(FAILURE_LOG_FILE, "w") as f:
            json.dump(failed_schools, f, indent=4)

        sys.exit(1 if failed_schools else 0)
