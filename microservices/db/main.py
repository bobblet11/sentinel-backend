from fastapi import FastAPI
import logging
from config import SERVICE_PORT

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_service")

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
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=SERVICE_PORT)