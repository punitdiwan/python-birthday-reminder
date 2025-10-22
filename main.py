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
async def replace_circle_api(school_id: str = Form(...),  poster: UploadFile = File(...), old_text:str = Form("www.reallygreatsite.com")) -> dict:
    logger.info(f"Received request with school_id: {school_id}, old_text: {old_text}")
    
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
        response = post_on_facebook()
        return {"output": response}
    except Exception as e:
        logger.error(f"Error posting on Facebook: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    from lib.process_imag import replace_circle, capitalize_name, post_on_facebook
    from lib.db_manager import execute_query
    import shutil

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

        # Cleanup any old files from previous runs
        for folder in [school_upload_dir, school_output_dir]:
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder, exist_ok=True)

        try:
            # 1️⃣ Fetch students with today's birthday
            students = execute_query(f"""
                SELECT full_name, photo, dob 
                FROM {school_id}.students
                WHERE is_deleted = false 
                AND length(photo) > 0
                AND TO_CHAR(CAST(dob AS DATE), 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')
            """)

            if not students:
                print(f"ℹ No birthdays today for {school_id}")
                # Cleanup even if no students found
                shutil.rmtree(school_upload_dir, ignore_errors=True)
                shutil.rmtree(school_output_dir, ignore_errors=True)
                exit(0)

            poster_path = "poster_template.jpg"  # ensure template exists

            for student in students:
                print(f"🎉 {student['full_name']} — {student['dob']}")
                _downloadPhoto(school_id, student['photo'])
                result = replace_circle(
                    f"{school_upload_dir}/{student['photo']}",
                    poster_path,
                    school_output_dir,
                    "www.reallygreatsite.com",
                    capitalize_name(student['full_name'])
                )
                print(f"✅ Poster generated: {result}")

            # ✅ Get Page ID & Access Token for this school
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
            # 🧹 Always clean up after each school — success or fail
            shutil.rmtree(school_upload_dir, ignore_errors=True)
            shutil.rmtree(school_output_dir, ignore_errors=True)
            print(f"🧹 Cleaned up temporary files for {school_id}")

