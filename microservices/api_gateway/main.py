import logging

from config import CACHE_TTL, NLP_URL, WEB_SCRAPER_URL
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from routers import analysis, articles, database, health, sources
from utils.cache import get_cache, set_cache
from utils.helpers import httpx_encode, url_key
from utils.requests import fetch_json

app = FastAPI(title="Sentinel API Gateway", version="0.1")

logger = logging.getLogger("api_gateway")
logging.basicConfig(level=logging.INFO)

# Include routers
app.include_router(health.router)
app.include_router(database.router)
app.include_router(analysis.router)
app.include_router(articles.router)
app.include_router(sources.router)


# Legacy endpoint for backward compatibility
@app.get("/healthz")
async def healthz():
    """Legacy health check endpoint"""
    return {"status": "ok"}


# Legacy analyze endpoint for backward compatibility
@app.get("/analyze")
async def analyze(url: str = Query(..., description="URL of article to analyze")):
    """Legacy analyze endpoint - maintained for backward compatibility

    Note: New analyze logic is in /analysis/analyze router.
    This endpoint maintains the original implementation for existing clients.
    """
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
        analysis_result = await fetch_json(
            f"{NLP_URL}/analyze", method="POST", json=nlp_req
        )

        # store cache
        await set_cache(key, analysis_result, ttl=CACHE_TTL)

        return {"cached": False, "data": analysis_result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed analyze pipeline")
        raise HTTPException(status_code=500, detail=str(e))
