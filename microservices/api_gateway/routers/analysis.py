# routers/analysis.py
import os
import sys
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

# Allow running this module directly or via relative import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CACHE_TTL, NLP_URL, WEB_SCRAPER_URL
from utils.cache import get_cache, set_cache
from utils.helpers import httpx_encode, url_key
from utils.requests import fetch_json

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger("api_gateway.analysis")


@router.get("/analyze")
async def analyze(url: str = Query(..., description="URL of the article to analyze")):
    """
    Run the analysis pipeline for a given article URL.

    Steps:
      1. Check Redis cache (avoid redundant processing)
      2. Scrape the article text via the Web Scraper service
      3. Send the scraped content to the NLP service for analysis
      4. Cache and return the combined result
    """
    key = url_key(url)

    # Check Redis cache first
    cached = await get_cache(key)
    if cached:
        return JSONResponse({"cached": True, "data": cached})

    try:
        # Scrape article content
        scrape_url = f"{WEB_SCRAPER_URL}/scrape?url={httpx_encode(url)}"
        scraped = await fetch_json(scrape_url, method="GET")
        if not scraped or "content" not in scraped:
            raise HTTPException(status_code=502, detail="Scraper returned no content")

        # Send scraped text to NLP service
        nlp_req = {"url": url, "content": scraped}
        analysis = await fetch_json(f"{NLP_URL}/analyze", method="POST", json=nlp_req)

        # Cache the result
        await set_cache(key, analysis, ttl=CACHE_TTL)

        return {"cached": False, "data": analysis}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in analysis pipeline")
        raise HTTPException(status_code=500, detail=str(e))
