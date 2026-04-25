# microservices/web_scraper/managers/test_script.py

import glob
import os

from microservices.web_scraper.managers.parse_manager import ParseManager

# --- MAP FILENAMES TO REALISTIC DOMAIN URLs ---
DOMAIN_MAP = {
    "nyt.html": "https://www.nytimes.com/mock-article",
    "washingtonpost.html": "https://www.washingtonpost.com/mock-article",
    "wsj.html": "https://www.wsj.com/articles/mock-article",
    "random.html": "https://www.randomnews.com/article/mock-article",
}

def infer_url(path: str) -> str:
    """Return the correct domain URL based on the filename."""
    filename = os.path.basename(path).lower()
    return DOMAIN_MAP.get(filename, None)

def run_file(path):
    print("\n==============================")
    print("TESTING:", path)
    print("==============================\n")

    with open(path, "r", encoding="utf8") as f:
        html = f.read()

    url = infer_url(path)

    # --- DEBUG: Show which URL is being passed ---
    print("[TestScript] URL passed into ParseManager:", url)

    pm = ParseManager()
    parsed = pm.parse_article_html(html, url=url)

    print("Title:", parsed.get("title"))
    print("Author:", parsed.get("author"))
    print("Published:", parsed.get("published_at"))
    print("Words:", len(parsed.get("text", "").split()))
    print("Preview:", parsed.get("text", ""))
    print("\n")

if __name__ == "__main__":
    for file_path in glob.glob("microservices/web_scraper/test_html/*.html"):
        run_file(file_path)
