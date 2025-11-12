import logging
import os
import sys

from config import CACHE_TTL, NLP_URL, WEB_SCRAPER_URL
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from utils.cache import get_cache, set_cache
from utils.helpers import httpx_encode, url_key
from utils.requests import fetch_json

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger("api_gateway.analysis")


@router.get("/analyze")
async def analyze(url: str = Query(..., description="URL of article to analyze")):
    """Analyze article content from URL"""
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
