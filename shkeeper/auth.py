import functools
import os

from flask import Blueprint
from flask import flash
from flask import g
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask import current_app as app
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from shkeeper.models import User, Wallet
from shkeeper import db


bp = Blueprint("auth", __name__, url_prefix="/")

@bp.context_processor
def inject_theme():
    return {'theme': request.cookies.get('theme', 'light')}

def metrics_basic_auth(view):

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        metrics_username = os.environ.get('METRICS_USERNAME', 'shkeeper')
        metrics_password = os.environ.get('METRICS_PASSWORD', 'shkeeper')
        auth = request.authorization
        if not (auth and auth.username == metrics_username
                     and auth.password == metrics_password):
            return {'status': 'error', 'msg': 'authorization requred'}, 401
        return view(**kwargs)

    return wrapped_view

def basic_auth_optional(view):
    """View decorator that allow to authenticate using HTTP Basic Auth."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            auth = request.authorization
            if auth:
                user = User.query.filter_by(username=auth.username).first()
                if user and user.verify_password(auth.password):
                    g.user = user
                else:
                    return {"status": "error", "message": "Bad HTTP Basic Auth credentials"}
        return view(**kwargs)

    return wrapped_view

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            if "X-Shkeeper-Api-Key" in request.headers:
                return {"status": "error", "message": "This endpoint doesn't accept X-Shkeeper-Api-Key auth"}
            return redirect(url_for("auth.login"))

        return view(**kwargs)

    return wrapped_view

def api_key_required(view):

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "X-Shkeeper-Api-Key" not in request.headers:
            return {"status": "error", "message": "No API key"}

        apikey = request.headers["X-Shkeeper-Api-Key"]
        wallet = Wallet.query.filter_by(apikey=apikey).first()
        if wallet:
            return view(**kwargs)
        else:
            return {"status": "error", "message": "Bad API key"}

    return wrapped_view

@bp.before_app_request
def load_logged_in_user():
    """If a user id is stored in the session, load the user object into ``g.user``."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        user = User.query.get(user_id)
        if user.passhash:
            g.user = user
        else:
            session.clear()
            g.user = None


# @bp.before_app_request
# def load_api_user():
#     if "X-Shkeeper-Api-Key" in request.headers:
#         apikey = request.headers["X-Shkeeper-Api-Key"]

#         if request.path in [str(path) for path in app.url_map._rules_by_endpoint['api_v1.list_crypto']]:
#             wallet = Wallet.query.filter_by(apikey=apikey).first()
#             if wallet:
#                 g.user = User.query.get(1)

#         elif request.path.startswith("/api/v1/"):
#             crypto = request.path.split('/')[3]
#             wallet = Wallet.query.filter_by(crypto=crypto, apikey=apikey).first()
#             if wallet:
#                 g.user = User.query.get(1)



@bp.route("/login", methods=("GET", "POST"))
def login():
    """Log in a registered user by adding the user id to the session."""
    if request.method == "POST":
        username = request.form["name"]
        password = request.form["password"]
        error = None

        user = User.query.filter_by(username=username).first()

        if user is None:
            error = "Incorrect username."
        elif not password:
            error = "No password provided."
        elif not user.verify_password(password):
            error = "Incorrect password."

        if error is None:
            # store the user id in a new session and return to the index
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("wallet.show_unlock"))

        flash(error)
    else:
        if not User.query.get(1).passhash:
            return redirect(url_for("auth.set_password"))

    return render_template("auth/login.j2")

@bp.route("/set-password", methods=("GET", "POST"))
def set_password():
    admin = User.query.get(1)
    if admin.passhash:
        return redirect(url_for("auth.login"))
    if request.method == 'POST':
        if request.form['pw1'] == request.form['pw2']:
            admin.passhash = User.get_password_hash(request.form['pw1'])
            db.session.commit()
            return redirect(url_for("auth.login"))
        else:
            flash("Passwords doesn't match")
    return render_template("auth/set-password.j2")


@bp.route("/logout")
def logout():
    """Clear the current session, including the stored user id."""
    session.clear()
    return redirect(url_for("auth.login"))
