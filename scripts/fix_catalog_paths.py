#!/usr/bin/env python3
"""
Fix catalog.json paths to be relative URLs instead of absolute file paths.
Converts /home/salty/Projects/Librarybot/Bookcovers/ to ./covers/
"""

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).parent.parent / "webapp" / "catalog.json"
ABSOLUTE_PREFIX = "/home/salty/Projects/Librarybot/Bookcovers/"
RELATIVE_PREFIX = "./covers/"

def fix_paths():
    """Load catalog, fix paths, and save."""
    with open(CATALOG_PATH, "r") as f:
        data = json.load(f)
    
    fixed_count = 0
    for book in data.get("books", []):
        if book.get("cover_path") and book["cover_path"].startswith(ABSOLUTE_PREFIX):
            book["cover_path"] = RELATIVE_PREFIX + book["cover_path"][len(ABSOLUTE_PREFIX):]
            fixed_count += 1
    
    with open(CATALOG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"Fixed {fixed_count} cover paths in {CATALOG_PATH}")
    print(f"Conversion: {ABSOLUTE_PREFIX} → {RELATIVE_PREFIX}")

if __name__ == "__main__":
    fix_paths()
