from fastapi import FastAPI, UploadFile, File, Form
import logging
import os
import requests
import shutil
from lib.process_imag import replace_circle, capitalize_name, post_on_facebook
from lib.db_manager import execute_query
from dotenv import load_dotenv
from lib.facebook_utils import get_page_access_token

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


# ---------------------- Download Photo ----------------------
def _downloadPhoto(school_id: str, photo_id: str):
    """
    Downloads a student's photo from DigitalOcean and saves it inside
    uploads/{school_id}/ to keep each school's data separate.
    """
    school_folder = os.path.join(UPLOAD_DIR, school_id)
    os.makedirs(school_folder, exist_ok=True)

    url = f"https://schoolerp-bucket.blr1.cdn.digitaloceanspaces.com/supa-img/{school_id}/students/{photo_id}?1758114330329"
    logger.info(f"Downloading image from URL: {url}")

    response = requests.get(url, stream=True)
    if response.status_code == 200:
        file_path = os.path.join(school_folder, photo_id)
        with open(file_path, "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)
        logger.info(f"✅ Image downloaded successfully: {file_path}")
        return file_path
    else:
        logger.error(f"❌ Failed to download image: {response.status_code}")
        return None


# ---------------------- Fetch Facebook Pages ----------------------
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


# ---------------------- Fetch Students ----------------------
async def _get_photos(school_id: str = Form(...)) -> dict:
    logger.info(f"Received request with school_id: {school_id}")

    students = execute_query(
        f"""
        SELECT full_name, photo, dob 
        FROM {school_id}.students
        WHERE is_deleted = false 
        AND length(photo) > 0
        AND TO_CHAR(CAST(dob AS DATE), 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')
        """
    )

    for student in students:
        logger.info(f" Student FullName: {student['full_name']}, Student Photo: {student['photo']}, DOB : {student['dob']}")
        _downloadPhoto(school_id, student['photo'])

    return {"output": students}


# ---------------------- FastAPI Endpoints ----------------------
@app.post("/replace-circle/")
async def replace_circle_api(
    school_id: str = Form(...),
    poster: UploadFile = File(...),
    old_text: str = Form("www.reallygreatsite.com")
) -> dict:
    logger.info(f"Received request with school_id: {school_id}, old_text: {old_text}")

    with open(f"{UPLOAD_DIR}/saved_{poster.filename}", "wb") as f:
        shutil.copyfileobj(poster.file, f)

    students = await _get_photos(school_id)
    if not students["output"]:
        return {"output": "No students with birthdays today."}

    results = []
    for student in students["output"]:
        student_photo_path = os.path.join(UPLOAD_DIR, school_id, student["photo"])
        try:
            result = replace_circle(
                student_photo_path,
                f"{UPLOAD_DIR}/saved_{poster.filename}",
                os.path.join(OUTPUT_DIR, school_id),
                old_text,
                capitalize_name(student["full_name"]),
            )
            results.append({"student": student["full_name"], "result": result})
        except Exception as e:
            logger.error(f"Error processing {student['photo']}: {e}")
            results.append({"student": student["full_name"], "error": str(e)})

    return {"output": results}


@app.post("/post-on-facebook/")
async def post_on_facebook_api() -> dict:
    logger.info("Received request to post on Facebook")
    try:
        response = post_on_facebook()
        return {"output": response}
    except Exception as e:
        logger.error(f"Error posting on Facebook: {e}")
        return {"error": str(e)}


# ---------------------- CLI Entry ----------------------
if __name__ == "__main__":
    import argparse
    from lib.process_imag import replace_circle, capitalize_name, post_on_facebook
    from lib.db_manager import execute_query

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_birthday_pipeline", action="store_true")
    args = parser.parse_args()

    if args.run_birthday_pipeline:
        school_id = os.getenv("SCHOOL_ID")
        if not school_id:
            print("❌ SCHOOL_ID not found in environment.")
            exit(1)

        print(f"🎂 Running birthday poster generator for {school_id}")

        # Define school-specific folders
        school_upload_dir = os.path.join(UPLOAD_DIR, school_id)
        school_output_dir = os.path.join(OUTPUT_DIR, school_id)

        # Cleanup previous runs
        for folder in [school_upload_dir, school_output_dir]:
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder, exist_ok=True)

        try:
            # 1️⃣ Fetch students
            students = execute_query(
                f"""
                SELECT full_name, photo, dob 
                FROM {school_id}.students
                WHERE is_deleted = false 
                AND length(photo) > 0
                AND TO_CHAR(CAST(dob AS DATE), 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')
                """
            )

            if not students:
                print(f"ℹ No birthdays today for {school_id}")
                shutil.rmtree(school_upload_dir, ignore_errors=True)
                shutil.rmtree(school_output_dir, ignore_errors=True)
                exit(0)

            poster_path = "poster_template.jpg"

            for student in students:
                print(f"🎉 {student['full_name']} — {student['dob']}")
                photo_path = _downloadPhoto(school_id, student["photo"])
                if not photo_path or not os.path.exists(photo_path):
                    logger.error(f"Photo missing for {student['full_name']}, skipping.")
                    continue

                result = replace_circle(
                    photo_path,
                    poster_path,
                    school_output_dir,
                    "www.reallygreatsite.com",
                    capitalize_name(student["full_name"]),
                )
                print(f"✅ Poster generated: {result}")

            # ✅ Facebook Upload
            page_id, access_token = get_page_access_token(school_id)

            if not page_id or not access_token:
                print(f"🚫 No access token for {school_id}. Skipping Facebook upload.")
            else:
                print("📤 Uploading to Facebook...")
                fb_result = post_on_facebook(output_folder=school_output_dir, school_id=school_id)
                print(f"📦 Facebook response: {fb_result}")

        except Exception as e:
            print(f"❌ Error processing {school_id}: {e}")

        finally:
            # 🧹 Always cleanup after every run
            shutil.rmtree(school_upload_dir, ignore_errors=True)
            shutil.rmtree(school_output_dir, ignore_errors=True)
            print(f"🧹 Cleaned up temporary files for {school_id}")

