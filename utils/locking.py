from datetime import datetime, timedelta

from pymongo.errors import DuplicateKeyError

from utils.db import db

# Lightweight lock used while a booking is being created.
LOCK_TIMEOUT_MINUTES = 15
_LOCK_INDEX_READY = False


def _ensure_lock_index():
    global _LOCK_INDEX_READY
    if _LOCK_INDEX_READY:
        return
    try:
        db.locks.create_index("resource_id", unique=True)
    except Exception:
        pass
    _LOCK_INDEX_READY = True


def acquire_lock(resource_id, user_id):
    _ensure_lock_index()
    now = datetime.utcnow()
    stale_before = now - timedelta(minutes=LOCK_TIMEOUT_MINUTES)
    db.locks.delete_many({"resource_id": resource_id, "lock_time": {"$lt": stale_before}})
    try:
        result = db.locks.update_one(
            {"resource_id": resource_id},
            {
                "$setOnInsert": {
                    "resource_id": resource_id,
                    "locked_by": user_id,
                    "lock_time": now,
                }
            },
            upsert=True,
        )
        return result.upserted_id is not None
    except DuplicateKeyError:
        return False


def release_lock(resource_id):
    db.locks.delete_one({"resource_id": resource_id})
