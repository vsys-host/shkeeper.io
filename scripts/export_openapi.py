import json
import os
from shkeeper import create_app

def main():
    app = create_app()
    with app.app_context():
        api = app.extensions["smorest"]
        spec = api.spec.to_dict()
        os.makedirs("static/openapi", exist_ok=True)
        path = "static/openapi/openapi.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()