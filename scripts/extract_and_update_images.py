import fitz  # PyMuPDF
import json
import re
import os

PDF_PATH = "W.D. Gann Master Commodities Course.pdf"
JSON_PATH = "gann_library_raw.json"
IMAGE_DIR = r"c:\Dev\GannTesting\extracted_images"

def extract_and_update():
    # Load JSON
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    doc = fitz.open(PDF_PATH)
    updated_count = 0

    print(f"Processing {len(data)} entries...")

    for entry in data:
        if entry.get("SourceType") == "Image":
            raw_content = entry.get("RawContent", "")
            # Extract xref
            match = re.search(r"xref (\d+)", raw_content)
            if match:
                xref = int(match.group(1))
                component_id = entry.get("ComponentID")
                
                try:
                    # Extract image
                    img = doc.extract_image(xref)
                    if img:
                        ext = img["ext"]
                        image_filename = f"{component_id}.{ext}"
                        image_path = os.path.join(IMAGE_DIR, image_filename)
                        
                        # Write bytes
                        with open(image_path, "wb") as img_file:
                            img_file.write(img["image"])
                        
                        # Update JSON entry
                        entry["FilePath"] = image_path
                        updated_count += 1
                        
                except Exception as e:
                    print(f"Failed to extract {component_id} (xref {xref}): {e}")

    # Save updated JSON
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Successfully extracted and updated {updated_count} images.")

if __name__ == "__main__":
    extract_and_update()
