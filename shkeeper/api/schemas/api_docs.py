from shkeeper.api.schemas.marshmallow_schemas import (
    DecryptionKeyErrorSchema,
    GetCryptoResponseSchema,
    TaskResponseSchema,
    BalancesResponseSchema,
    BalancesErrorSchema,
    ListAddressesResponseSchema,
    PaymentResponseSchema,
    PaymentRequestSchema,
    MultipayoutItemSchema,
    MultipayoutResponseSchema,
    ErrorPaymentResponseSchema,
    QuoteRequestSchema,
    QuoteResponseSchema,
    MetricsResponseSchema,
    ErrorSchema,
    PayoutCallbackSchema,
    PaymentCallbackSchema,
    BalanceResponseSchema,
    PayoutRequestSchema,
    PayoutResponseSchema,
    RetrieveTransactionsResponseSchema,
    InvoicesListResponseSchema,
    TxInfoResponseSchema,
    DecryptionKeyFormSchema,
    DecryptionKeySuccessSchema,
    PayoutStatusErrorSchema,
    PayoutStatusResponseSchema,
)

crypto_list_doc = {
    "description": (
        "Retrieve the list of available cryptocurrencies.\n\n"
        "Use `crypto_list` for integrations. "
        "The `crypto` field is kept only for backward compatibility."
    ),
    "tags": ["Cryptos"],
    "responses": {
        200: {
            "description": "Success – available cryptocurrencies retrieved",
            "content": {"application/json": {"schema": GetCryptoResponseSchema}},
        }
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/crypto'\n"
            ),
        }
    ],
}


crypto_balances_doc = {
    "description": (
        "Retrieve balances for all enabled cryptos, or for a subset "
        "specified via query parameter 'includes'."
    ),
    "tags": ["Cryptos"],
    "security": [{"API_Key": []}],
    "parameters": [
        {
            "name": "includes",
            "in": "query",
            "required": False,
            "description": (
                "Comma-separated list of crypto identifiers "
                "(e.g., BTC,ETH,TRX)"
            ),
            "schema": {"type": "string", "example": "BTC,ETH"},
        }
    ],
    "responses": {
        200: {
            "description": "Success – balances retrieved",
            "content": {"application/json": {"schema": BalancesResponseSchema}},
        },
        400: {
            "description": "Error – invalid includes or no valid cryptos requested",
            "content": {"application/json": {"schema": BalancesErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/crypto/balances?includes=BTC,ETH' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}


payment_request_doc = {
    "description": "Create a payment request",
    "tags": ["Payments"],
    "security": [{"API_Key": []}],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": PaymentRequestSchema}},
    },
    "responses": {
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": PaymentResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {
                "application/json": {"schema": ErrorPaymentResponseSchema}
            },
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request POST "
                "'https://demo.shkeeper.io/api/v1/ETH/payment_request' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                "--header 'Content-Type: application/json' \\\n"
                '--data-raw \'{"external_id":107,"fiat":"USD","amount":"18.25",'
                '"callback_url":"https://my-billing/callback.php"}\'\n'
            ),
        }
    ],
}

payout_callback_doc = {
    "description": (
        "SHKeeper sends a callback notification after a payout is completed.\n\n"
        "If `enable_payout_callback` is enabled, the callback will be sent automatically.\n"
        "If a `callback_url` was provided during payout creation, SHKeeper will send the notification to that URL."
    ),
    "tags": ["Notifications"],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": PayoutCallbackSchema}},
    },
    "responses": {
        202: {
            "description": "Callback accepted",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string", "example": "accepted"}}}}}
        },
        400: {
            "description": "Bad request",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "message": {"type": "string"}}}}}
        },
        500: {
            "description": "Internal server error",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "message": {"type": "string"}}}}}
        }
    }
}

metrics_doc = {
    "description": (
        "Retrieve system and cryptocurrency metrics.\n\n"
        "Authorization: HTTP Basic Auth using metric credentials. "
        "Metric credentials can be set via environment variables: METRICS_USERNAME, METRICS_PASSWORD. "
        "Default username/password: shkeeper/shkeeper."
    ),
    "tags": ["Metrics"],
    "security": [{"Basic_Metrics": []}],
    "responses": {
        200: {
            "description": "Success – metrics retrieved",
            "content": {"application/json": {"schema": MetricsResponseSchema}},
        },
        401: {
            "description": "Unauthorized – invalid credentials",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"msg": {"type": "string"}}}}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET 'https://demo.shkeeper.io/metrics' \\\n"
                "--header 'Authorization: Basic c2hrZWVwZXI6c2hrZWVwZXI='\n"
            ),
        }
    ],
}

transaction_callback_doc = {
    "description": (
        "SHKeeper sends payment notifications for invoice-related transactions.\n\n"
        "Each transaction is sent individually, and the transaction that triggered the callback has `trigger = true`.\n"
        "Your server should respond with HTTP 202 if successfully processed."
    ),
    "tags": ["Notifications"],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": PaymentCallbackSchema}},
    },
    "responses": {
        202: {
            "description": "Callback accepted",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string", "example": "accepted"}}}}}
        },
        400: {
            "description": "Bad request",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "message": {"type": "string"}}}}}
        },
        500: {
            "description": "Internal server error",
            "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "message": {"type": "string"}}}}}
        }
    }
}

quote_doc = {
    "description": "Create a quote",
    "tags": ["Cryptos"],
    "security": [{"API_Key": []}],
    "requestBody": {
        "required": False,
        "content": {"application/json": {"schema": QuoteRequestSchema}},
    },
    "responses": {
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": QuoteResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request POST "
                "'https://demo.shkeeper.io/api/v1/ETH/quote' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                "--header 'Content-Type: application/json' \\\n"
                '--data-raw \'{"fiat":"USD","amount":"100.00"}\'\n'
            ),
        }
    ],
}


balance_doc = {
    "description": (
        "Retrieve balance information for a specific crypto, "
        "including amount in crypto, fiat, and server status."
    ),
    "tags": ["Cryptos"],
    "security": [{"API_Key": []}],
    "responses": {
        200: {
            "description": "Success – balance retrieved",
            "content": {"application/json": {"schema": BalanceResponseSchema}},
        },
        400: {
            "description": "Error – crypto not enabled or invalid",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/ETH/balance' \\\n"
                "--header 'X-Shkeeper-Api-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}

payout_doc = {
    "description": "Create a single payout for the specified crypto.",
    "tags": ["Payouts"],
    "security": [{"Basic_Optional": []}, {"Basic": []}],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": PayoutRequestSchema}},
    },
    "responses": {
        200: {
            "description": "Payout task successfully created",
            "content": {"application/json": {"schema": PayoutResponseSchema}},
        },
        400: {
            "description": "Error creating payout",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request POST "
                "'https://demo.shkeeper.io/api/v1/BTC/payout' \\\n"
                "--header 'Authorization: Basic YOUR_BASIC_AUTH' \\\n"
                "--header 'Content-Type: application/json' \\\n"
                '--data-raw \'{"amount":100,"destination":"0x123...","fee":"10"}\'\n'
            ),
        }
    ],
}

task_status_doc = {
    "description": (
        "Check the status of a multi-payout task for the specified crypto."
    ),
    "tags": ["Other"],
    "security": [{"Basic_Optional": []}, {"Basic": []}],
    "responses": {
        200: {
            "description": "Task status (PENDING, SUCCESS, or FAILURE)",
            "content": {"application/json": {"schema": TaskResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/ETH-USDC/task/"
                "7028c45b-0c88-483e-b703-dd455a361b2e' \\\n"
                "--header 'Authorization: Basic YOUR_BASE64_CREDENTIALS'\n"
            ),
        }
    ],
}


multipayout_doc = {
    "description": "Execute a multi-payout for the specified crypto.",
    "tags": ["Payouts"],
    "security": [{"Basic_Optional": []}],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": MultipayoutItemSchema}},
    },
    "responses": {
        200: {
            "description": "Success",
            "content": {
                "application/json": {"schema": MultipayoutResponseSchema}
            },
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request POST "
                "'https://demo.shkeeper.io/api/v1/ETH-USDT/multipayout' \\\n"
                "--header 'Authorization: Basic YOUR_BASE64_CREDENTIALS' \\\n"
                "--header 'Content-Type: application/json' \\\n"
                "--data-raw '["
                '{"dest":"0xE77895BAda700d663f033510f73f1E988CF55756",'
                '"amount":"100","external_id":"43234",'
                '"callback_url":"https://my.payout.com/notification"},'
                '{"dest":"0x7C4C7D3010d31329dd8244617C46e460E5EF8a6F",'
                '"amount":"200.11","external_id":"43235",'
                '"callback_url":"https://my.payout.com/notification"}'
                "]'\n"
            ),
        }
    ],
}


addresses_doc = {
    "description": (
        "Retrieve all known wallet addresses for the specified crypto."
    ),
    "tags": ["Transactions"],
    "security": [{"API_Key": []}],
    "responses": {
        200: {
            "description": "Success",
            "content": {
                "application/json": {"schema": ListAddressesResponseSchema}
            },
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/ETH-USDC/addresses' \\\n"
                "--header 'X-Shkeeper-Api-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}


transactions_doc = {
    "description": (
        "Retrieve transactions for a given crypto and address. "
        "If none provided, returns all transactions."
    ),
    "tags": ["Transactions"],
    "security": [{"API_Key": []}],
    "responses": {
        200: {
            "description": "Success",
            "content": {
                "application/json": {
                    "schema": RetrieveTransactionsResponseSchema
                }
            },
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/transactions/ETH/"
                "0xDCA83F12D963c7233E939a32e31aD758C7cCF307' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}


invoices_doc = {
    "description": (
        "Retrieve invoices. Optionally filter by external_id. "
        "Excludes invoices with status 'OUTGOING'."
    ),
    "tags": ["Invoices"],
    "security": [{"API_Key": []}],
    "responses": {
        200: {
            "description": "List of invoices",
            "content": {
                "application/json": {"schema": InvoicesListResponseSchema}
            },
        },
        400: {
            "description": "Error occurred",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/invoices/107' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}


tx_info_doc = {
    "description": "Retrieve transaction info by txid and external_id.",
    "tags": ["Transactions"],
    "security": [{"API_Key": []}],
    "responses": {
        200: {
            "description": "Success",
            "content": {
                "application/json": {"schema": TxInfoResponseSchema}
            },
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/tx-info/"
                "0xbcf68720db79454f40b2acf6bfb18897d497ab4d8bc9faf243c859d14d5d6b66/240' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}


decryption_key_doc = {
    "description": (
        "Create an encryption key (enter a decryption key via API)."
    ),
    "tags": ["Encryption"],
    "security": [{"API_Key": []}],
    "requestBody": {
        "required": False,
        "content": {
            "multipart/form-data": {
                "schema": DecryptionKeyFormSchema
            }
        },
    },
    "responses": {
        200: {
            "description": "Success",
            "content": {
                "application/json": {
                    "schema": DecryptionKeySuccessSchema
                }
            },
        },
        400: {
            "description": "Error",
            "content": {
                "application/json": {
                    "schema": DecryptionKeyErrorSchema
                }
            },
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request POST "
                "'https://demo.shkeeper.io/api/v1/decryption-key' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                "--form 'key=asdfasfasgasgasgasgdeagweg'\n"
            ),
        }
    ],
}


payout_status_doc = {
    "description": (
        "Retrieve payout status by external_id for the specified "
        "cryptocurrency."
    ),
    "tags": ["Payouts"],
    "security": [{"API_Key": []}],
    "parameters": [
        {
            "name": "external_id",
            "in": "query",
            "required": True,
            "description": "External ID assigned to the payout",
            "schema": {"type": "string", "example": "abc123"},
        }
    ],
    "responses": {
        200: {
            "description": "Payout status retrieved",
            "content": {
                "application/json": {
                    "schema": PayoutStatusResponseSchema
                }
            },
        },
        400: {
            "description": "Missing external_id parameter",
            "content": {
                "application/json": {
                    "schema": PayoutStatusErrorSchema
                }
            },
        },
        404: {
            "description": "Payout not found",
            "content": {
                "application/json": {
                    "schema": PayoutStatusErrorSchema
                }
            },
        },
    },
    "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/BTC/payout/status"
                "?external_id=abc123' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
            ),
        }
    ],
}
