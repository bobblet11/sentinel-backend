from fastapi import FastAPI
from routers import health, database, analysis, articles, sources
import logging

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
async def analyze_legacy(url: str):
    """Legacy analyze endpoint - use /analysis/analyze instead"""
    # Import here to avoid circular imports
    from fastapi import Query
    return await analysis.analyze(url)
