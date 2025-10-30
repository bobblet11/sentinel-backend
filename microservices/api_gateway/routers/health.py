from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def healthz():
    """API Gateway health check"""
    return {"status": "ok"}
