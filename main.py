from fastapi import FastAPI, UploadFile, File, Form
import os
import shutil
from lib.process_imag import replace_circle

app = FastAPI()
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.post("/replace-circle/")
async def replace_circle_api( new_text: str = Form(...), base_img: UploadFile = File(...), circle_img: UploadFile = File(...), old_text:str = Form("www.reallygreatsite.com")) -> dict:
    print(f"Bas File name = {base_img.filename} and overlay file name =  {circle_img}.")

    base_path = os.path.join(UPLOAD_DIR, base_img.filename)
    circle_path = os.path.join(UPLOAD_DIR, circle_img.filename)
    output_path = os.path.join(OUTPUT_DIR, f"result_{base_img.filename}")

    # Save base image
    with open(f"{UPLOAD_DIR}/saved_{base_img.filename}", "wb") as f:
        shutil.copyfileobj(base_img.file, f)

    # Save circle image
    with open(f"{UPLOAD_DIR}/saved_{circle_img.filename}", "wb") as f:
        shutil.copyfileobj(circle_img.file, f)

    result = replace_circle(
        f"{UPLOAD_DIR}/saved_{circle_img.filename}",
        f"{UPLOAD_DIR}/saved_{base_img.filename}",
        output_path,
        old_text,
        new_text
        )
    return {"output": result}

