from datetime import datetime
from flask import Blueprint, request, redirect, render_template, session, flash, url_for, make_response, current_app
from utils.db import db
from utils.auth import hash_password, check_password, login_user, logout_user, set_admin_login_cookie, clear_admin_cookie

auth_bp = Blueprint("auth", __name__)

# User IDs are generated in the same format as the seeded dataset.
def _next_user_id():
    count = db.users.count_documents({})
    return f"USR{count + 1:04d}"


@auth_bp.route("/")
def root():
    return redirect(url_for("auth.auth_portal"))


@auth_bp.route("/auth")
def auth_portal():
    return render_template("auth.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Normal users can sign in with username or email.
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        remember = request.form.get("remember") == "1"

        if not username or not password:
            flash("Please provide username and password.", "warning")
            return redirect(url_for("auth.login"))

        user = db.users.find_one(
            {"$or": [{"username": username}, {"email": username}], "role": "user"}
        )

        valid = False
        if user:
            if user.get("password") == "hashed_password":
                valid = password == "user123"
            else:
                valid = check_password(password, user["password"])
        if valid:
            login_user(user, remember=remember)
            return redirect(url_for("user.home"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        security_question = request.form.get("security_question", "").strip()
        security_answer = request.form.get("security_answer", "").strip()

        if not all([name, username, email, password, phone, address, security_question, security_answer]):
            flash("All signup fields are required.", "warning")
            return redirect(url_for("auth.signup"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "warning")
            return redirect(url_for("auth.signup"))

        existing = db.users.find_one({"$or": [{"username": username}, {"email": email}]})
        if existing:
            flash("Username or email already exists.", "danger")
            return redirect(url_for("auth.signup"))

        user = {
            "_id": _next_user_id(),
            "name": name,
            "username": username,
            "email": email,
            "phone": phone,
            "address": address,
            "password": hash_password(password),
            "security_question": security_question,
            "security_answer_hash": hash_password(security_answer.lower()),
            "role": "user",
            "version": 1,
            "created_at": datetime.utcnow(),
        }
        db.users.insert_one(user)
        flash("Signup successful. Please login.", "success")
        return redirect(url_for("auth.login"))
    return render_template("signup.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        answer = request.form.get("security_answer", "").strip().lower()
        new_password = request.form.get("new_password", "").strip()
        user = db.users.find_one({"username": username, "role": "user"})
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("auth.forgot_password"))
        if not user.get("security_answer_hash") or not check_password(answer, user["security_answer_hash"]):
            flash("Security answer is incorrect.", "danger")
            return redirect(url_for("auth.forgot_password"))
        db.users.update_one({"_id": user["_id"]}, {"$set": {"password": hash_password(new_password)}, "$inc": {"version": 1}})
        flash("Password updated successfully.", "success")
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")


@auth_bp.route("/guest-enter")
def guest_enter():
    session.clear()
    session["user_id"] = "GUEST"
    session["role"] = "guest"
    session["display_name"] = "Guest"
    flash("Guest mode enabled. You can browse only.", "info")
    return redirect(url_for("user.home"))


@auth_bp.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    # Admin login stays separate from the user session.
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username == "admin" and password == "admin123":
            resp = make_response(redirect(url_for("admin.admin_home")))
            resp = set_admin_login_cookie(
                resp,
                secret_key=current_app.secret_key,
                admin_user={"_id": "ADMIN", "role": "admin", "name": "Admin", "username": "admin"},
            )
            flash("Welcome Admin.", "success")
            return resp
        flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    resp = make_response(redirect(url_for("auth.auth_portal")))
    clear_admin_cookie(resp)
    flash("Logged out successfully.", "info")
    return resp


@auth_bp.route("/admin/logout")
def admin_logout():
    resp = make_response(redirect(url_for("auth.admin_login")))
    clear_admin_cookie(resp)
    flash("Admin logged out.", "info")
    return resp
