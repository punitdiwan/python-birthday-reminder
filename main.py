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
    parser.add_argument("--schools_list", type=str, help="Path to file containing list of school IDs")
    args = parser.parse_args()

    if args.run_birthday_pipeline:
        school_list = []
        if args.schools_list and os.path.exists(args.schools_list):
            with open(args.schools_list, "r") as f:
                school_list = [line.strip() for line in f if line.strip()]
        elif os.getenv("SCHOOL_ID"):
            school_list = [os.getenv("SCHOOL_ID")]
        else:
            print("❌ No schools found. Provide --schools_list.")
            exit(1)

        print(f"🚀 Starting pipeline for {len(school_list)} schools...")

        # 2. Setup Artifacts Root Directories
        # We create a main folder that will hold subfolders for each school
        ARTIFACTS_ROOT = "birthday-posts" 
        FAILURE_LOG_FILE = "school-failures.json"
        
        # Clean start: remove root folder if it exists to prevent old files
        if os.path.exists(ARTIFACTS_ROOT):
            shutil.rmtree(ARTIFACTS_ROOT)
        os.makedirs(ARTIFACTS_ROOT, exist_ok=True)

        failed_schools = []
        success_count = 0

        # 3. Process Loop
        for school_id in school_list:
            print("\n" + "="*50)
            print(f"🏫 Processing school: {school_id}")
            print("="*50)

            # Create a UNIQUE folder for this specific school
            # Example: birthday-posts/minervaschool/
            school_output_dir = os.path.join(ARTIFACTS_ROOT, school_id)
            os.makedirs(school_output_dir, exist_ok=True)

            failure_record = {"school": school_id, "error": None}

            try:
                # A. Validate Facebook Config
                try:
                    page_id, _ = get_page_access_token(school_id)
                except Exception as e:
                    print(f"⚠️ Skipping {school_id}: {e}")
                    # If we skip, we remove the empty folder to keep artifacts clean
                    os.rmdir(school_output_dir) 
                    continue 

                # B. Fetch Students
                students = execute_query(f"""
                    SELECT full_name, photo, dob 
                    FROM {school_id}.students
                    WHERE is_deleted = false 
                      AND photo IS NOT NULL
                      AND length(photo) > 0
                      AND dob IS NOT NULL
                      AND EXTRACT(MONTH FROM dob::date) = EXTRACT(MONTH FROM CURRENT_DATE)
                      AND EXTRACT(DAY FROM dob::date) = EXTRACT(DAY FROM CURRENT_DATE);
                """)

                if not students:
                    print(f"ℹ️ No birthdays today for {school_id}")
                    os.rmdir(school_output_dir) # Clean up empty folder
                    continue

                poster_path = "poster_template.jpg"
                posters_created = False

                # C. Generate Posters -> INTO UNIQUE SCHOOL FOLDER
                for student in students:
                    print(f"🎂 Processing: {student['full_name']}")
                    try:
                        _downloadPhoto(school_id, student['photo'])
                        
                        # We pass 'school_output_dir' instead of generic 'outputs'
                        result = replace_circle(
                            f"uploads/{student['photo']}",
                            poster_path,
                            school_output_dir,  # <--- ISOLATION HAPPENS HERE
                            "Student",
                            capitalize_name(student['full_name'])
                        )
                        print(f"🖼️ Poster generated at: {school_output_dir}")
                        posters_created = True
                    except Exception as img_err:
                        print(f"❌ Image Error ({student['full_name']}): {img_err}")

                # D. Upload -> FROM UNIQUE SCHOOL FOLDER
                if posters_created:
                    print(f"📤 Uploading from {school_output_dir} to Facebook...")
                    
                    # Ensure the uploader only looks at this school's folder
                    post_on_facebook(output_folder=school_output_dir, school_id=school_id)
                    
                    success_count += 1
                else:
                    # If no posters were made (errors), remove folder
                    if os.path.exists(school_output_dir) and not os.listdir(school_output_dir):
                         os.rmdir(school_output_dir)

            except Exception as e:
                logger.error(f"❌ CRITICAL FAILURE for {school_id}: {e}")
                failure_record["error"] = str(e)
                failed_schools.append(failure_record)

        # 4. Save Failure Log
        print("\n" + "#"*50)
        print(f"🏁 Pipeline Finished.")
        print(f"✅ Successful: {success_count}")
        print(f"❌ Failed: {len(failed_schools)}")

        with open(FAILURE_LOG_FILE, "w") as f:
            json.dump(failed_schools, f, indent=4)

        if failed_schools:
            sys.exit(1)
        else:
            sys.exit(0)
