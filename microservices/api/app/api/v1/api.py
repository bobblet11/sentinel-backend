from fastapi import APIRouter
from microservices.api.app.api.v1.endpoints import jobs
from microservices.api.app.api.v1.endpoints import database
from microservices.api.app.api.v1.endpoints import topics
from microservices.api.app.api.v1.endpoints.articles import router as articles_router, outlets_router

api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(database.router, prefix="/database", tags=["database"])
api_router.include_router(topics.router, prefix="/topics", tags=["topics"])
api_router.include_router(articles_router, prefix="/articles", tags=["articles"])
api_router.include_router(outlets_router, prefix="/outlets", tags=["outlets"])
