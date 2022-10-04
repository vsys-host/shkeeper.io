import os
import logging
import secrets
from decimal import Decimal

from flask import Flask

from .utils import format_decimal

from flask_apscheduler import APScheduler
scheduler = APScheduler()

# from logging.config import dictConfig
# dictConfig({
#     'version': 1,
#     'formatters': {'default': {
#         'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
#     }},
#     'handlers': {'wsgi': {
#         'class': 'logging.StreamHandler',
#         'stream': 'ext://flask.logging.wsgi_errors_stream',
#         'formatter': 'default'
#     }},
#     'root': {
#         'level': 'INFO',
#         'handlers': ['wsgi']
#     }
# })

import flask_sqlalchemy
db = flask_sqlalchemy.SQLAlchemy()


def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # a default secret that should be overridden by instance config
        SECRET_KEY="dev",
        # store the database in the instance folder
        DATABASE=os.path.join(app.instance_path, "shkeeper.sqlite"),
        SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(app.instance_path, "shkeeper.sqlite"),
        SUGGESTED_WALLET_APIKEY=secrets.token_urlsafe(16),
        SESSION_TYPE='filesystem',
        SESSION_FILE_DIR=os.path.join(app.instance_path, "flask_session"),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.update(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from flask_session import Session
    Session(app)

    scheduler.init_app(app)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)

    from flask.json import JSONDecoder, JSONEncoder
    from decimal import Decimal
    class ShkeeperJSONDecoder(JSONDecoder):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, parse_float=Decimal, **kwargs)

    class ShkeeperJSONEncoder(JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return str(obj)
            return super().default(self, obj)

    app.json_decoder = ShkeeperJSONDecoder
    app.json_encoder = ShkeeperJSONEncoder

    db.init_app(app)
    with app.app_context():

        # Create tables according to models
        from .models import Wallet, User, PayoutDestination, Invoice, ExchangeRate, Invoice
        db.create_all()

        # Create default user
        default_user = 'admin'
        if not User.query.filter_by(username=default_user).first():
            admin = User(username=default_user)
            db.session.add(admin)
            db.session.commit()

        # Register rate sources
        import shkeeper.modules.rates

        # Register crypto
        from .modules import cryptos
        from .modules.classes.crypto import Crypto
        for crypto in Crypto.instances.values():
            Wallet.register_currency(crypto)
            crypto._wallet = Wallet
            ExchangeRate.register_currency(crypto)



        from . import tasks
        scheduler.start()

        # end of with app.app_context():

    # template filters
    app.jinja_env.filters['format_decimal'] = format_decimal

    # apply the blueprints to the app
    from . import auth, wallet, api_v1, callback

    app.register_blueprint(auth.bp)
    app.register_blueprint(wallet.bp)
    app.register_blueprint(api_v1.bp)
    app.register_blueprint(callback.bp)

    return app
