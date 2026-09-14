from flask import Blueprint, request, redirect, session, flash, url_for
from utils.db import db
from datetime import datetime
from utils.auth import is_guest

review_bp = Blueprint("review", __name__)

@review_bp.route("/review/<car_id>", methods=["POST"])
def add_review(car_id):
    # Reviews are only accepted from signed-in users.
    user_id = session.get("user_id")

    if not user_id or is_guest() or session.get("role") != "user":
        flash("Please sign up to submit a review.", "warning")
        return redirect(url_for("auth.signup"))

    rating = request.form.get("rating")
    comment = request.form.get("comment", "").strip()

    try:
        rating = int(rating)
    except Exception:
        flash("Invalid rating.", "danger")
        return redirect(url_for("user.car_details", car_id=car_id))

    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.", "danger")
        return redirect(url_for("user.car_details", car_id=car_id))

    review = {
        "user_id": user_id,
        "car_id": car_id,
        "rating": rating,
        "comment": comment,
        "created_at": datetime.now()
    }

    db.reviews.insert_one(review)

    # Keep the car document ready for quick average-rating display.
    db.cars.update_one(
        {"_id": car_id},
        {"$push": {"ratings": rating}, "$inc": {"version": 1}}
    )

    flash("Review added successfully!")
    return redirect(url_for("user.car_details", car_id=car_id))


@review_bp.route("/reviews/<car_id>")
def view_reviews(car_id):
    reviews = list(db.reviews.find({"car_id": car_id}))

    return {
        "reviews": [
            {
                "user": r["user_id"],
                "rating": r["rating"],
                "comment": r["comment"]
            }
            for r in reviews
        ]
    }


@review_bp.route("/reviews/avg/<car_id>")
def avg_rating(car_id):
    result = list(db.reviews.aggregate([
        {"$match": {"car_id": car_id}},
        {
            "$group": {
                "_id": "$car_id",
                "avgRating": {"$avg": "$rating"}
            }
        }
    ]))

    if result:
        return {"average_rating": round(result[0]["avgRating"], 2)}

    return {"average_rating": 0}
