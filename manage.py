#!/usr/bin/env python
from shkeeper import create_app, db
from flask_migrate import Migrate
from flask.cli import FlaskGroup

# create new migration
# flask --app manage.py db migrate -m "add callback to payout"

app = create_app()
migrate = Migrate(app, db)
cli = FlaskGroup(app)

if __name__ == "__main__":
    cli()
