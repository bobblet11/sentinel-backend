import requests
import time

API_BASE = "http://sentinel-api-service-container:8001"

TEST_URLS = [
    "https://www.bbc.com/sport/football/articles/c4g84l14e5eo",
    "https://www.bbc.com/news/live/c20dd5ynxz9t",   
        "https://www.bbc.com/news/articles/c4g44gj7rgno",
    "https://www.bbc.com/news/articles/cdxkk1vnp57o",
    "https://www.bbc.com/news/articles/cly0vk77vdko",
    "https://www.bbc.com/news/articles/cvg0z3n5e5jo",
    "https://www.bbc.com/news/articles/c5yj796plqmo",
    "https://www.bbc.com/news/articles/czjw2kz0l22o",
    "https://www.bbc.com/culture/article/20260414-10-of-the-most-iconic-images-of-pariss-secret-night-time-world",
    "https://www.bbc.com/news/articles/cm29plylqnvo",

]


def submit_job(url):
    payload = {
        "url": url
    }

    res = requests.post(
        f"{API_BASE}/api/v1/jobs",
        json={"article_url": url},
        timeout=30,
    )
    res.raise_for_status()

    data = res.json()
    uid = data.get("uid") or data.get("job_id")

    print(f"🚀 Submitted job for URL: {url}")
    print(f"UID: {uid}")
    return uid


def poll_result(uid, timeout=60):
    start = time.time()

    while time.time() - start < timeout:
        res = requests.get(f"{API_BASE}/jobs/{uid}")

        if res.status_code == 200:
            data = res.json()

            # adjust depending on your schema
            if data.get("status") == "complete" or data.get("retrieval_results"):
                print(f"✅ Completed job {uid}")
                return data

        time.sleep(2)

    print(f"⏰ Timeout waiting for job {uid}")
    return None


def print_result(data):
    if not data:
        print("❌ No data")
        return

    print("\n--- RESULT ---")

    # Adjust keys based on your actual response
    article = data.get("article") or {}
    claims = data.get("claims") or []
    results = data.get("retrieval_results") or {}

    print("Title:", article.get("title"))
    print("Author:", article.get("author"))
    print("Published:", article.get("published_at"))

    if article.get("text"):
        print("Text preview:", article["text"][:300])

    print("\nClaims:")
    for c in claims:
        print("-", c.get("text"))

    print("\nMatches:", len(results.get("matches", [])))


def run_e2e_tests():
    for url in TEST_URLS:
        print("\n" + "=" * 80)

        try:
            uid = submit_job(url)
            result = poll_result(uid)

            print_result(result)

        except Exception as e:
            print("💥 ERROR:", str(e))


if __name__ == "__main__":
    run_e2e_tests()