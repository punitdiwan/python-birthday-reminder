import cv2
import requests
import pytesseract
import numpy as np
import os
from PIL import Image, ImageDraw, ImageFont
from glob import glob
from lib.facebook_utils import get_page_access_token


def add_name(poster_path:str, output_path:str, old_text:str, new_text:str) -> dict :
    image = cv2.imread(poster_path)

    # Convert to RGB for pytesseract
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Run OCR
    results = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)

    # Loop through OCR results
    for i, word in enumerate(results["text"]):
        if word.strip().lower() == old_text.lower():
            x, y, w, h = results["left"][i], results["top"][i], results["width"][i], results["height"][i]

            # Convert to PIL for drawing
            pil_img = Image.fromarray(rgb)
            draw = ImageDraw.Draw(pil_img)

            # Step 1: Mask old text (white rectangle)
            draw.rectangle([x, y, x + w, y + h], fill="white")

            # Step 2: Write new text (adjust font path & size as needed)
            font = ImageFont.truetype("Roboto-Regular.ttf", 28)
            draw.text((x, y), new_text, font=font, fill="black")

            # Save result
            pil_img.save(output_path)
            break
    else:
        print(f"Could not find '{old_text}' in the image.")

    return {"output": output_path}

# function to capitalize names
def capitalize_name(full_name: str) -> str:
    """
    Capitalizes the first character of a single word name, or both words if there are two words.
    Examples:
        'john' -> 'John'
        'john doe' -> 'John Doe'
    """
    if not full_name:
        return ''
    words = full_name.split()
    if len(words) == 1:
        return words[0].capitalize()
    elif len(words) == 2:
        return f"{words[0].capitalize()} {words[1].capitalize()}"
    else:
        # For more than two words, capitalize each word
        return ' '.join(word.capitalize() for word in words)

def replace_circle(img_path: str,  poster_path: str, output_folder: str, old_text:str, new_text:str ) -> dict:
    """
      Replace a detected circle in base image with an overlay image (circular cropped).
    """
    # Detect circle in template using OpenCV
    template_cv = cv2.imread(poster_path)
    grey = cv2.cvtColor(template_cv, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.medianBlur(grey, 5)

    # Detect circles (Hough Transform)
    circles = cv2.HoughCircles(
        gray_blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=1000,
        param1=50, param2=30,
        minRadius=100, maxRadius=400
        )
    if circles is None:
        raise Exception("Can't detect circles")

    circles = np.uint16(np.around(circles))
    x_center, y_center, radius = circles[0][0]
    print(f"Circle detected: center=({x_center},{y_center}), radius={radius}")

    # convert cv2 image -> PIL
    template = Image.fromarray(cv2.cvtColor(template_cv, cv2.COLOR_BGR2RGB)).convert("RGBA")
    subject = Image.open(img_path).convert("RGBA")

    # Diameter of circle
    circle_diameter = radius * 2

    # Resize subject to fit inside detected circle
    subject = subject.resize((circle_diameter, circle_diameter))

    # Create circular mask
    mask = Image.new("L", (circle_diameter, circle_diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, circle_diameter, circle_diameter), fill=255)

    # Apply mask to subject
    subject_circle = Image.new("RGBA", (circle_diameter, circle_diameter), (0, 0, 0, 0))
    subject_circle.paste(subject, (0, 0), mask=mask)

    # --- Step 3: Paste subject inside detected circle ---
    top_left_x = x_center - radius
    top_left_y = y_center - radius

    template.paste(subject_circle, (top_left_x, top_left_y), subject_circle)

    # --- Step 4: OCR text replacement ---
    rgb = cv2.cvtColor(np.array(template), cv2.COLOR_RGBA2RGB)
    results = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)

    pil_img = template.copy()
    draw = ImageDraw.Draw(pil_img)

    found = False
    for i, word in enumerate(results["text"]):
        if word.strip().lower() == old_text.lower():
            x, y, w, h = (
                results["left"][i],
                results["top"][i],
                results["width"][i],
                results["height"][i],
            )
            print(f"X Value {x}")
            print(f"Y Value {y}")
            print(f"Width Value {w}")
            print(f"Height Value {h}")

            # Mask old text
            draw.rectangle([x, y, x + w, y + h], fill="white")

            # Replace with new text
            # --- Step 4: Dynamic font scaling ---
            base_font_size = int(template.width * 0.05)  # 5% of width
            font_size = max(60, min(base_font_size, 120))  # clamp 60–120 px

            try:
                font = ImageFont.truetype("Roboto-Bold.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()

            # Get text size
            text_bbox = draw.textbbox((0, 0), new_text, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            # Center the text in the rectangle
            text_x = x + (w - text_w) // 2
            text_y = y + (h - text_h) // 2

            # draw.text((x, y), new_text, font=font, fill="black")
            draw.text((text_x, text_y), new_text, font=font, fill="black")

            found = True
            break

    # --- Step 5: Fallback if OCR text not found ---
    if not found:
        print(f"⚠ Could not find '{old_text}' in the image. Drawing name manually.")

        # Place name near bottom center of image
        base_font_size = int(template.width * 0.05)
        font_size = max(60, min(base_font_size, 120))

        try:
            font = ImageFont.truetype("Roboto-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), new_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        text_x = (template.width - text_w) // 2
        text_y = template.height - text_h - 120  # adjust margin
        draw.text((text_x, text_y), new_text, font=font, fill="black")

    # --- Step 6: Save output ---
    file_name = os.path.splitext(os.path.basename(img_path))[0] + ".png"
    os.makedirs(output_folder, exist_ok=True)
    save_path = os.path.join(output_folder, file_name)
    pil_img.save(save_path, format="PNG")
    print(f"✅ Saved: {save_path}")
    # Removing the file after processing
    #os.remove(poster_path)
    # os.remove(img_path)
    return {"Output": save_path, "status": "true"}


import requests
import os

def post_on_facebook(output_folder: str, school_id: str):
    from lib.facebook_utils import get_page_access_token

    page_id, access_token = get_page_access_token(school_id)
    if not page_id or not access_token:
        print(f"🚫 No access token for {school_id}")
        return None

    for file_name in os.listdir(output_folder):
        file_path = os.path.join(output_folder, file_name)
        if not os.path.isfile(file_path):
            continue

        print(f"📤 Uploading {file_name} to Facebook Page {page_id}...")
        try:
            with open(file_path, "rb") as image_file:
                url = f"https://graph.facebook.com/v23.0/{page_id}/feed"
                response = requests.post(
                    url,
                    files={"source": image_file},
                    data={
                        "caption": f"🎂 Happy Birthday from Our Whole School Family! 🎉",
                        "access_token": access_token,
                    },
                )
            response.raise_for_status()
            print(f"✅ Uploaded: {response.json()}")
        except Exception as e:
            print(f"❌ Failed to post {file_name}: {e}")
            print(f"Response: {getattr(e, 'response', None).text if hasattr(e, 'response') else 'No response'}")

    print("🎉 All posters uploaded directly to Facebook!")




def upload_file():
    url = "https://tmpfiles.org/api/v1/upload"
    file_path = "./cleanliness_day.jpg"

    with open(file_path, "rb") as f:
        files = {"file": f}
        resp = requests.post(url, files=files)

    return resp.json()