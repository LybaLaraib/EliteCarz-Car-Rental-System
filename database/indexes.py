from utils.db import db
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# Run after loading data to keep common searches and lookups fast.
def create_indexes():
    db.cars.create_index("city")
    db.cars.create_index("price_per_day")
    db.cars.create_index("availability")
    db.users.create_index("email", unique=True)
    db.users.create_index("username", unique=True, sparse=True)
    db.bookings.create_index("car_id")
    db.bookings.create_index("user_id")
    db.bookings.create_index("created_at")
    db.bookings.create_index([("car_id", 1), ("start_date", 1), ("end_date", 1)])
    db.bookings.create_index("status")
    db.bookings.create_index("expires_at")
    db.reviews.create_index("car_id")
    db.reviews.create_index("user_id")
    db.payments.create_index("booking_id")
    db.payments.create_index("created_at")
    db.locks.create_index("resource_id", unique=True)
    db.locks.create_index("lock_time")
    db.payments.create_index("status")
    db.mv_revenue_by_city_current_month.create_index("total")
    db.mv_top_cars_current_month.create_index("total")

if __name__ == "__main__":
    create_indexes()
    try:
        from database.views import setup_reporting_views

        setup_reporting_views()
        print("Reporting views ready")
    except Exception as exc:
        print(f"Reporting views skipped: {exc}")
    print("Indexes created")
