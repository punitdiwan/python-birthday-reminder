from fastapi import FastAPI, UploadFile, File, Form
import logging
import os
import requests
import shutil
from lib.process_imag import replace_circle 
from lib.db_manager import execute_query


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
        with open(os.path.join(UPLOAD_DIR, "downloaded_image.png"), 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        logger.info("Image downloaded successfully.")
    else:
        logger.error("Failed to download image.")


# API endpoint to replace circle in image
@app.post("/replace-circle/")
async def replace_circle_api(school_id: str = Form(...), new_text: str = Form(...), base_img: UploadFile = File(...), circle_img: UploadFile = File(...), old_text:str = Form("www.reallygreatsite.com")) -> dict:
    # fee_categories = execute_query("SELECT _uid, batches, category_name FROM thekatarahillsschool.finance_fee_categories WHERE is_deleted = %s", (False,))  
    student_dob = execute_query(f"select photo, dob from {school_id}.students where is_deleted = false and TO_CHAR(CAST(dob AS DATE), 'MM-DD') = TO_CHAR(CURRENT_DATE, 'MM-DD')")
    for service in student_dob:
        logger.info(f"Student ID: {service['photo']}, DOB : {service['dob']}")
        _downloadPhoto(school_id, service['photo'])
        
    output_path = os.path.join(OUTPUT_DIR, f"result_{base_img.filename}")

    # Save base image
    with open(f"{UPLOAD_DIR}/saved_{base_img.filename}", "wb") as f:
        shutil.copyfileobj(base_img.file, f)

    # Save circle image
    with open(f"{UPLOAD_DIR}/saved_{circle_img.filename}", "wb") as f:
        shutil.copyfileobj(circle_img.file, f)

    # Call the replace_circle function
    result = replace_circle(
        f"{UPLOAD_DIR}/saved_{circle_img.filename}",
        f"{UPLOAD_DIR}/saved_{base_img.filename}",
        output_path,
        old_text,
        new_text
        )
    return {"output": result}

