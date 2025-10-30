from fastapi import FastAPI
from logging import basicConfig, INFO, getLogger
from .config import SERVICE_PORT
import uvicorn

# Configure logging
basicConfig(level=INFO)
logger = getLogger("db_service")

# Initialize FastAPI app
app = FastAPI(
    title="Sentinel Database Service",
    version="0.1.0"
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "database"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "Sentinel Database Service", "version": "0.1.0"}

if __name__ == "__main__":
    uvicorn.run("microservices.db.main:app", host="0.0.0.0", port=SERVICE_PORT)
