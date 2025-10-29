from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["sources"])


# Future endpoints will be added here following the DATABASE_OPERATIONS_GUIDE.md
# Examples (DO NOT IMPLEMENT YET):
#
# @router.get("/", response_model=List[SourceResponse])
# async def list_sources():
#     """List RSS sources"""
#     pass
#
# @router.post("/", response_model=SourceResponse)
# async def create_source(source: SourceCreate):
#     """Create new RSS source"""
#     pass