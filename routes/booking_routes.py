from datetime import datetime, timedelta
import os
from flask import Blueprint, session, redirect, flash, request, render_template, url_for, current_app
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure

from utils.db import client, db
from utils.locking import acquire_lock, release_lock
from utils.auth import is_guest

booking_bp = Blueprint("booking", __name__)


class BookingUnavailable(Exception):
    pass


def _next_booking_id(mongo_session=None):
    count = db.bookings.count_documents({}, session=mongo_session)
    db.counters.update_one(
        {"_id": "bookings"},
        {"$max": {"seq": count}},
        upsert=True,
        session=mongo_session,
    )
    counter = db.counters.find_one_and_update(
        {"_id": "bookings"},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
        session=mongo_session,
    )
    return f"BKG{int(counter['seq']):04d}"


# Reject bookings that overlap an existing active booking for the same car.
def _is_date_available(car_id, start_dt, end_dt, mongo_session=None):
    overlap = db.bookings.find_one(
        {
            "car_id": car_id,
            "status": {"$nin": ["cancelled", "completed"]},
            "$or": [
                {"start_date": {"$lte": end_dt}, "end_date": {"$gte": start_dt}},
            ],
        },
        session=mongo_session,
    )
    return overlap is None


def _transaction_not_supported(error):
    text = str(error).lower()
    return "transaction numbers" in text or "transactions are not supported" in text


def _card_brand(card_number):
    digits = "".join(ch for ch in str(card_number or "") if ch.isdigit())
    if digits.startswith("4"):
        return "Visa"
    if digits[:2] in {"51", "52", "53", "54", "55"} or 2221 <= int(digits[:4] or 0) <= 2720:
        return "Mastercard"
    return "Card"


def _masked_card_details(card_name, card_number, card_expiry):
    digits = "".join(ch for ch in str(card_number or "") if ch.isdigit())
    return {
        "cardholder": card_name.strip(),
        "brand": _card_brand(digits),
        "last4": digits[-4:] if len(digits) >= 4 else "",
        "masked_number": f"**** **** **** {digits[-4:]}" if len(digits) >= 4 else "Not provided",
        "expiry": card_expiry.strip(),
        "cvv_stored": False,
    }


def _create_booking_and_payment(
    car,
    user_id,
    car_id,
    start_dt,
    end_dt,
    days,
    total_rent,
    name,
    phone,
    address,
    payment_method,
    card_details,
    mongo_session=None,
):
    if not _is_date_available(car_id, start_dt, end_dt, mongo_session=mongo_session):
        raise BookingUnavailable()

    booking_id = _next_booking_id(mongo_session=mongo_session)
    booking_uid = f"ELC-{booking_id}"
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=2)

    booking = {
        "_id": booking_id,
        "user_id": user_id,
        "car_id": car_id,
        "customer_name": name,
        "customer_phone": phone,
        "customer_address": address,
        "pickup_city": car.get("city"),
        "start_date": start_dt,
        "end_date": end_dt,
        "total_days": days,
        "total_price": total_rent,
        "status": "pending",
        "payment_status": "pending",
        "payment_method": payment_method,
        "status_label": "Pending",
        "booking_uid": booking_uid,
        "card_details": card_details,
        "expires_at": expires_at,
        "version": 1,
        "created_at": now,
    }
    db.bookings.insert_one(booking, session=mongo_session)

    db.payments.insert_one(
        {
            "booking_id": booking_id,
            "amount": total_rent,
            "status": "pending",
            "method": payment_method,
            "card_details": card_details,
            "version": 1,
            "created_at": now,
        },
        session=mongo_session,
    )
    return booking_uid


def _create_booking_with_transaction(*args):
    try:
        with client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                return _create_booking_and_payment(*args, mongo_session=mongo_session)
    except OperationFailure as exc:
        if not _transaction_not_supported(exc):
            raise
        return _create_booking_and_payment(*args)


@booking_bp.route("/book/<car_id>", methods=["GET", "POST"])
def book(car_id):
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id or is_guest():
        flash("Please sign up before booking.", "warning")
        return redirect(url_for("auth.signup"))
    if role != "user":
        flash("Only signed-in users can book cars.", "warning")
        return redirect(url_for("user.car_details", car_id=car_id))

    car = db.cars.find_one({"_id": car_id})
    if not car:
        flash("Car not found.", "danger")
        return redirect(url_for("user.cars"))

    if not car.get("image_url"):
        local_rel = f"images/cars/{car_id}.jpg"
        local_abs = os.path.join(current_app.static_folder, local_rel.replace("/", os.sep))
        if os.path.exists(local_abs):
            car["image_url"] = f"/static/{local_rel}"
        else:
            brand = str(car.get("brand", "car")).replace(" ", "+")
            model = str(car.get("model", "vehicle")).replace(" ", "+")
            car["image_url"] = f"https://source.unsplash.com/1200x800/?{brand},{model},car"

    if request.method == "GET":
        return render_template("booking_form.html", car=car)

    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    payment_method = request.form.get("payment_method", "cash").strip().lower()
    if payment_method not in {"cash", "online"}:
        payment_method = "cash"
    card_name = request.form.get("card_name", "").strip()
    card_number = request.form.get("card_number", "").strip()
    card_expiry = request.form.get("card_expiry", "").strip()
    card_cvv = request.form.get("card_cvv", "").strip()
    if not all([start_date, end_date, name, phone, address]):
        flash("Please complete all booking fields.", "warning")
        return redirect(url_for("booking.book", car_id=car_id))
    card_digits = "".join(ch for ch in card_number if ch.isdigit())
    has_card_details = any([card_name, card_number, card_expiry, card_cvv])
    if has_card_details and (
        len(card_digits) < 12
        or len(card_digits) > 19
        or not card_name
        or not card_expiry
        or not (3 <= len(card_cvv) <= 4 and card_cvv.isdigit())
    ):
        flash("Please enter valid card details.", "warning")
        return redirect(url_for("booking.book", car_id=car_id))

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    if end_dt < start_dt:
        flash("End date must be after start date.", "danger")
        return redirect(url_for("booking.book", car_id=car_id))

    days = (end_dt - start_dt).days + 1
    total_rent = days * int(car.get("price_per_day", 0))

    # The lock keeps two users from submitting the same car booking together.
    if not acquire_lock(car_id, user_id):
        flash("This car is currently being processed by another user.", "warning")
        return redirect(url_for("user.car_details", car_id=car_id))
    try:
        booking_uid = _create_booking_with_transaction(
            car,
            user_id,
            car_id,
            start_dt,
            end_dt,
            days,
            total_rent,
            name,
            phone,
            address,
            payment_method,
            _masked_card_details(card_name, card_number, card_expiry) if has_card_details else {},
        )
        flash(
            f"Booked successfully. Booking ID: {booking_uid}. Pick up from EliteCarz {car.get('city')} outlet within 2 hours or booking will auto-cancel.",
            "success",
        )
    except BookingUnavailable:
        flash("Car is not available in selected dates.", "danger")
        return redirect(url_for("booking.book", car_id=car_id))
    finally:
        release_lock(car_id)
    return redirect(url_for("user.my_bookings"))
