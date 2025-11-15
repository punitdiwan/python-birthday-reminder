from fastapi import FastAPI, UploadFile, File, Form
import logging
import os
import requests
import shutil
from lib.process_imag import replace_circle, capitalize_name, post_on_facebook, reset_output_folder
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


async def _get_photos(school_id: str) -> dict:
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
async def post_on_facebook_api(school_id: str = Form(...)) -> dict:
    """
    API endpoint to post generated images to Facebook for a specific school.
    """
    logger.info(f"Received request to post on Facebook for school: {school_id}")
    try:
        # The post_on_facebook function will now handle its own credential fetching
        results = post_on_facebook(output_folder="outputs", school_id=school_id)
        return {"output": results}
    except Exception as e:
        logger.error(f"Error posting on Facebook: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_birthday_pipeline", action="store_true")
    args = parser.parse_args()

    if args.run_birthday_pipeline:
        school_id = os.getenv("SCHOOL_ID")
        if not school_id:
            print("SCHOOL_ID not found in environment.")
            exit(1)

            print(f"Running birthday poster generator for {school_id}")

        # --------------------------------------------------------------
        # NEW: check facebook_page_id *before* any heavy work
        # --------------------------------------------------------------
        try:
            page_id, _ = get_page_access_token(school_id)
            print(f"Found FB page {page_id} – proceeding")
        except Exception as e:
            print(f"Skipping {school_id}: {e}")
            exit(0)
        # --------------------------------------------------------------

        reset_output_folder(OUTPUT_DIR)

        # 1. Fetch students with today's birthday
        students = execute_query(f"""
            SELECT full_name, photo, dob
            FROM {school_id}.students
            WHERE is_deleted = false
            AND length(photo) > 0
            AND TO_CHAR(CAST(dob AS DATE), 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')
        """)

        if not students:
            print(f"No birthdays today for {school_id}")
            exit(0)

        poster_path = "poster_template.jpg"
        for student in students:
            print(f"{student['full_name']} — {student['dob']}")
            _downloadPhoto(school_id, student['photo'])
            result = replace_circle(
                f"uploads/{student['photo']}",
                poster_path,
                "outputs",
                "Student",
                capitalize_name(student['full_name'])
            )
            print(f"Poster generated: {result}")

       # 2. Post all generated posters to Facebook
        print("Uploading to Facebook...")
        post_on_facebook(output_folder="outputs", school_id=school_id)

        # 2️⃣ Post on Facebook
        # fb_result = post_on_facebook()
        # print(f"📦 Facebook response: {fb_result}")
