from logging import Logger, getLogger
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from microservices.db_wrapper_api.config import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB, POSTGRES_PORT



logger:Logger = getLogger("connection_to_postgres")

# We should replace localhost with our Docker host IP if we connect from a different machine.
# connection string format
# postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&param2=value2]
database_url:str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
   
def get_db() -> Session:
	logger.info("Attemping to connect to postgres database")
	db = SessionLocal()
	logger.info("Successfully connected")
	try:
		yield db
	finally:
		db.close()

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

test_connection()
