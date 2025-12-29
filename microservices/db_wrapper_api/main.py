import uvicorn


from logging import DEBUG, INFO, Logger, basicConfig, getLogger
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from common.io.logging import setup_logging
from microservices.db_wrapper_api.src.setup.connect_to_postgres import get_db
from .config import DB_SERVICE_PORT

CONTAINER_NAME:str = "sentinel_db_service"
FAST_API_NAME:str = "Sentinel Database Service"
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
async def root(db: Session = Depends(get_db)):
    """Root endpoint"""
    return {"service": "Sentinel Database Service", "version": "0.1.0"}

if __name__ == "__main__":
    uvicorn.run("microservices.db_wrapper_api.main:app", host="0.0.0.0", port=DB_SERVICE_PORT)
