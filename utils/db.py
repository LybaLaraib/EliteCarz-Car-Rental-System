from pymongo import MongoClient
from config import MONGO_URI, DB_NAME

# Shared MongoDB connection for routes and helper modules.
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
