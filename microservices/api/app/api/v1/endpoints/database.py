from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import APIRouter
from microservices.api.app.crud.crud_db import DbStatus, health_check_db
from microservices.api.app.db.session import get_db

router = APIRouter()

@router.get("/status", status_code=status.HTTP_200_OK)
def database_status(db: Session = Depends(get_db)):
    """
    Checks the health of the database connection.
    """
    health: DbStatus = health_check_db(db)
    
    if health["status"] == "error":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health
        )
    
    return health
