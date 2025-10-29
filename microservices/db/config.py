import os
from dotenv import load_dotenv

load_dotenv()

# Service Configuration
SERVICE_PORT = int(os.getenv("DB_SERVICE_PORT", 8001))