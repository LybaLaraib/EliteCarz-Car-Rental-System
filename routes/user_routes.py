from datetime import datetime
import os
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, current_app
from utils.db import db
from utils.auth import require_role, require_login, check_password, hash_password
from utils.helpers import clean_search, contains_regex, get_pagination_args, page_meta

user_bp = Blueprint("user", __name__)

# Posts are inserted only when the blog collection has no matching title.
DEFAULT_BLOG_POSTS = [
    {
        "title": "How to Choose the Right Rental Car (City vs Highway)",
        "content": "Choosing the right rental is easier when you start with your route.\n\nIf you’re mostly driving inside a busy city, prioritize compact size, easy parking, good AC performance, and fuel economy. A small sedan or hatchback often wins on comfort and cost.\n\nFor long highway drives, look for stability, cruise comfort, strong headlights, and luggage space. SUVs and larger sedans reduce fatigue on longer trips.\n\nChecklist before you book:\n- Count passengers + luggage\n- Decide if you need higher ground clearance\n- Estimate daily distance to plan fuel\n- Compare price/day against expected mileage\n\nA smart choice saves time, fuel, and stress — and makes the whole trip feel premium.",
    },
    {
        "title": "7 Pre-Drive Checks That Prevent Rental Day Surprises",
        "content": "Before you leave the pickup point, take 2 minutes for quick checks.\n\n1) Walk-around photos: capture all sides, bumpers, and wheels.\n2) Tire condition: look for low tread or uneven wear.\n3) Lights: headlights, indicators, and brake lights.\n4) AC + cabin smell: comfort matters on long rides.\n5) Brakes at low speed: ensure the pedal feels firm.\n6) Wipers + washer: critical in unexpected rain or dust.\n7) Fuel level and mileage: confirm it matches your booking details.\n\nThese checks protect you from disputes and help you enjoy a smooth ride from the first kilometer.",
    },
    {
        "title": "Security Deposits & Refunds: What to Expect",
        "content": "A security deposit is typically used to cover traffic fines, tolls, or minor damages.\n\nBest practices:\n- Ask how long refunds take and what triggers deductions\n- Keep a copy/photo of the deposit receipt\n- Return the car with the same fuel level\n- Report any issues immediately during the trip\n\nClear documentation makes refunds faster and keeps the experience stress-free.",
    },
    {
        "title": "Renting in Rainy Season: Safer Driving Tips",
        "content": "Wet roads change braking distance and traction.\n\nTips for safer rainy-season rentals:\n- Reduce speed and increase following distance\n- Avoid sudden steering inputs\n- Keep headlights on for visibility\n- Check tire condition before leaving\n- Use AC/defogger early to keep windows clear\n\nA calm driving style and a well-checked car make rainy trips far more comfortable.",
    },
    {
        "title": "Fuel Saving for Rentals: Small Habits, Big Difference",
        "content": "Fuel costs can quietly become the largest part of a trip.\n\nSimple habits:\n- Gentle acceleration and smooth braking\n- Keep tire pressure correct (ask at pickup)\n- Avoid heavy idling (especially in traffic)\n- Use cruise control on open roads when safe\n- Plan routes to avoid peak traffic\n\nSaving fuel also reduces stress — fewer stops, fewer surprises.",
    },
    {
        "title": "Why Booking Early Matters (Especially on Weekends)",
        "content": "Demand spikes on weekends and holidays.\n\nBooking early helps you:\n- Get better vehicle choices and categories\n- Lock predictable pricing\n- Avoid last-minute compromises (higher costs, limited availability)\n\nIf you know your dates, early booking is the easiest win for a premium experience.",
    },
    {
        "title": "A Simple Guide to Rental Insurance Terms",
        "content": "Insurance words can be confusing.\n\nCommon terms explained:\n- Coverage: what the policy includes\n- Excess/Deductible: what you pay before insurance covers the rest\n- Liability: damage you cause to others\n- Collision coverage: damage to the rented car\n\nAlways confirm the deductible and what documents you need in case of an incident. It’s better to know now than during an emergency.",
    },
]


def _ensure_default_blog_posts():
    existing_titles = {
        str(p.get("title", "")).strip().casefold()
        for p in db.blog_posts.find({}, {"title": 1})
    }
    now = datetime.utcnow()
    inserts = []
    for post in DEFAULT_BLOG_POSTS:
        t = post["title"].strip().casefold()
        if t not in existing_titles:
            inserts.append({"title": post["title"], "content": post["content"], "created_at": now})
            existing_titles.add(t)
    if inserts:
        db.blog_posts.insert_many(inserts)


def _car_image(car):
    # Prefer stored/local images and fall back to a search image if needed.
    if car.get("image_url"):
        return car["image_url"]
    car_id = str(car.get("_id") or "").strip()
    if car_id:
        local_rel = f"images/cars/{car_id}.jpg"
        local_abs = os.path.join(current_app.static_folder, local_rel.replace("/", os.sep))
        if os.path.exists(local_abs):
            return f"/static/{local_rel}"
    brand = str(car.get("brand", "car")).replace(" ", "+")
    model = str(car.get("model", "vehicle")).replace(" ", "+")
    return f"https://source.unsplash.com/1200x800/?{brand},{model},car"


def _car_with_meta(car):
    ratings = car.get("ratings", [])
    car["rating_avg"] = round(sum(ratings) / len(ratings), 1) if ratings else 0
    car["rating_count"] = len(ratings)
    car["image_url"] = _car_image(car)
    return car


def _expire_pending_bookings():
    # Pending bookings are auto-cancelled if pickup is not completed in time.
    now = datetime.utcnow()
    db.bookings.update_many(
        {"status": {"$in": ["pending", "confirmed"]}, "expires_at": {"$lte": now}},
        {
            "$set": {
                "status": "cancelled",
                "payment_status": "cancelled",
                "status_label": "Auto cancelled",
                "cancel_reason": "Auto-cancelled after 2 hours",
                "cancelled_by": "system",
                "cancelled_at": now,
                "updated_at": now,
            },
            "$inc": {"version": 1},
        },
    )


def _booking_status_label(booking):
    label = booking.get("status_label")
    if label:
        return label
    status = str(booking.get("status") or "pending").strip().lower()
    reason = str(booking.get("cancel_reason") or "").strip().lower()
    if status == "cancelled" and "auto" in reason:
        return "Auto cancelled"
    if status == "cancelled" and str(booking.get("cancelled_by") or "").lower() == "admin":
        return "Cancelled by EliteCarz (admin)"
    if status == "completed":
        return "Completed"
    return status.title()


@user_bp.route("/home")
def home():
    _expire_pending_bookings()
    return render_template("home.html")


@user_bp.route("/cars")
def cars():
    # Search supports city, brand, model, category, and car ID.
    _expire_pending_bookings()
    q = clean_search(request.args.get("q"))
    city = clean_search(request.args.get("city"))
    page, per_page, skip = get_pagination_args(request, default_per_page=12, max_per_page=48)
    query = {}
    if city:
        query["city"] = contains_regex(city)
    if q:
        query["$or"] = [
            {"brand": contains_regex(q)},
            {"model": contains_regex(q)},
            {"city": contains_regex(q)},
            {"category": contains_regex(q)},
            {"_id": contains_regex(q)},
        ]
    total = db.cars.count_documents(query)
    cars = list(db.cars.find(query).sort("_id", 1).skip(skip).limit(per_page))
    cars = [_car_with_meta(c) for c in cars]
    return render_template(
        "cars.html",
        cars=cars,
        selected_city=city,
        q=q,
        pager=page_meta(total, page, per_page),
    )


@user_bp.route("/cars/<car_id>")
def car_details(car_id):
    car = db.cars.find_one({"_id": car_id})
    if not car:
        flash("Car not found.", "danger")
        return redirect(url_for("user.cars"))
    car = _car_with_meta(car)
    reviews = list(db.reviews.find({"car_id": car_id}).sort("created_at", -1).limit(10))
    return render_template("car_detail.html", car=car, reviews=reviews)


@user_bp.route("/about")
def about():
    about_doc = db.site_content.find_one({"key": "about"}) or {}
    return render_template("about.html", about_content=about_doc.get("content"))


@user_bp.route("/policies")
def policies():
    return render_template("policies.html")


@user_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        db.contact_queries.insert_one(
            {
                "name": request.form.get("name", "").strip(),
                "email": request.form.get("email", "").strip(),
                "message": request.form.get("message", "").strip(),
                "created_at": datetime.utcnow(),
                "status": "new",
            }
        )
        flash("Query submitted. We will contact you soon.", "success")
        return redirect(url_for("user.contact"))
    return render_template("contact.html")


@user_bp.route("/blog")
def blog():
    q = clean_search(request.args.get("q"))
    page, per_page, skip = get_pagination_args(request, default_per_page=6, max_per_page=24)
    _ensure_default_blog_posts()
    posts_all = list(db.blog_posts.find({}).sort("created_at", -1))
    if q:
        q_cf = q.casefold()
        posts_all = [
            p
            for p in posts_all
            if q_cf in str(p.get("title", "")).casefold() or q_cf in str(p.get("content", "")).casefold()
        ]
    total = len(posts_all)
    posts = posts_all[skip : skip + per_page]
    return render_template("blog.html", posts=posts, q=q, pager=page_meta(total, page, per_page))


@user_bp.route("/dashboard")
@require_role("user")
def user_home():
    bookings_count = db.bookings.count_documents({"user_id": session.get("user_id")})
    reviews_count = db.reviews.count_documents({"user_id": session.get("user_id")})
    return render_template("user_dashboard.html", bookings_count=bookings_count, reviews_count=reviews_count)


@user_bp.route("/my-bookings")
@require_login
def my_bookings():
    _expire_pending_bookings()
    q = clean_search(request.args.get("q"))
    page, per_page, skip = get_pagination_args(request, default_per_page=12, max_per_page=50)
    query = {"user_id": session.get("user_id")}
    if q:
        query["$or"] = [{"car_id": contains_regex(q)}, {"status": contains_regex(q)}]
    total = db.bookings.count_documents(query)
    bookings = list(db.bookings.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    car_ids = [b.get("car_id") for b in bookings if b.get("car_id")]
    cars = {c["_id"]: _car_with_meta(c) for c in db.cars.find({"_id": {"$in": car_ids}})} if car_ids else {}
    for b in bookings:
        b["_car"] = cars.get(b.get("car_id"))
        b["_status_label"] = _booking_status_label(b)
    return render_template("user_bookings.html", bookings=bookings, q=q, pager=page_meta(total, page, per_page))


@user_bp.route("/my-reviews")
@require_login
def my_reviews():
    q = clean_search(request.args.get("q"))
    page, per_page, skip = get_pagination_args(request, default_per_page=12, max_per_page=50)
    query = {"user_id": session.get("user_id")}
    if q:
        query["$or"] = [{"car_id": contains_regex(q)}, {"comment": contains_regex(q)}]
    total = db.reviews.count_documents(query)
    reviews = list(db.reviews.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    car_ids = [r.get("car_id") for r in reviews if r.get("car_id")]
    cars = {c["_id"]: _car_with_meta(c) for c in db.cars.find({"_id": {"$in": car_ids}})} if car_ids else {}
    for r in reviews:
        r["_car"] = cars.get(r.get("car_id"))
    return render_template("user_reviews.html", reviews=reviews, q=q, pager=page_meta(total, page, per_page))


@user_bp.route("/profile", methods=["GET", "POST"])
@require_login
def profile():
    user = db.users.find_one({"_id": session.get("user_id")})
    if request.method == "POST":
        action = request.form.get("action", "update_profile").strip()
        old_password = request.form.get("old_password", "").strip()
        if not user or not old_password or not user.get("password") or not check_password(old_password, user["password"]):
            flash("Old password is incorrect.", "danger")
            return redirect(url_for("user.profile"))

        if action == "change_password":
            new_password = request.form.get("new_password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()
            if len(new_password) < 6:
                flash("New password must be at least 6 characters.", "warning")
                return redirect(url_for("user.profile"))
            if new_password != confirm_password:
                flash("New password confirmation does not match.", "warning")
                return redirect(url_for("user.profile"))
            current_version = user.get("version", 1)
            result = db.users.update_one(
                {"_id": session.get("user_id"), "$or": [{"version": current_version}, {"version": {"$exists": False}}]},
                {"$set": {"password": hash_password(new_password)}, "$inc": {"version": 1}},
            )
            if result.modified_count == 0:
                flash("Profile was updated elsewhere. Please try again.", "warning")
                return redirect(url_for("user.profile"))
            flash("Password updated successfully.", "success")
            return redirect(url_for("user.profile"))

        username = request.form.get("username", "").strip().lower()
        updates = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "address": request.form.get("address", "").strip(),
        }
        if username and username != user.get("username"):
            existing = db.users.find_one({"username": username, "role": "user", "_id": {"$ne": user["_id"]}})
            if existing:
                flash("That username is already taken.", "danger")
                return redirect(url_for("user.profile"))
            updates["username"] = username
        current_version = user.get("version", 1)
        result = db.users.update_one(
            {"_id": session.get("user_id"), "$or": [{"version": current_version}, {"version": {"$exists": False}}]},
            {"$set": updates, "$inc": {"version": 1}},
        )
        if result.modified_count == 0:
            flash("Profile was updated elsewhere. Please try again.", "warning")
            return redirect(url_for("user.profile"))
        session["display_name"] = updates.get("username") or updates.get("name") or session.get("display_name")
        flash("Profile updated.", "success")
        return redirect(url_for("user.profile"))
    return render_template("user_profile.html", user=user)
