# SHKeeper.io<!-- omit in toc -->

![SHKeeper logo](https://github.com/user-attachments/assets/dd573f14-1b8e-47d7-86e5-59f24b67b027)               

- [About SHKeeper](#about-shkeeper)
 - [Demo](#demo)
 - [Helpful links](#helpful-links)
- [Available coins](#available-coins)
- [Features](#features)
- [Installation](#installation)
- [Developing](#developing)
  - [Payment flow](#payment-flow)
  - [API](#api)
     - [Auth](#auth)
        - [ApiKey](#apikey)
        - [Basic (used only for Payout)](#basic-used-only-for-payout)
     - [Retrieve the list of available cryptocurrencies](#retrieve-the-list-of-available-cryptocurrencies)
     - [Invoice creation](#invoice-creation)
     - [Retrieve created addresses](#retrieve-created-addresses)
     - [Retrieve transactions by address](#retrieve-transactions-by-address)
     - [Retrieve information by external_id](#retrieve-information-by-external_id)
     - [Retrieve information by the pair of transaction_id and external_id](#retrieve-information-by-the-pair-of-transaction_id-and-external_id)
     - [Wallet encryption (Enter decryption_key via API)](#wallet-encryption-enter-decryption_key-via-api)
     - [Retrieving metrics](#retrieving-metrics)
     - [Payout](#payout)
     - [Payout related endpoints](#payout-related-endpoints)
        - [Creating a payout task](#creating-a-payout-task)
        - [Creating a multipayout task](#creating-a-multipayout-task)
        - [Checking task status](#checking-task-status)
        - [Get crypto balance information](#get-crypto-balance-info)
  - [Receiving callback](#receiving-callback)
  - [Ready-made modules](#ready-made-modules)
     - [WHMCS](#whmcs)
     - [WooCommerce WordPress](#woocommerce-wordpress)
     - [Opencart 3](#opencart-3)
     - [Prestashop 8](#prestashop-8)
- [Be involved](#be-involved)
- [Contact us](#contact-us)
  
<a name="about-shkeeper"></a>
## 1. About SHKeeper

SHKeeper - is an open-source, self-hosted cryptocurrency payment processor. It uniquely serves as both a gateway and a merchant, enabling you to accept payments in various cryptocurrencies without fees and intermediaries.

<a name="demo"></a>
### 1.1. Demo

SHKeeper demo version is available from us (works in testnet network), so you can try it yourself without installing it:

https://demo.shkeeper.io/

**Login:** admin 

**Password:** admin  

<a name="helpful-links"></a>
### 1.2. Helpful links

**Details of the latest version can be found here:** https://github.com/vsys-host/shkeeper.io/commits/main/

**Find the comprehensive list of API endpoints here https://shkeeper.io/api/**

**Tutorial video:** https://www.youtube.com/watch?v=yYK_JAm1_hg

**Find the knowledge base here:** https://shkeeper.io/kb/launch/what-is-shkeeper

**Latest announcements:** https://shkeeper.io/news

<a name="available-coins"></a>
## 2. Available coins
SHKeeper offers a direct way to receive BTC, ETH, LTC, DOGE, XMR, XRP, TRX, BNB, SOL, MATIC, AVAX, FIRO, USDT (ERC20, TRC20, BEP-20, Polygon, Avalanche), USDC (ERC20, TRC20, BEP-20, Polygon, Avalanche).

<img width="2060" height="800" alt="Group 2614" src="https://github.com/user-attachments/assets/d44d5343-cd90-473f-a63f-dd1b1b74e8c5" />

<a name="features"></a>
## 3. Features

1. Non-custodial
2. Multi-currency
3. No transaction fees & third parties
4. Direct crypto payments
5. Easily embed payment buttons / QR-code
6. Ability to set your exchange rates, commissions, or fees
7. Crediting the overpayment to the balance
8. Partial payments
9. Setting auto-payments into a cold wallet
10. Increased privacy and security
11. No KYC or AML
12. Multipayout

![image](https://github.com/user-attachments/assets/e7c637af-8da6-455b-80f5-9b054cfff03b)

<a name="installation"></a>
## 4. Installation

Install k3s and helm on a fresh server (tested on Ubuntu 22):

```
# curl -sfL https://get.k3s.io | sh -
# mkdir /root/.kube && ln -s /etc/rancher/k3s/k3s.yaml /root/.kube/config
# curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

Create Shkeeper chart configuration file `values.yaml` with BTC, LTC, DOGE, XMR enabled:

```
# cat << EOF > values.yaml

#
# General
#

storageClassName: local-path

#
# BTC and forks
#

btc:
  enabled: true
ltc:
  enabled: true
doge:
  enabled: true

#
# Monero
#

monero:
  enabled: true
  fullnode:
    enabled: true
EOF
```

Install Shkepeer helm chart:

```
# helm repo add vsys-host https://vsys-host.github.io/helm-charts
# helm repo add mittwald https://helm.mittwald.de
# helm repo update
# helm install kubernetes-secret-generator mittwald/kubernetes-secret-generator
# helm install -f values.yaml shkeeper vsys-host/shkeeper
```

Login to Shkeeper: http://\<ip>\:5000/


### Install auto SSL

Install cert-manager:

```
# helm repo add jetstack https://charts.jetstack.io
# helm install \
  cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.9.1 \
  --set installCRDs=true
```

Create CRDs, replace "demo.shkeeper.io" and "support@v-sys.org" with your own domain and email address:

```
cat << EOF > ssl.yaml
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: shkeeper-cert
  namespace: shkeeper
spec:
  commonName: demo.shkeeper.io
  secretName: shkeeper-cert
  dnsNames:
    - demo.shkeeper.io
  issuerRef:
    name: letsencrypt-production
    kind: ClusterIssuer
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-production
spec:
  acme:
    email: support@v-sys.org
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: your-own-very-secretive-key
    solvers:
      - http01:
          ingress:
            class: traefik
---
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: shkeeper
  namespace: shkeeper
spec:
  entryPoints:
    - web
    - websecure
  routes:
    - match: Host(`demo.shkeeper.io`)
      kind: Rule
      services:
        - name: shkeeper
          port: 5000
          namespace: shkeeper
  tls:
    secretName: shkeeper-cert
EOF
```

Apply CRDS:

```
# kubectl apply -f ssl.yaml
```

After a few minutes, your Shkeeper should be reachable on https://\<your domain\> and have a valid SSL.
<a name="developing"></a>
## 5. Developing
<a name="payment-flow"></a>
**Find the comprehensive list of endpoints here https://shkeeper.io/api/**
### 5.1. Payment flow
The process of accepting payments through SHKeeper works as follows:
Once you have installed SHKeeper and see active Wallets in the SHKeeper admin panel, you can start configuring your store to work with SHKeeper. SHKeeper operates on an invoice-based system, where each created invoice in SHKeeper corresponds to a unique address for the respective cryptocurrency. This allows you to identify the customer who made the payment.

Creating an invoice requires passing the `X-Shkeeper-Api-Key` in the header, and you also need to know the cryptocurrency name to form the endpoint for the request.

To begin, you need to obtain a list of cryptocurrencies available for invoice creation from SHKeeper (these are the ones that are online and not disabled in the admin panel).
<p align="center">
  <img src="https://github.com/user-attachments/assets/66374540-21de-4cb1-a07f-0813600b743c" alt="image6">
</p>

To do this, use the [endpoint](#retrieve-the-list-of-available-cryptocurrencies) `/api/v1/crypto`. This endpoint does not require authorization. The retrieved list can be displayed to the customer to choose the desired cryptocurrency for payment.

Next, create an invoice for the selected cryptocurrency using the [endpoint](#invoice-creation) `/api/v1/{crypto_name}/payment_request`. An invoice in SHKeeper should be created at the stage when you already know the unique `order_id /invoice_id` in your system, and only for the cryptocurrency chosen by the customer (do not create invoices for all cryptocurrencies received from SHKeeper immediately, as this will generate excess addresses that will not be used later). Invoices in SHKeeper are unique, one invoice will be created in the SHKeeper system for one `external_id`. The customer can change their mind and generate an address for another cryptocurrency; in this case, simply create an invoice for the new cryptocurrency as usual, and SHKeeper will automatically update the information in the already created invoice and provide you with a new payment address. If the customer pays to the previously generated address, SHKeeper will process the payment, and you will receive a notification (callback) about this payment, as SHKeeper saves all addresses generated by the customer. For each cryptocurrency, the customer receives a unique cryptocurrency address linked to their specific `order_id` (invoice_id). This address remains the same even if you send another request to SHKeeper to create the same invoice.

When creating an invoice in SHKeeper, provide a `callback_url` to indicate where SHKeeper should send a notification (callback) upon receiving a transaction associated with this invoice. When transactions are received for the corresponding invoice, SHKeeper updates the status of the invoice. An invoice in SHKeeper can be in one of the following statuses: UNPAID, PARTIAL, PAID, OVERPAID. You receive the current status of the invoice in the callback.

- **UNPAID**: The initial status for a newly created invoice, where no transactions have been made.
- **PARTIAL**: The status for an invoice that has received a transaction, but the amount is insufficient for full payment.
- **PAID**: A fully paid invoice in SHKeeper. You can influence the thresholds for when an invoice is considered fully paid by using the appropriate setting in the wallet.
  
<p align="center">
  <img src="https://github.com/user-attachments/assets/7c04fd4f-d04f-4112-b5c0-468ba98b4686" alt="image5">
</p>

- **OVERPAID**: The status when the client has sent a total amount in transactions that exceed the sum of the generated invoice. You can influence the thresholds for when an invoice is considered overpaid by using the appropriate setting in the wallet.
  
<p align="center">
  <img src="https://github.com/user-attachments/assets/ea1f48be-00bf-4fc2-beaa-bcd90789025e" alt="image2">
</p>

You can consider the SHKeeper invoice status when developing a payment module for your store, but be mindful when using the `overpaid_fiat`  value from the callback in the OVERPAID status.
By default, when adding a transaction and calculating the amount in fiat, SHKeeper uses the cryptocurrency exchange rate that was in effect at the time the invoice was created or updated. However, you can adjust this behavior by configuring the relevant field in the wallet settings.
<p align="center">
  <img src="https://github.com/user-attachments/assets/4ad2ee1f-652a-43da-81f3-8e913d931144" alt="image3">
</p>

If you have set “Recalculate invoice rate” to a value other than 0, then in the case of an invoice being paid after the specified time, the exchange rate will be the one at the moment the transaction is credited. When creating an invoice in SHKeeper, an object is returned that includes the `recalculate_after` field, allowing you to inform the customer of how long the current exchange rate will be held for them.

#### Static address mode (advanced)

For businesses that need a permanent deposit address per customer (e.g., exchanges, custodial flows, recurring deposits), SHKeeper supports a “static address” usage pattern **without** changing the core invoice mechanics:

1. **Create a “large” reusable invoice per customer and per coin.**  
   Set an intentionally high target amount so the invoice never reaches the “fully paid” state during normal operation. This lets you reuse the **same address** for many deposits from the same customer.

2. **Keep the address static by reusing the same invoice.**  
   Each invoice in SHKeeper maps to a unique blockchain address. By reusing that invoice, you keep the deposit address unchanged for the customer.

3. **Control pricing exposure with “Recalculate invoice rate after”.**  
   Set a minimal recalculation period (e.g., 1 hour) so fiat/crypto conversion snapshots are refreshed at your cadence. Within the configured period, the rate remains fixed; after it expires, the next transactions will use the updated rate snapshot automatically.

**Notes & caveats**

- This approach preserves a **static deposit address** while keeping rate handling predictable via the recalculation window.  
- Standard invoice thresholds (under/overpayment windows) and confirmations still apply.  
- Accounting & reconciliation remain invoice-centric: you attribute multiple deposits to the same customer by keeping a dedicated invoice per customer/coin.

<a name="api"></a>
### 5.2. API 
<a name="auth"></a>
#### 5.2.1. Auth
<a name="apikey"></a>
##### 5.2.1.1. ApiKey

Go to SHKeeper and either view or generate a new API Key.
![image4](https://github.com/user-attachments/assets/2d97d861-f5f5-44de-9b44-3be913d165d2)
![image1](https://github.com/user-attachments/assets/1737bc56-2531-4e03-9d47-15af080da336)


The API key is the same for each wallet, so you can perform this procedure on any available one.

SHKeeper supports user authentication and authorization through an API Key generated by the user. Send the API Key as a header value to Authorization with the format: `X-Shkeeper-Api-Key {API Key}`

The only request that does not require authorization is the one for retrieving the list of active cryptocurrencies: `GET /api/v1/crypto`
<a name="basic-used-only-for-payout"></a>
##### 5.2.1.2. Basic (used only for Payout)
SHKeeper supports authenticating and authorizing user through the Basic HTTP authentication scheme only for Payout related API calls. Send the user and password encoded in base64 with the format `Basic {base64(username:password)}`. Using this authentication is required for payout-related [endpoints](#payout-related-endpoints).
<a name="retrieve-the-list-of-available-cryptocurrencies"></a>
#### 5.2.2. Retrieve the list of available cryptocurrencies

**Endpoint:** `/api/v1/crypto`     
**Authorization:** No authorization is required.   
**HTTP request method:** GET  
**Example Curl request:**  

```
curl --location --request GET 
'https://demo.shkeeper.io/api/v1/crypto'
```
**Successful response:**
```
{
    "crypto": [
        "BNB",
        "ETH",
        ...
    ],
    "crypto_list": [
        {
            "display_name": "BNB",
            "name": "BNB"
        },
        {
            "display_name": "Ethereum",
            "name": "ETH"
        },
        ...
    ],
    "status": "success"
}
```
Use the `crypto_list` array; the `crypto` array exists only for backward compatibility. In the `crypto_list` array:
- `name` is used when forming the endpoint for invoice creation requests,
- `display_name` is the cryptocurrency human-readable format.
<a name="invoice-creation"></a>
#### 5.2.3. Invoice Creation

**Endpoint:** `/api/v1/<crypto_name>/payment_request`  
**Authorization:** ApiKey.   
**HTTP request method:**  POST request with a JSON object in the following format:  
```
{
    "external_id":<order_id>,
    "fiat":"USD",
    "amount":"<order_amount>",
    "callback_url":"<callback_script_url>"
}
```

- `external_id`: A unique order_id or invoice_id from your store.
- `fiat`: Currency code in ISO 4217 format for conversion. Currently, only USD is supported.
- `amount`: The amount for which the invoice should be created in SHKeeper.
- `callback_url`: The URL to which SHKeeper will send notifications in the event of transactions related to the created invoices.

SHKeeper uses pair  `external_id` and `callback_url` as invoice identificator and update invoice in case repeating it on the next invoice creation requests.
**Example Curl request:**
```
curl --location --request POST 'https://demo.shkeeper.io/api/v1/ETH/payment_request' \
--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY' \
--header 'Content-Type: application/json' \
--data-raw '{"external_id":107,"fiat":"USD","amount":"18.25","callback_url":"https://my-billing/callback.php"}'
```
**Success Example Response:**
```
{
    "amount": "0.01080125",
    "display_name": "Ethereum",
    "exchange_rate": "3379.24",
    "id": 61,
    "recalculate_after": 0,
    "status": "success",
    "wallet": "0x8695f1a224e28adf362E6f8a8E695EDCc5D64960"
}
```
**Unavailable Crypto Response:**
```
{
    "message": "BTC payment gateway is unavailable",
    "status": "error"
}
```
<a name="quote-generation"></a>
#### 5.2.3.1 Quote Generation

**Endpoint:** `/api/v1/<crypto_name>/quote`  
**Authorization:** ApiKey.  
**HTTP request method:** POST request with a JSON object in the following format:  
```json
{
    "fiat": "USD",
    "amount": "100.00"
}
```

- `fiat`: Currency code in ISO 4217 format for conversion. Currently, only USD is supported.
- `amount`: The amount for which the crypto quote should be generated.

This endpoint returns the crypto amount equivalent and the exchange rate used for the conversion. It does **not** create an invoice and is intended for informational purposes (e.g., showing the user how much crypto they'll need to pay before generating a real invoice).

**Example Curl request:**
```bash
curl --location --request POST 'https://demo.shkeeper.io/api/v1/ETH/quote' \
--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY' \
--header 'Content-Type: application/json' \
--data-raw '{"fiat":"USD","amount":"100.00"}'
```

**Success Example Response:**
```json
{
    "crypto_amount": "0.02981237",
    "exchange_rate": "3353.26",
    "status": "success"
}
```

**Unavailable Crypto Response:**
```json
{
    "message": "BTC payment gateway is unavailable",
    "status": "error"
}
```
<a name="retrieve-created-addresses"></a>
#### 5.2.4. Retrieve created addresses

**Endpoint:** `/api/v1/<crypto_name>/addresses`  
**Authorization:** ApiKey.   
**HTTP request method:** GET  
**Example Curl request:**  
```
curl --location --request GET 'https://demo.shkeeper.io/api/v1/ETH-USDC/addresses' \
--header 'X-Shkeeper-Api-Key: nApijGv8djih7ozY'
```
**Successful Response:**
```
{
    "addresses": [
        "0x0A71f4741DcaD3C06AA51eE6cF0E22675507d0d0",
        …
        "0x8695f1a224e28adf362E6f8a8E695EDCc5D64960"
    ],
    "status": "success"
}
```
<a name="retrieve-transactions-by-address"></a>
#### 5.2.5. Retrieve transactions by address
**Endpoint:** `/api/v1/transactions/<crypto_name>/<addr>`  
**Authorization:** ApiKey.   
**HTTP request method:** GET  
**Curl Example:**  
```
curl --location --request GET 'https://demo.shkeeper.io/api/v1/transactions/ETH/0xDCA83F12D963c7233E939a32e31aD758C7cCF307' \
--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY'
```
**Successful Response:**
```
{
    "status": "success",
    "transactions": [
        {
            "addr": "0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
            "amount": "0.0001000000",
            "crypto": "ETH",
            "status": "CONFIRMED",
            "txid": "0xbcf68720db79454f40b2acf6bfb18897d497ab4d8bc9faf243c859d14d5d6b66"
        }
    ]
}
```
**Not Found Response:**
```
{
    "status": "success",
    "transactions": []
}
```
<a name="retrieve-information-by-external_id"></a>
#### 5.2.6. Retrieve information by external_id
**Endpoint:** `/api/v1/invoices/<external_id>`  
**Authorization:** ApiKey.  
**HTTP request method:** GET  
**Curl Example:**  
```
curl --location --request GET 'https://demo.shkeeper.io/api/v1/invoices/107' \
--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY'
```
**Successful Response:**
```
{
    "invoices": [
        {
            "amount_fiat": "18.2500000000",
            "balance_fiat": "0E-10",
            "external_id": "107",
            "fiat": "USD",
            "status": "UNPAID",
            "txs": []
        }
    ],
    "status": "success"
}
```
**Not Found Response:**
```
{
    "invoices": [],
    "status": "success"
}
```
<a name="retrieve-information-by-the-pair-of-transaction_id-and-external_id"></a>
#### 5.2.7. Retrieve information by the transaction_id and external_id
**Endpoint:** `/api/v1/tx-info/<tx_id>/<external_id>`  
**Authorization:** ApiKey.   
**HTTP request method:** GET  
**Curl Example:**  
```
curl --location --request GET 'https://demo.shkeeper.io/api/v1/tx-info/0xbcf68720db79454f40b2acf6bfb18897d497ab4d8bc9faf243c859d14d5d6b66/240' \
--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY'
```
**Successful Response:**
```
{
    "info": {
        "addr": "0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
        "amount": "0.295503",
        "crypto": "ETH"
    },
    "status": "success"
}
```
**Not Found Response:**
```
{
    "info": {},
    "status": "success"
}
```
<a name="wallet-encryption-enter-decryption_key-via-api"></a>
#### 5.2.8. Wallet encryption (Enter decryption_key via API)
**Endpoint:** `/api/v1/decryption-key`  
**Authorization:** ApiKey.   
**HTTP request method:**  POST request with a formdata body in the following format:  
```
key=<decryption_key>
```
**Curl Example:**
```
curl --location --request POST 'https://demo.shkeeper.io/api/v1/decryption-key' \
--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY' \
--form 'key="asdfasfasgasgasgasgdeagweg"'
```
**Successful Decrypt Response:**
```
{
    "status": "success"
}
```
**Successful Response (Decryption is not needed):**
```
{
    "message": "Decryption key was already entered",
    "status": "success"
}
```
**Error Responses:**
```
{
    "message": "Decryption key is required",
    "status": "error"
}
{
    "message": "Invalid decryption key",
    "status": "error"
}
{
    "message": "Wallet is not encrypted",
    "status": "error"
}
```
<a name="retrieving-metrics"></a>
#### 5.2.9. Retrieving Metrics

**Endpoint:** `/metrics`  
**Authorization:** HTTP Basic Auth using metric credentials. Metric credentials can be set by environment variables: `METRICS_USERNAME, METRICS_PASSWORD`. The default username/password is `shkeeper/shkeeper`.   
**HTTP request method:**  GET  
**Example Curl Request:**  
```
curl --location --request GET 'https://demo.shkeeper.io/metrics' \
--header 'Authorization: Basic c2hrZWVwZXI6c2hrZWVwZXI='
```
**Successful Response:**
```
# HELP geth_last_release_info Version of the latest release from https://github.com/ethereum/go-ethereum/releases
# TYPE geth_last_release_info gauge
geth_last_release_info{name="Bothros (v1.14.5)",published_at="2024-06-06T13:41:53Z",tag_name="v1.14.5",version="1.14.5"} 1.0
# HELP prysm_last_release_info Version of the latest release from https://github.com/prysmaticlabs/prysm/releases
# TYPE prysm_last_release_info gauge
prysm_last_release_info{name="v5.0.4",published_at="2024-06-21T16:13:40Z",tag_name="v5.0.4",version="5.0.4"} 1.0
# HELP geth_fullnode_version_info Current geth version in use
# TYPE geth_fullnode_version_info gauge
geth_fullnode_version_info{version="1.14.6"} 1.0
# HELP prysm_fullnode_version_info Current prysm version in use
# TYPE prysm_fullnode_version_info gauge
prysm_fullnode_version_info 1.0
# HELP ethereum_fullnode_status Connection status to ethereum fullnode
# TYPE ethereum_fullnode_status gauge
ethereum_fullnode_status 1.0
# HELP ethereum_fullnode_last_block the Last block loaded to the fullnode
# TYPE ethereum_fullnode_last_block gauge
ethereum_fullnode_last_block 6.415394e+06
# HELP ethereum_wallet_last_block Last checked block
# TYPE ethereum_wallet_last_block gauge
ethereum_wallet_last_block 6.415392e+06
# HELP ethereum_fullnode_last_block_timestamp Last block timestamp loaded to the fullnode
# TYPE ethereum_fullnode_last_block_timestamp gauge
ethereum_fullnode_last_block_timestamp 1.722503064e+09
# HELP ethereum_wallet_last_block_timestamp Last checked block timestamp
# TYPE ethereum_wallet_last_block_timestamp gauge
ethereum_wallet_last_block_timestamp 1.72250304e+09
```
<a name="payout"></a>
#### 5.2.10. Payout

SHKeeper allows you to make payouts through the API. The API calls related to payouts are somewhat different from those described earlier, as they use HTTP Basic Auth for authentication and authorization, utilizing your SHKeeper login and password.

**Payouts Flow**
- Creating a payout task (Payout or Multipayout)
- Checking the task result

There are two methods for creating a payout: **Payout** and **Multipayout**, with some differences between them. Currently, Multipayout is not supported for the following cryptocurrencies: XMR, BTC, LTC, and DOGE. For these, you need to use the Payout method.

**Check the Task Results** After you submit the payout task, you should poll for the task status:
- **PENDING** means the task is in progress, and no result is available at this point yet.
- **SUCCESS** means the task is complete, and you are presented with the results.

The task results are an array of objects, each containing the original payout request, the transaction status (success or error), and a list of transaction IDs related to the payout. If the transfer status happens to be an error, there will be a text description of the error in the `message` field.
<a name="payout-related-endpoints"></a>
#### 5.2.11. Payout Related Endpoints
<a name="creating-a-payout-task"></a>
##### 5.2.11.1. Creating a Payout Task

**Endpoint:** `/api/v1/<crypto_name>/payout`  
**Authorization:** HTTP Basic Auth.   
**HTTP request method:**  POST request with a JSON object in the following format:  
```
{
  "amount": <amount_to_send>,
  "destination": "<addr>",
  "fee": "<transaction_fee>"
}
```
- `amount`: The amount to be sent.
- `destination`: The address to which the amount should be sent.
  - For XRP, the address must be provided in the X-address format. The X-address format replaces the use of a separate destination tag when sending funds to a multi-user wallet on the XRP ledger, such as those of exchanges and custodial services.
- `fee`: The transaction fee.
  - This must always be specified, even for cryptocurrencies with automatically determined fees.
  - For BTC, it is specified in sat/vByte; for LTC and DOGE, it is in sat/Byte.
  - For XMR, an integer (1-4) is passed to set the transaction priority:
    - 1 - Unimportant
    - 2 - Normal
    - 3 - Elevated
    - 4 - Priority
  - For other cryptocurrencies, any value can be passed; the optimal fee is calculated and set automatically, and this field is ignored.

Since the payout task is an asynchronous process, the call will always complete successfully (except in cases where required parameters are missing or Basic authentication fails), returning a `task_id` which is used to check the status of the task later.

**Curl Example:**
```
curl --location --request POST 'https://demo.shkeeper.io/api/v1/ETH-USDC/payout' \
--header 'Authorization: Basic  nApijGv8djih7ozY' \
--header 'Content-Type: application/json' \
--data-raw '{"amount":107,"destination":"0xBD26e3512ce84F315e90E3FE75907bfbB5bD0c44","fee":"10"}'
```
**Successful Response:**
```
{"task_id":"b2a01bb0-8abe-403b-a3fa-8124c84bcf23"}
```
<a name="creating-a-multipayout-task"></a>
##### 5.2.11.2. Creating a Multipayout Task

**Endpoint:** `/api/v1/<crypto_name>/multipayout`  
**Authorization:** HTTP Basic Auth.   
**HTTP request method:**  POST request with a JSON object in the following format:  
```
{
  "amount": <amount_to_send>,
  "dest": "<addr>"
}
```
For sending XRP, you can optionally pass a `dest_tag`. If provided, the address should be given in the regular format, and SHKeeper will automatically convert it to X-address format. Alternatively, you can manually convert the XRP address to X-address format and pass it in the `dest` field; in this case, `dest_tag` does not need to be provided.

**Curl Example:**
```
curl --location --request POST 'https://demo.shkeeper.io/api/v1/ETH-USDT/multipayout' \
--header 'Authorization: Basic  nApijGv8djih7ozY' \
--header 'Content-Type: application/json' \
--data-raw '[{"dest":"0xE77895BAda700d663f033510f73f1E988CF55756","amount":"100"},{"dest":"0x7C4C7D3010d31329dd8244617C46e460E5EF8a6F","amount":"200.11"}]'
```
**Successful Response:**
```
{
    "task_id": "0471adec-5de5-4668-bc1d-e8e7729cb676"
}
```
**Error Response:**
```
{
    "msg": "Bad destination address in {'dest': 'wrong_address', 'amount': '100'}",
    "status": "error"
}
```
<a name="checking-task-status"></a>
##### 5.2.11.3. Checking Task Status

**Endpoint:** `/api/v1/<crypto_name>/task/<task_id>`  
**Authorization:** HTTP Basic Auth.  
**HTTP request method:**  GET  
**Curl Example:**  
```
curl --location --request GET 'https://demo.shkeeper.io/api/v1/ETH-USDC/task/7028c45b-0c88-483e-b703-dd455a361b2e' \
--header 'Authorization: Basic  nApijGv8djih7ozY' \
--header 'Content-Type: application/json'
```
**Successful Response:**
```
When the task is in progress:
{
  "result": null,
  "status": "PENDING"
}
```
**When the task is complete:**
```
{
  "result": [
    {
      "amount": "100",
      "dest": "TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ",
      "status": "success",
      "txids": [
        "4c32969220743644e3480d96e95a423d351049ac6296b8315103225709881ae3",
        "da2996bae7a8a4d655a1288f8f4c79ce0aa3640e61f8ae8de08ae9c70c72d90d"
      ]
    },
    {
      "amount": "200.11",
      "dest": "TYtD9md7cHuB4P6kDd362jhcUGP7cJybF7",
      "status": "success",
      "txids": [
        "e155f80221bf73a127ec8a9a5d1b6989edd38e7583e7747f128152833ff49090",
        "0f999d988641395b38943d8a9c01581c19fcaa4dcdd4bb35f99e16510fdd10d6",
        "8cbfe9131d406a1bcfca403f4318b9592e7c08c04ea9b20629f430762d4eb7a4",
        "0036fbeadcb8cec278754f9fb7b18a3e9b57c71eb743115a8338d72b552a3dd4",
        "d8972ac9c964adbc25486d2cfdf2de7b61c3f0ca7510aa7cddc832a9bccdf551"
      ]
    }
  ],
  "status": "SUCCESS"
}
```
**Failure Response:**
```
{
    "result": "Have not enough tokens on fee account, need 107 have 0",
    "status": "FAILURE"
}
```

<a name="get-crypto-balance-info"></a>
##### 5.2.11.4. Get crypto balance information

**Endpoint:** `/api/v1/<crypto_name>/balance`  
**Authorization:** ApiKey.    
**HTTP request method:**  GET  
**Curl Example:**
```
curl --location --request GET 'https://demo.shkeeper.io/api/v1/ETH/balance' \
--header 'X-Shkeeper-Api-Key: nApijGv8djih7ozY'
```

**Successful Response:**
```
{
  "amount_crypto":"0.0213590094",
  "amount_fiat":"88.8201590493",
  "display_name":"Ethereum",
  "fiat":"USD",
  "name":"ETH",
  "rate":"4158.44000000",
  "server_status":"Synced"
}
```

**Error Response:**
```
{
  "message":"Crypto XRP is not enabled",
  "status":"error"
}
```

<a name="receiving-callback"></a>
### 5.3 Receiving callback

The callback is sent to the specified `callback_url` provided during the invoice creation process. Typically, this is a script that receives the notification from SHKeeper, validates and processes it.

Once SHKeeper receives a payment, it will send a payment notification to the `<callback_url>` using a POST request with a JSON-encoded body and the `X-Shkeeper-Api-Key` HTTP header to authenticate with your system.

If a payment notification is successfully processed by your server, it should return the HTTP code `202 Accepted`. Any other response or connection failure will cause SHKeeper to resend the payment notification every 60 seconds.

SHKeeper will send a notification for each transaction related to the invoice, even if the invoice is already in the PAID/OVERPAID status. The transaction that triggered the callback is marked with the `trigger` field.

**Structure of the Callback Object:**
```
{
  "external_id": "1",  // Invoice or Order ID in the external system
  "crypto": "BTC",  // cryptocurrency (provided during payment request creation)
  "addr": "AAAAAAAAAAAAAA", // wallet address that receives payments
  "fiat":   "USD",  // fiat currency (provided during payment request creation)
  "balance_fiat":      "100",  // amount in fiat currency
  "balance_crypto": "0.0025",  // amount in cryptocurrency
  "paid": true,  // true if the payment request is fully paid
                      // false if only a partial payment is received
  "status": "PAID",  // PARTIAL - partial invoice payment
                              // PAID - full invoice payment
                              // OVERPAID - overpaid invoice payment
  "transactions": [  // list of transactions related to the payment request
    {
      "txid": "ZZZZZZZZZZZZZZZZZZZ",  // blockchain transaction ID
      "date": "2022-04-01 11:22:33",  // transaction date
      "amount_crypto": "0.0025",      // transaction amount in cryptocurrency
      "amount_fiat": "50",           // transaction amount in fiat currency
      "trigger": false,  // true if this transaction was the trigger for the payment notification
      "crypto": "ETH-USDT" // transaction cryptocurrency
    },
    {
      "txid": "CCCCCCCCCCCC",  // blockchain transaction ID
      "date": "2022-04-01 11:42:33",  // transaction date
      "amount_crypto": "0.0025",      // transaction amount in cryptocurrency
      "amount_fiat": "50",           // transaction amount in fiat currency
      "trigger": true,  // true if this transaction was the trigger for the payment notification
      "crypto": "ETH-USDT" // transaction cryptocurrency
    }
  ],
 "fee_percent": "2", // fee percentage added to the invoice amount
 "overpaid_fiat": "0.00" // In case of overpayment, the overpaid amount will be shown here
}
```
**Callback Example:**
```
{
  "external_id": "147",
  "crypto": "ETH-USDT",
  "addr": "0x6f2Fc9D7205B7D9037dDE45B5f9e12B18EA07e27",
  "fiat": "USD",
  "balance_fiat": "7.80",
  "balance_crypto": "7.80000000",
  "paid": true,
  "status": "PAID",
  "transactions": [
    {
      "txid": "0x518a10b13a708fd11aa98db88c625dd45130db6656ba822600b01d0c53c85078",
      "date": "2024-06-25 15:45:38",
      "amount_crypto": "7.80000000",
      "amount_fiat": "7.80",
      "trigger": true,
      "crypto": "ETH-USDT"
    }
  ],
  "fee_percent": "2",
  "overpaid_fiat": "0.00"
}
```
<a name="ready-made-modules"></a>
### 5.4. Ready-made modules
<a name="whmcs"></a>
#### 5.4.1. WHMCS

Shkeeper payment gateway module for WHMCS

Module has been tested on WHMCS Version: 8.10.1

Find module for WHMCS here: https://github.com/vsys-host/whmcs-shkeeper-gateway-module

<a name="woocommerce-wordpress"></a>
#### 5.4.2. WooCommerce WordPress

Shkeeper payment gateway plugin for CMS WordPress + WooCommerce

Plugin has been tested on CMS WordPress 5.9.3 + WooCommerce 6.3.1

Find module for WooCommerce / WordPress here: https://github.com/vsys-host/wp-shkeeper-plugin

<a name="opencart-3"></a>
#### 5.4.3. Opencart 3

SHKeeper payment gateway module for OpenCart 3

The module has been tested on CMS OpenCart Version 3.0.3.9

Find the module for Opencart 3 here: https://github.com/vsys-host/opencart-3-shkeeper-payment-module 

<a name="prestashop-8"></a>
#### 5.4.4. Prestashop 8

SHKeeper payment gateway module for Prestashop 8

The module has been tested on CMS Prestashop Version  8.1.7

Find the module for Prestashop 8 here: https://github.com/vsys-host/prestashop-8-shkeeper-payment-module

<a name="be-involved"></a>
## 6. Be involved

![image](https://github.com/user-attachments/assets/2749c1b4-ed8f-4dd1-b186-903e3d4c7c84)

SHKeeper features open-source code available from GitHub, which also means an excellent opportunity to be involved in the community. You can contribute to us, and if you do, we will appreciate it very much. After the validation, review, and test, we will publish your data. Should you consider this opportunity, please get in touch here.

<a name="contact-us"></a>
## 7. Contact us

![image](https://github.com/user-attachments/assets/2d75394d-5efe-48ac-98c0-8692253ad0ad)

If you have experienced any problems using SHKeeper, you can contact the community listed on the [official website](https://shkeeper.io/). However, please ask questions on [Github Issues](https://github.com/vsys-host/shkeeper.io/issues) related to technical issues only. Thank you.




### CREATED BY

![VSYS logo](https://github.com/user-attachments/assets/719e1f58-a6b4-455d-b4e6-531a777c52f0)




### JOIN OUR COMMUNITY

[![Group 1790](https://github.com/user-attachments/assets/9829e615-2f22-4340-8d5d-eb5c156fcbcf)](https://www.reddit.com/user/shkeeper_io/)
[![Group 1795](https://github.com/user-attachments/assets/24ee0fac-9f4d-4274-a482-18663f8a8f3f)](https://medium.com/@shkeeper.io)
[![Group 1794](https://github.com/user-attachments/assets/e6803fff-7738-4148-a4d4-ed7d40faeeda)](https://x.com/shkeeper_io)
[![Group 1793](https://github.com/user-attachments/assets/bba26cfd-fcdf-44ac-8046-6a03e06648b3)](https://www.facebook.com/shkeeper.io)
[![Group 1792](https://github.com/user-attachments/assets/62be0ba8-6658-4822-a3f5-de445299eb32)](https://www.linkedin.com/company/86576569/admin/feed/posts/)
[![Group 1791](https://github.com/user-attachments/assets/dc12acee-6d70-489e-a351-750ca4d92e06)](https://www.youtube.com/channel/UCfJp6tIaiJ2bchDyF-LFnaw)


Stay informed with the latest SHKeeper news, updates, and technical announcements. Follow our Telegram to never miss important changes and improvements:
https://t.me/shkeeper_updates


