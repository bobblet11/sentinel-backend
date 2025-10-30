from os import getenv
from dotenv import load_dotenv

load_dotenv()

# Service Configuration
SERVICE_PORT = int(getenv("DB_SERVICE_PORT", 8001))

# not currently in use
POSTGRES_HOST = getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = getenv("POSTGRES_DB", "sentinel_db")
POSTGRES_USER = getenv("POSTGRES_USER", "sentinel_user")
POSTGRES_PASSWORD = getenv("POSTGRES_PASSWORD", "sentinel_password")
