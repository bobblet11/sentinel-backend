from logging import Logger, getLogger
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from microservices.api.app.core.config import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB, POSTGRES_PORT, POSTGRES_SSLMODE



logger:Logger = getLogger("postgres_session")

# We should replace localhost with our Docker host IP if we connect from a different machine.
# connection string format
# postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&param2=value2]
database_url:str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode={POSTGRES_SSLMODE}"

engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
   
def get_db() -> Session:
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

