import uvicorn


from logging import DEBUG, Logger, getLogger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from common.io.logging import setup_logging
from microservices.api.app.api.v1.api import api_router
from microservices.api.app.core.config import API_SERVICE_PORT

CONTAINER_NAME:str = "sentinel_api_service"
FAST_API_NAME:str = "Sentinel API Service"
FAST_API_VERSION:str = "0.0"

setup_logging(level=DEBUG,container_name=CONTAINER_NAME)
logger:Logger = getLogger("__main__")

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

if __name__ == "__main__":
    uvicorn.run("microservices.api.app.main:app", host="0.0.0.0", port=API_SERVICE_PORT)
