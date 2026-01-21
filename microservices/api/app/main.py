

from fastapi.responses import JSONResponse
from psycopg2 import IntegrityError, OperationalError
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from microservices.api.app.core.config import API_SERVICE_PORT
from microservices.api.app.api.v1.api import api_router

CONTAINER_NAME:str = "sentinel_api_service"
FAST_API_NAME:str = "Sentinel API Service"
FAST_API_VERSION:str = "0.0"

app = FastAPI(title=FAST_API_NAME, version=FAST_API_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "database"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "Sentinel Database Service", "version": "0.1.0"}

app.include_router(api_router, prefix="/api/v1")

# let any errors bubble to top!
@app.exception_handler(Exception)
async def sqlalchemy_exception_handler(request: Request, exc: Exception):
    """
    Catches and handles SQLAlchemy exceptions globally, returning a
    structured JSON error response.
    """
    # Default to a 500 Internal Server Error
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = "An unexpected internal server error occurred."

    # Be more specific for known database errors
    if isinstance(exc, IntegrityError):
        # This happens on unique constraint violations (e.g., duplicate article_url)
        status_code = status.HTTP_409_CONFLICT
        detail = "A job for this resource already exists."
        # You can add more specific parsing of exc.orig if needed
        # For example: if "unique constraint" in str(exc.orig).lower():

    elif isinstance(exc, OperationalError):
        # This happens if the database is down or unreachable
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        detail = "The database service is currently unavailable."

    # You can add more isinstance checks for other specific SQLAlchemy errors

    # Log the original exception for debugging purposes
    # import logging
    # logging.getLogger(__name__).error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )


if __name__ == "__main__":
    uvicorn.run("microservices.api.app.main:app", host="0.0.0.0", port=API_SERVICE_PORT)
