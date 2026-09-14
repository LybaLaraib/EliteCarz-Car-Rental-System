import os
from dotenv import load_dotenv

# Environment values are loaded once and reused across the app.
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
