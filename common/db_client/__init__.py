import os
from dotenv import load_dotenv

load_dotenv()

# Database Configuration - moved from microservices/db/config.py for sharing
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "sentinel_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "sentinel_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "sentinel_password")
