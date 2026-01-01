import fitz  # PyMuPDF
import re
import json
import os

PDF_PATH = "W.D. Gann Master Commodities Course.pdf"
OUTPUT_FILE = "gann_library_raw.json"

def extract_gann_components(pdf_path):
    doc = fitz.open(pdf_path)
    library_entries = []

    # Regex patterns for classification
    patterns = {
        "MATH": [
            r"\b\d{2,}\b",  # Significant numbers (simple heuristic, refine later)
            r"square of \d+",
            r"root of \d+",
            r"price level",
            r"range"
        ],
        "GEOMETRY": [
            r"\d+x\d+ angles?",
            r"\d+\s*degrees?",
            r"geometric",
            r"triangle",
            r"square",
            r"circle",
            r"45 deg"
        ],
        "TIME": [
            r"\d+\s*days?",
            r"\d+\s*weeks?",
            r"\d+\s*months?",
            r"\d+\s*years?",
            r"cycle",
            r"anniversary",
            r"season",
            r"periodic"
        ],
        "MECHANICAL": [
            r"buy\s+at",
            r"sell\s+at",
            r"stop\s+loss",
            r"if\s+.*then",
            r"rule \d+"
        ]
    }

    print(f"Analyzing {len(doc)} pages...")

    for page_num, page in enumerate(doc):
        text = page.get_text("text")  # Get plain text
        # Clean text slightly
        clean_text = re.sub(r'\s+', ' ', text).strip()
        
        # 1. Image Analysis Placeholder (detect presence)
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_ext = base_image["ext"]
            # We treat images as potential sources for Geometry/Visual-Logic
            entry = {
                "ComponentID": f"IMG_Pg{page_num+1}_{img_index+1}",
                "SourceType": "Image",
                "LogicType": "Visual-Logic",
                "GeometricParameters": f"Image Size: {base_image['width']}x{base_image['height']}",
                "AlgorithmicDefinition": "Visual verification required",
                "ContextVeilNote": "Check for handwritten angles or price/time scales.",
                "Page": page_num + 1,
                "RawContent": f"[Image Ref: xref {xref}]"
            }
            library_entries.append(entry)

        # 2. Text Analysis
        # Split text into sentences or roughly logical chunks for analysis
        # For now, we scan the whole page text for keywords to identify 'sections'
        
        # A simple sentence splitter
        sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', clean_text)
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue

            matches = {}
            for category, regex_list in patterns.items():
                for pattern in regex_list:
                    if re.search(pattern, sentence, re.IGNORECASE):
                        matches[category] = matches.get(category, []) + [pattern]

            if matches:
                # Determine primary logic type
                primary_logic = max(matches, key=lambda k: len(matches[k]))
                
                entry = {
                    "ComponentID": f"TXT_Pg{page_num+1}_{i}",
                    "SourceType": "Text",
                    "LogicType": primary_logic,
                    "GeometricParameters": "N/A" if primary_logic != "GEOMETRY" else f"Found: {matches['GEOMETRY']}",
                    "AlgorithmicDefinition": sentence, 
                    "ContextVeilNote": "Review for hidden meaning" if "VEILED" in matches else "",
                    "Page": page_num + 1,
                    "RawContent": sentence
                }
                library_entries.append(entry)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(library_entries, f, indent=2)
    
    print(f"Extraction complete. Found {len(library_entries)} potential components.")
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    if os.path.exists(PDF_PATH):
        extract_gann_components(PDF_PATH)
    else:
        print(f"Error: {PDF_PATH} not found.")
