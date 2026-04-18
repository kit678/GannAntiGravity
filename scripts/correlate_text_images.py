import fitz  # PyMuPDF
import json
import re

PDF_PATH = "W.D. Gann Master Commodities Course.pdf"
JSON_PATH = "gann_library_raw.json"

def correlate_text_and_images():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    doc = fitz.open(PDF_PATH)
    updated_count = 0

    print("Correlating text with images (looking back 1 page)...")

    for entry in data:
        if entry.get("SourceType") == "Image":
            page_num = entry.get("Page", 1) - 1  # 0-indexed for fitz
            if page_num < 0 or page_num >= len(doc):
                continue

            # Start with current page text
            current_text = doc[page_num].get_text("text").replace("\n", " ").strip()
            
            # Fetch previous page text if available
            prev_text = ""
            if page_num > 0:
                prev_text = doc[page_num - 1].get_text("text").replace("\n", " ").strip()

            # Combine: Previous + Current (Logic usually flows this way)
            # We add a marker to know where the split is
            combined_text = f"{prev_text} [PAGE BREAK] {current_text}"
            
            # Simple keyword extraction for geometric parameters
            geo_params = []
            
            # Look for Angles
            angles = re.findall(r"(\d+x\d+ angles?|\d+\s*degrees?)", combined_text, re.IGNORECASE)
            if angles:
                geo_params.append(f"Angles mentioned: {', '.join(set(angles))}")

            # Look for specific geometric shapes or patterns
            shapes = re.findall(r"(triangle|square|circle|cycle|resistance level)", combined_text, re.IGNORECASE)
            if shapes:
                geo_params.append(f"Concepts: {', '.join(set(shapes))}")

            # Update Entry
            if combined_text:
                # We prioritize text near "Chart" or "Figure" first, searching the whole block
                relevant_context = combined_text[:1000] + "..." # Increased context window
                
                # Check for "Chart" keyword proximity in the combined text
                match = re.search(r"([^.]*?Chart[^.]*\.)", combined_text, re.IGNORECASE)
                if match:
                    relevant_context = match.group(1)
                
                # Check if the result was mostly from previous page
                source_pages = f"Pages {page_num} & {page_num+1}"
                if len(current_text) < 50:
                    source_pages = f"Page {page_num} (Preceding)"

                entry["AlgorithmicDefinition"] = f"Context from {source_pages}: \"{relevant_context}\""
                
                if geo_params:
                    entry["GeometricParameters"] = " | ".join(geo_params)
                else:
                    entry["GeometricParameters"] = "See context text"

                updated_count += 1

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Updated {updated_count} image entries with contextual text.")

if __name__ == "__main__":
    correlate_text_and_images()
