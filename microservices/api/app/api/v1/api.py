from fastapi import APIRouter
from microservices.api.app.api.v1.endpoints import jobs
from microservices.api.app.api.v1.endpoints import database
from microservices.api.app.api.v1.endpoints import topics

api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(database.router, prefix="/database", tags=["database"])
api_router.include_router(topics.router, prefix="/topics", tags=["topics"])
