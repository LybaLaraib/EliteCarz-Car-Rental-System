from datetime import timedelta
from flask import Flask, g
from config import SECRET_KEY

from routes.auth_routes import auth_bp
from routes.user_routes import user_bp
from routes.admin_routes import admin_bp
from routes.booking_routes import booking_bp
from routes.review_routes import review_bp
from utils.auth import current_user

# Main Flask app setup and route registration.
app = Flask(__name__)
app.secret_key = SECRET_KEY

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 7


@app.before_request
def _inject_current_identity():
    # Keep identity data available for templates and role checks.
    g._secret_key = app.secret_key
    user_id, role, display_name = current_user(app.secret_key)
    g.user_id = user_id
    g.role = role
    g.display_name = display_name

# Blueprints are split by feature so routes stay easier to maintain.
app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(booking_bp)
app.register_blueprint(review_bp)

if __name__ == "__main__":
    app.run(debug=True)
