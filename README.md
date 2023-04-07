# shkeeper.io<!-- omit in toc -->

- [API for plugins](#api-for-plugins)
  - [Auth](#auth)
  - [List available cryptos with GET `/api/v1/crypto`](#list-available-cryptos-with-get-apiv1crypto)
  - [Create a payment request with POST `/api/v1/<crypto>/payment_request`](#create-a-payment-request-with-post-apiv1cryptopayment_request)
  - [Payment notifications format](#payment-notifications-format)


## API for plugins

### Auth

To authenticate to shkeeper.io use `X-Shkeeper-API-Key` HTTP header in a request:

```
X-Shkeeper-API-Key: <api key>
```

Curl example:

```
curl -H "X-Shkeeper-API-Key: wvoNQaHswSBk9rZu" https://<shkeeper.io_url>/api/v1/crypto
```

### List available cryptos with GET `/api/v1/crypto`

Request example:

```
curl -H "X-Shkeeper-API-Key: wvoNQaHswSBk9rZu" https://<shkeeper.io_url>/api/v1/crypto
```

Response:

```jsonc
{
  "status": "success",
  "crypto": ["BTC", "LTC", "DOGE"],
  "crypto_list": [{"name": "BTC", "display_name": "Bitcoin"}, ...]
}
```

### Create a payment request with POST `/api/v1/<crypto>/payment_request`

Request format:

```jsonc
{
  "external_id": "1",  // an invoice or an order ID
  "fiat": "USD",       // fiat currency
  "amount": 100,       // fiat currency amount
  "callback_url": "https://my-billing-system/callback.php"  // URL where shkeeper.io should send a payment notification
}
```

Request example via curl:

```
curl -d '{"external_id":"1","fiat":"USD","amount":100,"callback_url":"https://my-billing-system/callback.php"}' \
     -H "X-Shkeeper-API-Key: wvoNQaHswSBk9rZu" \
     https://<shkeeper.io_url>/api/v1/BTC/payment_request
```

Response (on success):

```jsonc
{
  "status": "success",
  "id": 1,  // Invoice ID in shkeeper.io
  "exchange_rate": "40000.00",  // crypto currency to fiat currency exchange rate
  "amount": 0.0025,  // crypto currency amount
  "wallet": "1bcxxxxxxxxxxxxxxxxxxx"  // crypto currency wallet address
}
```

Response (on error):

```jsonc
{
    "status":"error",
    "message":"error description"
}
```

### Payment notifications format

Once shkeeper.io receives a payment it will send a payment notification to the `<callback_url>` using POST with json-encoded body and `X-Shkeeper-API-Key` HTTP header to authenticate to your system:

```jsonc
{
  "external_id": "1",  // Invoice or Order ID in the external system
  "crypto": "BTC",  // crypto currency (provided during payment request creation)
  "fiat":   "USD",  // fiat currency (provided during payment request creation)
  "balance_fiat":      "100",  // amount in fiat currency
  "balance_crypto": "0.0025",  // amount in crypto currency
  "fee_percent": "2",  // fee percent added to invoice amount
  "paid": true,  // true  -- if the payment request is fully paid
                 // false -- when only a partial payment received
  "transactions": [  // list of transactions related to the payment request
    {
      "txid": "ZZZZZZZZZZZZZZZZZZZ",  // blockchain transaction ID
      "date": "2022-04-01 11:22:33",  // transaction date
      "amount_crypto": "0.0025",      // transaction amount in crypto currency
      "amount_fiat": "100",           // transaction amount in fiat currency
      "trigger": true,  // true -- if this transaction was a trigger for payment notification
    },
    ...
  ]
}
```

If a payment notification was successfuly processed by your server, it should return HTTP code `202 Accepted`. Any other response or connection failure will cause shkeeper.io to send a payment notification again in 60 seconds.