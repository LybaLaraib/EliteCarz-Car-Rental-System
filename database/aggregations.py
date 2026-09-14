from utils.db import db

# Aggregation helpers used by admin dashboard and revenue pages.
def _paid_or_pending_with_date_pipeline():
    return [
        {"$match": {"status": {"$in": ["paid", "pending"]}}},
        {
            "$addFields": {
                "created_at": {
                    "$cond": [
                        {"$eq": [{"$type": "$created_at"}, "date"]},
                        "$created_at",
                        {"$toDate": "$created_at"},
                    ]
                }
            }
        },
    ]


def monthly_revenue_pipeline():
    return _paid_or_pending_with_date_pipeline() + [
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}},
                "total": {"$sum": "$amount"},
            }
        },
        {"$sort": {"_id": 1}},
    ]


def current_month_total_revenue_pipeline():
    return _paid_or_pending_with_date_pipeline() + [
        {"$addFields": {"ym": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}}},
        {"$match": {"$expr": {"$eq": ["$ym", {"$dateToString": {"format": "%Y-%m", "date": "$$NOW"}}]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]


def revenue_by_city_current_month_pipeline():
    return _paid_or_pending_with_date_pipeline() + [
        {"$addFields": {"ym": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}}},
        {"$match": {"$expr": {"$eq": ["$ym", {"$dateToString": {"format": "%Y-%m", "date": "$$NOW"}}]}}},
        {
            "$lookup": {
                "from": "bookings",
                "localField": "booking_id",
                "foreignField": "_id",
                "as": "booking",
            }
        },
        {"$unwind": "$booking"},
        {
            "$lookup": {
                "from": "cars",
                "localField": "booking.car_id",
                "foreignField": "_id",
                "as": "car",
            }
        },
        {"$unwind": "$car"},
        {"$group": {"_id": "$car.city", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]


def top_cars_by_revenue_current_month_pipeline():
    return _paid_or_pending_with_date_pipeline() + [
        {"$addFields": {"ym": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}}},
        {"$match": {"$expr": {"$eq": ["$ym", {"$dateToString": {"format": "%Y-%m", "date": "$$NOW"}}]}}},
        {
            "$lookup": {
                "from": "bookings",
                "localField": "booking_id",
                "foreignField": "_id",
                "as": "booking",
            }
        },
        {"$unwind": "$booking"},
        {"$group": {"_id": "$booking.car_id", "total": {"$sum": "$amount"}, "bookings": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$lookup": {"from": "cars", "localField": "_id", "foreignField": "_id", "as": "car"}},
        {"$unwind": "$car"},
        {"$project": {"_id": 1, "total": 1, "bookings": 1, "car": 1}},
    ]


def _replace_materialized(collection_name, source_collection, pipeline):
    docs = list(source_collection.aggregate(pipeline))
    target = db[collection_name]
    target.delete_many({})
    if docs:
        target.insert_many(docs)
    return docs


def refresh_materialized_views():
    return {
        "monthly_revenue": _replace_materialized("mv_monthly_revenue", db.payments, monthly_revenue_pipeline()),
        "revenue_by_city_current_month": _replace_materialized(
            "mv_revenue_by_city_current_month",
            db.payments,
            revenue_by_city_current_month_pipeline(),
        ),
        "top_cars_current_month": _replace_materialized(
            "mv_top_cars_current_month",
            db.payments,
            top_cars_by_revenue_current_month_pipeline(),
        ),
    }


def _materialized_or_live(collection_name, pipeline, sort_field=None, sort_direction=1):
    try:
        _replace_materialized(collection_name, db.payments, pipeline)
        cursor = db[collection_name].find({})
        if sort_field:
            cursor = cursor.sort(sort_field, sort_direction)
        return list(cursor)
    except Exception:
        return list(db.payments.aggregate(pipeline))


def revenue_stats():
    return list(db.payments.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]))


def bookings_by_city():
    return list(db.bookings.aggregate([
        {
            "$lookup": {
                "from": "cars",
                "localField": "car_id",
                "foreignField": "_id",
                "as": "car"
            }
        },
        {"$unwind": "$car"},
        {
            "$group": {
                "_id": "$car.city",
                "total": {"$sum": 1}
            }
        }
    ]))


def booking_status_breakdown():
    return list(
        db.bookings.aggregate(
            [
                {"$group": {"_id": "$status", "total": {"$sum": 1}}},
                {"$sort": {"total": -1}},
            ]
        )
    )


def monthly_revenue():
    # Chart data is grouped by month and sorted from oldest to newest.
    return _materialized_or_live("mv_monthly_revenue", monthly_revenue_pipeline(), "_id")


def current_month_total_revenue():
    return list(db.payments.aggregate(current_month_total_revenue_pipeline()))


def revenue_by_city_current_month():
    return _materialized_or_live(
        "mv_revenue_by_city_current_month",
        revenue_by_city_current_month_pipeline(),
        "total",
        -1,
    )


def top_cars_by_revenue_current_month():
    # Used on Manage Cars to show the current month's strongest performers.
    return _materialized_or_live(
        "mv_top_cars_current_month",
        top_cars_by_revenue_current_month_pipeline(),
        "total",
        -1,
    )
