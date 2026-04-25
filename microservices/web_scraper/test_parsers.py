import requests
from bs4 import BeautifulSoup

# from microservices.web_scraper.parsers.CNN_parser import CNNParser  # if exists
from microservices.web_scraper.parsers.ABC_parser import ABCParser
from microservices.web_scraper.parsers.BBC_parser import BBCParser
from microservices.web_scraper.parsers.CBC_parser import CBCParser
from microservices.web_scraper.parsers.CBS_parser import CBSParser
from microservices.web_scraper.parsers.Euronews_parser import EuronewsParser
from microservices.web_scraper.parsers.NBC_parser import NBCParser
from microservices.web_scraper.parsers.NPR_parser import NPRParser
from microservices.web_scraper.parsers.The_Guardian_parser import \
    TheGuardianParser

PARSER_MAP = {
    "bbc": BBCParser(),
    "abc": ABCParser(),
    "cbc": CBCParser(),
    "cbs": CBSParser(),
    "npr": NPRParser(),
    "nbc": NBCParser(),
    "euronews": EuronewsParser(),
    "guardian": TheGuardianParser(),
}


TEST_URLS = {
    "bbc": "https://www.bbc.com/news/articles/c937gd1vq7xo",
    "abc": "https://abcnews.com/Politics/senate-passes-bill-fund-dhs-except-ice-parts/story?id=131461819",
    "cbc": "https://www.cbc.ca/news/world/iran-strikes-military-base-us-troops-wounded-9.7145616",
    "cbs": "https://www.cbsnews.com/news/michael-jordan-nascar-lawsuit-vision-for-sport-gayle-king-interview/",
    "npr": "https://www.npr.org/2026/03/26/nx-s1-5762974/education-department-building",
    "nbc": "https://www.nbcnews.com/politics/trump-administration/trump-johnson-dhs-house-rebels-senate-bill-ice-cbp-rcna265507",
    "euronews": "https://www.euronews.com/2026/03/30/trump-threatens-to-obliterate-irans-kharg-island-oil-hub-if-no-deal-reached-shortly",
    "guardian": "https://www.theguardian.com/world/2026/mar/30/egypt-pakistan-saudi-arabia-turkey-talks-embryo-new-order",
}


def fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    return res.text


def validate_result(result, url):
    errors = []

    if not result:
        errors.append("❌ No result returned")
        return errors

    if not result.text or len(result.text) < 200:
        errors.append("❌ Text too short")

    if not result.title:
        errors.append("❌ Missing title")

    if not result.author:
        errors.append("❌ Missing author")

    if not result.published_at:
        errors.append("❌ Missing published_at")

    return errors


def run_tests():
    for outlet, parser in PARSER_MAP.items():
        url = TEST_URLS[outlet]

        print("\n" + "=" * 80)
        print(f"🧪 Testing: {outlet.upper()}")
        print(f"URL: {url}")

        try:
            html = fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")

            result = parser.extract(soup, url)

            errors = validate_result(result, url)

            if errors:
                print("⚠️ Issues found:")
                for e in errors:
                    print("   ", e)
            else:
                print("✅ PASSED")

            if result:
                print("\n--- OUTPUT PREVIEW ---")
                print("Title:", result.title)
                print("Author:", result.author)
                print("Published:", result.published_at)
                print("Text preview:", result.text[:300])

        except Exception as e:
            print("💥 CRASHED:", str(e))


if __name__ == "__main__":
    run_tests()