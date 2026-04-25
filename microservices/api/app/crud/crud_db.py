from typing import TypedDict

from psycopg2 import OperationalError
from sqlalchemy import text
from sqlalchemy.orm import Session


class DbStatus(TypedDict):
    status: str
    message: str


def health_check_db(db: Session) -> DbStatus:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "message": "Database connection is healthy."}
    except OperationalError as e:
        return {"status": "error", "message": f"Database connection failed: {e}"}
    except Exception as e:
        return {
            "status": "error",
            "message": f"An unexpected database error occurred: {e}",
        }
