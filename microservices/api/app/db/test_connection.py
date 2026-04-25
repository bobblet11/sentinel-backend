from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from microservices.api.app.core.config import POSTGRES_HOST, POSTGRES_PORT
from microservices.api.app.db.session import engine


def test_connection():
    print(f"Testing connection to: {POSTGRES_HOST}:{POSTGRES_PORT}...")
    try:
        # establishing the connection explicitly
        with engine.connect() as connection:
            # execute a simple query to force a round-trip to the database
            result = connection.execute(text("SELECT 1"))
            print("\n✅ Connection Successful!")
            print(f"Test Query Result: {result.scalar()}")
    except OperationalError as e:
        print("\n❌ Connection Failed!")
        print(f"Error: {e}")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")

