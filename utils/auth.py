import bcrypt
from functools import wraps
from flask import g, session, redirect, url_for, flash, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_ADMIN_COOKIE = "elitecarz_admin"
_ADMIN_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 7

# Password helpers keep hashing details out of the route files.
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def _serializer(secret_key: str):
    return URLSafeTimedSerializer(secret_key=secret_key, salt="elitecarz-auth")


def login_user(user, remember: bool = False):
    session["user_id"] = user["_id"]
    session["role"] = user["role"]
    session["display_name"] = user.get("username") or user.get("name", "User")
    session.permanent = bool(remember)


def set_admin_login_cookie(response, secret_key: str, admin_user: dict):
    # Admin login uses a signed cookie so user sessions can stay separate.
    s = _serializer(secret_key)
    token = s.dumps({"user_id": admin_user.get("_id", "ADMIN"), "role": "admin", "name": admin_user.get("name", "Admin")})
    response.set_cookie(
        _ADMIN_COOKIE,
        token,
        max_age=_ADMIN_COOKIE_MAX_AGE_S,
        httponly=True,
        samesite="Lax",
    )
    return response


def clear_admin_cookie(response):
    response.delete_cookie(_ADMIN_COOKIE)
    return response


def current_user(secret_key: str | None = None):
    # Admin routes read the signed cookie; user pages read the Flask session.
    if request.path.startswith("/admin") and secret_key:
        token = request.cookies.get(_ADMIN_COOKIE)
        if token:
            s = _serializer(secret_key)
            try:
                payload = s.loads(token, max_age=_ADMIN_COOKIE_MAX_AGE_S)
                return payload.get("user_id"), payload.get("role"), payload.get("name", "Admin")
            except (BadSignature, SignatureExpired):
                pass
    return session.get("user_id"), session.get("role"), session.get("display_name")

def logout_user():
    session.clear()

def is_guest():
    return session.get("role") == "guest"


def require_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_id, role, _ = current_user(None)
        if not user_id or role == "guest":
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    return wrapper

def require_role(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # This check is used by both user-only and admin-only pages.
            secret_key = getattr(g, "_secret_key", None)
            _, r, _ = current_user(secret_key)
            if r != role:
                flash("Access denied for this page.", "danger")
                if role == "admin":
                    return redirect(url_for("auth.admin_login"))
                return redirect(url_for("auth.login"))
            return func(*args, **kwargs)
        return wrapper
    return decorator
