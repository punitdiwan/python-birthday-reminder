import cv2
import pytesseract
import numpy as np
import os
from PIL import Image, ImageDraw, ImageFont

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
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, circle_diameter, circle_diameter), fill=255)

    # Apply mask to subject
    subject_circle = Image.new("RGBA", (circle_diameter, circle_diameter), (0, 0, 0, 0))
    subject_circle.paste(subject, (0, 0), mask=mask)

    # --- Step 3: Paste subject inside detected circle ---
    top_left_x = x_center - radius
    top_left_y = y_center - radius

    template.paste(subject_circle, (top_left_x, top_left_y), subject_circle)

    # --- Step 4: OCR text replacement ---
    # Convert to cv2 again for OCR
    template_cv = cv2.cvtColor(np.array(template), cv2.COLOR_RGBA2RGB)
    rgb = cv2.cvtColor(template_cv, cv2.COLOR_BGR2RGB)
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
            try:
                font = ImageFont.truetype("Roboto-Bold.ttf", 34)
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

    if not found:
        print(f"⚠ Could not find '{old_text}' in the image.")

    # --- Step 5: Save and cleanup ---
    pil_img.save(output_folder, format="PNG")

    # Removing the file after processing
    os.remove(poster_path)
    # os.remove(img_path)

    return {"Output": output_folder, "status": "true"}

