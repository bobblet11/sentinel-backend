from fastapi import APIRouter
from microservices.api.app.api.v1.endpoints import jobs 
from microservices.api.app.api.v1.endpoints import results 

api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(results.router, prefix="/results", tags=["results"])
