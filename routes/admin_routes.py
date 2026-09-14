from datetime import datetime
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from bson import ObjectId
from utils.db import db
from utils.auth import require_role
from database.aggregations import (
    revenue_stats,
    bookings_by_city,
    booking_status_breakdown,
    monthly_revenue,
    current_month_total_revenue,
    revenue_by_city_current_month,
    top_cars_by_revenue_current_month,
)
from utils.helpers import clean_search, contains_regex, exact_regex, get_pagination_args, page_meta
from routes.user_routes import _ensure_default_blog_posts

admin_bp = Blueprint("admin", __name__)

# Admin pages use the same car-image fallback as the user side.
def _car_image(car):
    if not car:
        return ""
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
    return f"https://source.unsplash.com/1200x800/?{brand},{model},supercar"


PENDING_STATUSES = ["pending", "confirmed"]


def _format_status_label(booking):
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


def _expire_pending_bookings():
    now = datetime.utcnow()
    db.bookings.update_many(
        {"status": {"$in": PENDING_STATUSES}, "expires_at": {"$lte": now}},
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


def _booking_status_query(tab):
    if tab == "pending":
        return {"status": {"$in": PENDING_STATUSES}}
    if tab == "cancelled":
        return {"status": "cancelled"}
    if tab == "completed":
        return {"status": "completed"}
    return {}


def _booking_search_query(q):
    if not q:
        return {}
    search_parts = [
        {"_id": contains_regex(q)},
        {"booking_uid": contains_regex(q)},
        {"customer_name": contains_regex(q)},
        {"customer_phone": contains_regex(q)},
        {"customer_address": contains_regex(q)},
        {"pickup_city": contains_regex(q)},
        {"car_id": contains_regex(q)},
        {"user_id": contains_regex(q)},
        {"status": contains_regex(q)},
        {"status_label": contains_regex(q)},
    ]
    matching_cars = list(
        db.cars.find(
            {
                "$or": [
                    {"_id": contains_regex(q)},
                    {"brand": contains_regex(q)},
                    {"model": contains_regex(q)},
                    {"city": contains_regex(q)},
                    {"category": contains_regex(q)},
                ]
            },
            {"_id": 1},
        )
    )
    q_cf = q.casefold()
    combined_car_ids = [
        c["_id"]
        for c in db.cars.find({}, {"_id": 1, "brand": 1, "model": 1})
        if q_cf in f"{c.get('brand', '')} {c.get('model', '')}".casefold()
    ]
    car_ids = list({c["_id"] for c in matching_cars} | set(combined_car_ids))
    if car_ids:
        search_parts.append({"car_id": {"$in": car_ids}})

    matching_users = list(
        db.users.find(
            {
                "$or": [
                    {"_id": contains_regex(q)},
                    {"name": contains_regex(q)},
                    {"username": contains_regex(q)},
                    {"email": contains_regex(q)},
                    {"phone": contains_regex(q)},
                ]
            },
            {"_id": 1},
        )
    )
    user_ids = [u["_id"] for u in matching_users]
    if user_ids:
        search_parts.append({"user_id": {"$in": user_ids}})
    return {"$or": search_parts}


def _combine_queries(*queries):
    queries = [q for q in queries if q]
    if not queries:
        return {}
    if len(queries) == 1:
        return queries[0]
    return {"$and": queries}


def _enrich_bookings(bookings):
    car_ids = [b.get("car_id") for b in bookings if b.get("car_id")]
    user_ids = [b.get("user_id") for b in bookings if b.get("user_id")]
    booking_ids = [b.get("_id") for b in bookings if b.get("_id")]
    cars = {c["_id"]: c for c in db.cars.find({"_id": {"$in": car_ids}})} if car_ids else {}
    users = {u["_id"]: u for u in db.users.find({"_id": {"$in": user_ids}})} if user_ids else {}
    payments = {p["booking_id"]: p for p in db.payments.find({"booking_id": {"$in": booking_ids}})} if booking_ids else {}
    for booking in bookings:
        car = cars.get(booking.get("car_id"))
        if car:
            car["image_url"] = _car_image(car)
        booking["_car"] = car
        booking["_user"] = users.get(booking.get("user_id"))
        booking["_payment"] = payments.get(booking.get("_id"))
        booking["_status_label"] = _format_status_label(booking)
    return bookings


def _booking_redirect_args(booking_id):
    tab = clean_search(request.form.get("tab") or request.args.get("tab"), max_length=20)
    q = clean_search(request.form.get("q") or request.args.get("q"))
    page = clean_search(request.form.get("page") or request.args.get("page") or "1", max_length=8)
    if request.form.get("next") == "detail":
        return redirect(url_for("admin.admin_booking_detail", booking_id=booking_id))
    return redirect(url_for("admin.admin_bookings", tab=tab or "all", q=q, page=page))


@admin_bp.route("/admin")
@require_role("admin")
def admin_home():
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/dashboard")
@require_role("admin")
def dashboard():
    revenue = revenue_stats()
    revenue = revenue[0]["total"] if revenue else 0
    cities = bookings_by_city()
    statuses = booking_status_breakdown()
    return render_template("admin_dashboard.html", revenue=revenue, cities=cities, statuses=statuses, monthly=monthly_revenue())


@admin_bp.route("/admin/stats-json")
@require_role("admin")
def stats_json():
    return jsonify(
        {
            "revenue": monthly_revenue(),
            "cities": bookings_by_city(),
            "statuses": booking_status_breakdown(),
        }
    )


@admin_bp.route("/admin/bookings")
@require_role("admin")
def admin_bookings():
    _expire_pending_bookings()
    tab = clean_search(request.args.get("tab"), max_length=20) or "all"
    if tab not in {"all", "pending", "cancelled", "completed"}:
        tab = "all"
    q = clean_search(request.args.get("q"))
    page, per_page, skip = get_pagination_args(request, default_per_page=9, max_per_page=50)
    query = _combine_queries(_booking_status_query(tab), _booking_search_query(q))
    total = db.bookings.count_documents(query)
    bookings = list(db.bookings.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    bookings = _enrich_bookings(bookings)
    tab_counts = {
        "all": db.bookings.count_documents({}),
        "pending": db.bookings.count_documents(_booking_status_query("pending")),
        "cancelled": db.bookings.count_documents(_booking_status_query("cancelled")),
        "completed": db.bookings.count_documents(_booking_status_query("completed")),
    }
    return render_template(
        "admin_bookings.html",
        bookings=bookings,
        tab=tab,
        q=q,
        pager=page_meta(total, page, per_page),
        tab_counts=tab_counts,
    )


@admin_bp.route("/admin/bookings/<booking_id>")
@require_role("admin")
def admin_booking_detail(booking_id):
    _expire_pending_bookings()
    booking = db.bookings.find_one({"_id": booking_id}) or db.bookings.find_one({"booking_uid": booking_id})
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("admin.admin_bookings"))
    booking = _enrich_bookings([booking])[0]
    return render_template("admin_booking_detail.html", booking=booking)


@admin_bp.route("/admin/bookings/<booking_id>/cancel", methods=["POST"])
@require_role("admin")
def admin_cancel_booking(booking_id):
    now = datetime.utcnow()
    result = db.bookings.update_one(
        {"_id": booking_id, "status": {"$ne": "completed"}},
        {
            "$set": {
                "status": "cancelled",
                "payment_status": "cancelled",
                "status_label": "Cancelled by EliteCarz (admin)",
                "cancel_reason": "Cancelled by EliteCarz admin",
                "cancelled_by": "admin",
                "cancelled_at": now,
                "updated_at": now,
            },
            "$inc": {"version": 1},
        },
    )
    if result.modified_count:
        db.payments.update_one({"booking_id": booking_id}, {"$set": {"status": "cancelled", "updated_at": now}, "$inc": {"version": 1}})
        flash("Booking cancelled by EliteCarz admin.", "success")
    else:
        flash("Booking could not be cancelled.", "warning")
    return _booking_redirect_args(booking_id)


@admin_bp.route("/admin/bookings/<booking_id>/complete", methods=["POST"])
@require_role("admin")
def admin_complete_booking(booking_id):
    now = datetime.utcnow()
    result = db.bookings.update_one(
        {"_id": booking_id, "status": {"$in": PENDING_STATUSES}},
        {
            "$set": {
                "status": "completed",
                "payment_status": "paid",
                "status_label": "Completed",
                "completed_by": "admin",
                "completed_at": now,
                "updated_at": now,
            },
            "$inc": {"version": 1},
        },
    )
    if result.modified_count:
        db.payments.update_one({"booking_id": booking_id}, {"$set": {"status": "paid", "updated_at": now}, "$inc": {"version": 1}})
        flash("Booking marked as completed.", "success")
    else:
        flash("Only pending bookings can be marked completed.", "warning")
    return _booking_redirect_args(booking_id)


@admin_bp.route("/admin/cars", methods=["GET", "POST"])
@require_role("admin")
def admin_cars():
    # Add, update, delete, search, and monthly top cars share this page.
    edit_id = clean_search(request.args.get("edit_id"), max_length=40)
    show_form = request.args.get("show_form", "").strip() == "1"
    view_all = request.args.get("view_all", "").strip() == "1"
    q = clean_search(request.args.get("q"))
    page, per_page, skip = get_pagination_args(request, default_per_page=10, max_per_page=50)
    if request.method == "POST":
        mode = request.form.get("mode", "add")
        car_id = request.form.get("_id", "").strip()
        if mode == "delete":
            db.cars.delete_one({"_id": car_id})
            flash("Car deleted.", "info")
            return redirect(url_for("admin.admin_cars"))
        payload = {
            "brand": request.form.get("brand", "").strip(),
            "model": request.form.get("model", "").strip(),
            "year": int(request.form.get("year", "2024")),
            "category": request.form.get("category", "Sedan").strip(),
            "price_per_day": int(request.form.get("price_per_day", "0")),
            "city": request.form.get("city", "").strip(),
            "image_url": request.form.get("image_url", "").strip(),
            "features": [x.strip() for x in request.form.get("features", "").split(",") if x.strip()],
            "ratings": [],
            "availability": True,
            "created_at": datetime.utcnow(),
        }
        db.cars.update_one({"_id": car_id}, {"$set": payload, "$inc": {"version": 1}}, upsert=True)
        flash("Car saved successfully.", "success")
        return redirect(url_for("admin.admin_cars"))
    query = {}
    if q:
        query["$or"] = [
            {"_id": contains_regex(q)},
            {"brand": contains_regex(q)},
            {"model": contains_regex(q)},
            {"city": contains_regex(q)},
            {"category": contains_regex(q)},
        ]
    show_results = view_all or bool(q)
    cars = []
    cars_pager = None
    if show_results:
        total = db.cars.count_documents(query)
        cars = list(db.cars.find(query).sort("_id", 1).skip(skip).limit(per_page))
        for c in cars:
            c["image_url"] = _car_image(c)
        cars_pager = page_meta(total, page, per_page)

    edit_car = db.cars.find_one({"_id": edit_id}) if edit_id else None
    show_top = not view_all
    top_cars = []
    top_pager = None
    if show_top:
        top_all = top_cars_by_revenue_current_month()
        top_total = len(top_all)
        top_per_page = 10
        top_page = max(1, int(request.args.get("top_page", 1) or 1))
        top_skip = (top_page - 1) * top_per_page
        top_cars = top_all[top_skip : top_skip + top_per_page]
        for item in top_cars:
            if item.get("car"):
                item["car"]["image_url"] = _car_image(item["car"])
        top_pager = page_meta(top_total, top_page, top_per_page)

    return render_template(
        "admin_cars.html",
        cars=cars,
        edit_car=edit_car,
        show_form=show_form or bool(edit_car),
        view_all=view_all,
        show_results=show_results,
        q=q,
        cars_pager=cars_pager,
        show_top=show_top,
        top_cars=top_cars,
        top_pager=top_pager,
    )


@admin_bp.route("/admin/cars/delete/<car_id>", methods=["POST"])
@require_role("admin")
def delete_car(car_id):
    db.cars.delete_one({"_id": car_id})
    flash("Car deleted.", "info")
    return redirect(url_for("admin.admin_cars"))


@admin_bp.route("/admin/revenue")
@require_role("admin")
def admin_revenue():
    # Payment rows are enriched with booking and car details for display.
    q = clean_search(request.args.get("q"))
    status = clean_search(request.args.get("status"), max_length=30)
    page, per_page, skip = get_pagination_args(request, default_per_page=20, max_per_page=100)
    query = {}
    if status:
        query["status"] = exact_regex(status)
    if q:
        query["booking_id"] = contains_regex(q)
    total = db.payments.count_documents(query)
    payments = list(db.payments.find(query).sort("created_at", -1).skip(skip).limit(per_page))

    month_total = current_month_total_revenue()
    month_total = month_total[0]["total"] if month_total else 0
    city_breakdown = revenue_by_city_current_month()

    booking_ids = [p.get("booking_id") for p in payments if p.get("booking_id")]
    bookings = {b["_id"]: b for b in db.bookings.find({"_id": {"$in": booking_ids}})}
    car_ids = [b.get("car_id") for b in bookings.values() if b.get("car_id")]
    cars = {c["_id"]: c for c in db.cars.find({"_id": {"$in": car_ids}})}
    for p in payments:
        b = bookings.get(p.get("booking_id"))
        c = cars.get(b.get("car_id")) if b else None
        if c:
            c["image_url"] = _car_image(c)
        p["_booking"] = b
        p["_car"] = c

    return render_template(
        "admin_revenue.html",
        payments=payments,
        q=q,
        status=status,
        pager=page_meta(total, page, per_page),
        month_total=month_total,
        city_breakdown=city_breakdown,
    )


@admin_bp.route("/admin/blogs", methods=["GET", "POST"])
@require_role("admin")
def admin_blogs():
    # Admin can manage the same blog posts shown on the public blog page.
    _ensure_default_blog_posts()
    q = clean_search(request.args.get("q"))
    edit_id = clean_search(request.args.get("edit_id"), max_length=40)
    if request.method == "POST":
        mode = request.form.get("mode", "add")
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if mode == "update":
            post_id = request.form.get("post_id", "").strip()
            try:
                db.blog_posts.update_one(
                    {"_id": ObjectId(post_id)},
                    {"$set": {"title": title, "content": content}, "$inc": {"version": 1}},
                )
                flash("Blog post updated.", "success")
            except Exception:
                flash("Unable to update blog post.", "danger")
            return redirect(url_for("admin.admin_blogs"))
        db.blog_posts.insert_one({"title": title, "content": content, "created_at": datetime.utcnow()})
        flash("Blog post created.", "success")
        return redirect(url_for("admin.admin_blogs"))
    posts = list(db.blog_posts.find({}).sort("created_at", -1))
    if q:
        q_cf = q.casefold()
        posts = [p for p in posts if q_cf in str(p.get("title", "")).casefold() or q_cf in str(p.get("content", "")).casefold()]
    edit_post = None
    if edit_id:
        try:
            edit_post = db.blog_posts.find_one({"_id": ObjectId(edit_id)})
        except Exception:
            edit_post = None
    return render_template("admin_blogs.html", posts=posts, q=q, edit_post=edit_post)


@admin_bp.route("/admin/blogs/delete/<post_id>", methods=["POST"])
@require_role("admin")
def delete_blog(post_id):
    try:
        db.blog_posts.delete_one({"_id": ObjectId(post_id)})
    except Exception:
        pass
    flash("Blog post removed.", "info")
    return redirect(url_for("admin.admin_blogs"))


@admin_bp.route("/admin/queries")
@require_role("admin")
def admin_queries():
    q = clean_search(request.args.get("q"))
    status = clean_search(request.args.get("status"), max_length=30)
    page, per_page, skip = get_pagination_args(request, default_per_page=12, max_per_page=50)
    query = {}
    if status:
        query["status"] = exact_regex(status)
    if q:
        query["$or"] = [{"name": contains_regex(q)}, {"email": contains_regex(q)}, {"message": contains_regex(q)}]
    total = db.contact_queries.count_documents(query)
    queries = list(db.contact_queries.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    return render_template("admin_queries.html", queries=queries, q=q, status=status, pager=page_meta(total, page, per_page))


@admin_bp.route("/admin/queries/reply/<query_id>", methods=["POST"])
@require_role("admin")
def reply_query(query_id):
    reply = request.form.get("reply", "").strip()
    if not reply:
        flash("Reply message is required.", "warning")
        return redirect(url_for("admin.admin_queries"))
    try:
        db.contact_queries.update_one(
            {"_id": ObjectId(query_id)},
            {"$set": {"admin_reply": reply, "replied_at": datetime.utcnow()}, "$inc": {"version": 1}},
        )
        flash("Reply saved.", "success")
    except Exception:
        flash("Unable to save reply.", "danger")
    return redirect(url_for("admin.admin_queries"))


@admin_bp.route("/admin/queries/resolve/<query_id>", methods=["POST"])
@require_role("admin")
def resolve_query(query_id):
    try:
        db.contact_queries.update_one({"_id": ObjectId(query_id)}, {"$set": {"status": "resolved"}, "$inc": {"version": 1}})
    except Exception:
        pass
    flash("Query marked as resolved.", "success")
    return redirect(url_for("admin.admin_queries"))


@admin_bp.route("/admin/reviews")
@require_role("admin")
def admin_reviews():
    q = clean_search(request.args.get("q"))
    page, per_page, skip = get_pagination_args(request, default_per_page=20, max_per_page=100)
    query = {}
    if q:
        query["$or"] = [{"user_id": contains_regex(q)}, {"car_id": contains_regex(q)}, {"comment": contains_regex(q)}]
    total = db.reviews.count_documents(query)
    reviews = list(db.reviews.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    return render_template("admin_reviews.html", reviews=reviews, q=q, pager=page_meta(total, page, per_page))


@admin_bp.route("/admin/about", methods=["GET", "POST"])
@require_role("admin")
def admin_about():
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        db.site_content.update_one(
            {"key": "about"},
            {"$set": {"key": "about", "content": content, "updated_at": datetime.utcnow()}, "$inc": {"version": 1}},
            upsert=True,
        )
        flash("About content updated.", "success")
        return redirect(url_for("admin.admin_about"))
    about_doc = db.site_content.find_one({"key": "about"}) or {}
    return render_template("admin_about.html", about_content=about_doc.get("content", ""))


@admin_bp.route("/admin/reviews/delete/<review_id>", methods=["POST"])
@require_role("admin")
def delete_review(review_id):
    result = db.reviews.delete_one({"_id": review_id})
    if result.deleted_count == 0:
        try:
            db.reviews.delete_one({"_id": ObjectId(review_id)})
        except Exception:
            pass
    flash("Review deleted.", "info")
    return redirect(url_for("admin.admin_reviews"))
