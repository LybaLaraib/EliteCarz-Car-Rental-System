from database.aggregations import refresh_materialized_views
from utils.db import db
import sys
from pathlib import Path

from pymongo.errors import CollectionInvalid, OperationFailure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# Optional reporting views for joined booking/payment/car data.
VIEW_DEFINITIONS = {
    "booking_payment_view": {
        "viewOn": "bookings",
        "pipeline": [
            {"$lookup": {"from": "cars", "localField": "car_id", "foreignField": "_id", "as": "car"}},
            {"$unwind": {"path": "$car", "preserveNullAndEmptyArrays": True}},
            {"$lookup": {"from": "payments", "localField": "_id", "foreignField": "booking_id", "as": "payments"}},
        ],
    },
    "user_booking_view": {
        "viewOn": "bookings",
        "pipeline": [
            {"$lookup": {"from": "cars", "localField": "car_id", "foreignField": "_id", "as": "car"}},
            {"$unwind": {"path": "$car", "preserveNullAndEmptyArrays": True}},
            {"$project": {"user_id": 1, "car_id": 1, "status": 1, "start_date": 1, "end_date": 1, "total_price": 1, "car": 1}},
        ],
    },
}


def create_views():
    existing = {item["name"]: item.get("type") for item in db.list_collections()}
    created = []
    skipped = []
    for name, definition in VIEW_DEFINITIONS.items():
        if name in existing:
            skipped.append(name)
            continue
        try:
            db.command(
                {
                    "create": name,
                    "viewOn": definition["viewOn"],
                    "pipeline": definition["pipeline"],
                }
            )
            created.append(name)
        except (CollectionInvalid, OperationFailure):
            skipped.append(name)
    return {"created": created, "skipped": skipped}


def setup_reporting_views():
    return {
        "views": create_views(),
        "materialized_views": refresh_materialized_views(),
    }


if __name__ == "__main__":
    result = setup_reporting_views()
    print(f"Views ready: {result['views']}")
