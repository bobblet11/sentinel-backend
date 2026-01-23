# microservices/api_gateway/main.py
import logging

from fastapi import FastAPI 
from microservices.api_gateway.routers import analysis, articles, database, health, sources

from common.io.logging import setup_logging

app = FastAPI(title="Sentinel API Gateway", version="0.1")

setup_logging(
    level=logging.INFO,
    container_name="api-gateway"
)

logger = logging.getLogger(__name__)

# Include routers
app.include_router(health.router)
app.include_router(database.router)
app.include_router(analysis.router)
app.include_router(articles.router)
app.include_router(sources.router)


