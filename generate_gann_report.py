import json

INPUT_FILE = "gann_library_raw.json"
OUTPUT_FILE = "Gann_Component_Library.md"

def generate_report():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Group by LogicType
    categorized = {}
    for entry in data:
        ltype = entry.get("LogicType", "Uncategorized")
        if ltype not in categorized:
            categorized[ltype] = []
        categorized[ltype].append(entry)

    # Start Markdown
    md = "# The Gann Component Library\n\n"
    md += "A deconstruction of the W.D. Gann Master Commodities Course.\n\n"

    # Define order
    order = ["MECHANICAL", "MATH", "GEOMETRY", "TIME", "VISUAL-LOGIC", "VEILED", "Visual-Logic"]

    for category in order:
        entries = categorized.get(category, [])
        if not entries:
            continue
        
        md += f"## {category} Components\n\n"
        md += f"| ID | Source | Definition / Rule | Params/Notes |\n"
        md += f"|---|---|---|---|\n"
        
        for item in entries:
            # Clean up text for table
            defi = item.get("AlgorithmicDefinition", "").replace("\n", " ")[:200]
            if len(defi) == 200: defi += "..."
            
            params = item.get("GeometricParameters", "")
            if params == "N/A": params = ""
            
            note = item.get("ContextVeilNote", "")
            if note: params += f" <br> *Note: {note}*"

            file_path = item.get("FilePath", "")
            if file_path:
                # Make it a clickable file link for local use
                params += f" <br> **[Open Image]({file_path})**"

            md += f"| {item['ComponentID']} | Pg {item['Page']} ({item['SourceType']}) | {defi} | {params} |\n"
        
        md += "\n"

    # Handle remaining categories if any
    others = [k for k in categorized if k not in order]
    if others:
        md += "## Other Components\n\n"
        for category in others:
            md += f"### {category}\n"
            md += f"| ID | Source | Definition | Params |\n"
            md += f"|---|---|---|---|\n"
            for item in categorized[category]:
                defi = item.get("AlgorithmicDefinition", "").replace("\n", " ")[:200]
                md += f"| {item['ComponentID']} | Pg {item['Page']} | {defi} | {item.get('GeometricParameters','')} |\n"
            md += "\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Report generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_report()
