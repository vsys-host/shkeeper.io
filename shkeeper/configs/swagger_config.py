# swagger_config.py
API_TITLE = "SHKeeper API"
API_VERSION = "2.3.5"
OPENAPI_VERSION = "3.0.3"
OPENAPI_URL_PREFIX = "/"
OPENAPI_JSON_PATH = "openapi.json"
OPENAPI_SWAGGER_UI_PATH = "/docs"
OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

API_SPEC_OPTIONS = {
    "info": {
        "description": (
            "# Introduction\n"
            "SHKeeper - is an open-source, self-hosted cryptocurrency payment processor. "
            "It uniquely serves as both a gateway and a merchant, enabling you to accept payments "
            "in various cryptocurrencies without fees and intermediaries.\n\n"
            "# Authentication\n"
            "You can authenticate either via Basic Auth or an API key depending from endpoint requirement. "
            "You can generate or view an API key in the SHKeeper UI under `Wallets` -> `Manage` -> `API key`. "
            "For metrics endpoints, use `METRICS_USERNAME` and `METRICS_PASSWORD`.\n\n"
            "<!-- Redoc-Inject: <security-definitions> -->\n"
        ),
        "contact": {"email": "support@shkeeper.io", "url": "https://shkeeper.io"},
        "x-logo": {"url": "https://shkeeper.io/images/shkeeper-logo.svg", "altText": "SHKeeper logo"},
        "license": {"name": "GPL-3.0", "url": "https://github.com/vsys-host/shkeeper.io"},
    },
    "servers": [{"url": "https://demo.shkeeper.io"}],
    "tags": [
        {"name": "Cryptos", "x-displayName": "Available crypto", "description": "Crypto currency operations"},
        {"name": "Invoices", "x-displayName": "Invoices", "description": "Invoices operations"},
        {"name": "Payouts", "x-displayName": "Payouts", "description": "Payouts operations"},
        {"name": "Payments", "x-displayName": "Payments", "description": "Payments operations"},
        {"name": "Metrics", "x-displayName": "Metrics", "description": "Metrics operations"},
        {"name": "Transactions", "x-displayName": "Transactions", "description": "Transaction operations"},
        {"name": "Encryption", "x-displayName": "Wallet encryption", "description": "Wallet encryption operations"},
        {"name": "Other", "x-displayName": "Useful endpoints", "description": "Other operations"},
    ],
    "x-tagGroups": [
        {"name": "Obtain crypto address", "tags": ["Cryptos", "Invoices"]},
        {"name": "Payouts", "tags": ["Payouts"]},
        {"name": "Payments", "tags": ["Payments"]},
        {"name": "Transactions", "tags": ["Transactions"]},
        {"name": "Security", "tags": ["Encryption"]},
        {"name": "Other", "tags": ["Other", "Metrics"]},
    ],
}

SECURITY_SCHEMES = {
    "API_Key": {
        "type": "apiKey",
        "description": (
            "Send the API Key in header: `X-Shkeeper-Api-Key {API Key}`."
        ),
        "name": "X-Shkeeper-Api-Key",
        "in": "header",
    },
    "Basic": {
        "type": "http",
        "description": (
            "Basic HTTP authentication: `Basic {base64(username:password)}`. "
            "Used for payout endpoints and metrics."
        ),
        "scheme": "basic",
    },
    "Basic_Optional": {
        "type": "http",
        "description": (
            "Optional Basic Auth. If header is provided, user is attached to context. "
            "Otherwise request is anonymous."
        ),
        "scheme": "basic",
    },
}
