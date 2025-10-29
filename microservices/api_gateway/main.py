from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from utils.cache import get_cache, set_cache
from utils.requests import fetch_json
from config import WEB_SCRAPER_URL, NLP_URL, CACHE_TTL
import logging
import hashlib

app = FastAPI(title="Sentinel API Gateway", version="0.1")

logger = logging.getLogger("api_gateway")
logging.basicConfig(level=logging.INFO)


def url_key(u: str) -> str:
    # deterministic cache key for URL
    h = hashlib.sha256(u.encode("utf-8")).hexdigest()
    return f"analysis:{h}"


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/analyze")
async def analyze(url: str = Query(..., description="URL of article to analyze")):
    key = url_key(url)

    # 1) Check cache
    cached = await get_cache(key)
    if cached:
        return JSONResponse({"cached": True, "data": cached})

    # 2) Orchestrate: scrape -> nlp -> combine
    try:
        # call scraper
        scrape_url = f"{WEB_SCRAPER_URL}/scrape?url={httpx_encode(url)}"
        scraped = await fetch_json(scrape_url, method="GET")
        if not scraped or "content" not in scraped:
            raise HTTPException(status_code=502, detail="Scraper returned no content")

        # call NLP
        nlp_req = {"url": url, "content": scraped}
        analysis = await fetch_json(f"{NLP_URL}/analyze", method="POST", json=nlp_req)

        # store cache
        await set_cache(key, analysis, ttl=CACHE_TTL)

        return {"cached": False, "data": analysis}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed analyze pipeline")
        raise HTTPException(status_code=500, detail=str(e))


# small helper to urlencode manually (avoid importing heavy libs)
def httpx_encode(u: str) -> str:
    import urllib.parse
    return urllib.parse.quote_plus(u)
