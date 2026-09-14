import json
from pymongo import MongoClient

MONGO_URI = "mongodb+srv://laibalaraib25_db_user:kOsi3Rc3PEJ0yHSA@cluster0.nj0gyoi.mongodb.net/?appName=Cluster0"
DB_NAME = "CarRentalFinal"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

files_to_collections = {
    "data/cars.json": "cars",
    "data/users.json": "users",
    "data/bookings.json": "bookings",
    "data/reviews.json": "reviews",
    "data/payments.json": "payments",
}

for filepath, collection_name in files_to_collections.items():
    with open(filepath) as f:
        docs = json.load(f)
    if docs:
        db[collection_name].delete_many({})
        db[collection_name].insert_many(docs)
        print(f"Loaded {len(docs)} docs into {collection_name}")

print("Done.")