import logging
import os
import sys

from config import DB_SERVICE_URL
from fastapi import APIRouter
from utils.requests import fetch_json

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


router = APIRouter(prefix="/database", tags=["database"])
logger = logging.getLogger("api_gateway.database")


@router.get("/status")
async def database_status():
    """Check database service status"""
    try:
        # Call the database service health endpoint
        db_health = await fetch_json(f"{DB_SERVICE_URL}/health", method="GET")
        return {"database_service": db_health, "gateway_status": "connected"}
    except Exception as e:
        logger.error(f"Database service unreachable: {e}")
        return {
            "database_service": "unreachable",
            "gateway_status": "disconnected",
            "error": str(e),
        }
