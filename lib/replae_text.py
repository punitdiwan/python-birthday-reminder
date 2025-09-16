import cv2
import pytesseract
from PIL import Image, ImageDraw, ImageFont

# Load the image
input_path = "template.jpeg"
output_path = "output.jpeg"
image = cv2.imread(input_path)

# Convert to RGB for pytesseract
rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

# Run OCR
results = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)

# Word to replace
old_text = "www.reallygreatsite.com"
new_text = "Amit Shukla"

# # Loop through OCR results
# for i, word in enumerate(results["text"]):
#     if word.strip().lower() == old_text.lower():
#         x, y, w, h = results["left"][i], results["top"][i], results["width"][i], results["height"][i]
#
#         # Convert to PIL for drawing
#         pil_img = Image.fromarray(rgb)
#         draw = ImageDraw.Draw(pil_img)
#
#         # Step 1: Mask old text (white rectangle)
#         draw.rectangle([x, y, x + w, y + h], fill="white")
#
#         # Step 2: Write new text (adjust font path & size as needed)
#         font = ImageFont.truetype("Roboto-Regular.ttf", 28)
#         draw.text((x, y), new_text, font=font, fill="black")
#
#         # Save result
#         pil_img.save(output_path)
#         print(f"Replaced '{old_text}' with '{new_text}' and saved as {output_path}")
#         break
# else:
#     print(f"Could not find '{old_text}' in the image.")