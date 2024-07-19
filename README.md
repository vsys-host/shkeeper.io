# SHKeeper.io<!-- omit in toc -->

![SHKeeper logo](https://github.com/user-attachments/assets/dd573f14-1b8e-47d7-86e5-59f24b67b027)               

- [About SHKeeper](#about-shkeeper)
 - [Demo](#demo)
 - [Helpful links](#helpful-links)
- [Available coins](#available-coins)
- [Features](#features)
- [Installation](#installation)
- [API for plugins](#api-for-plugins)
  - [Auth](#auth)
  - [List available cryptos with GET `/api/v1/crypto`](#list-available-cryptos-with-get-apiv1crypto)
  - [Create a payment request with POST `/api/v1/<crypto>/payment_request`](#create-a-payment-request-with-post-apiv1cryptopayment_request)
  - [Payment notifications format](#payment-notifications-format)
  - [Wallet encryption](#wallet-encryption)
- [Ready-made modules](#ready-made-modules)
  - [WHMCS](#whmcs)
  - [WooCommerce WordPress](#woocommerce-wordpress)
  - [Opencart 3](#opencart-3)
- [Be involved](#be-involved)
- [Contact us](#contact-us)



## About SHKeeper

SHKeeper - is an open-source, self-hosted cryptocurrency payment processor. It uniquely serves as both a gateway and a merchant, enabling you to accept payments in various cryptocurrencies without fees and intermediaries.


### Demo

SHKeeper demo version available from us, so you can try it yourself without installing it:

http://demo.shkeeper.io:5000/

Login: admin 

Password: admin  


### Helpful links

Details of the latest version can be found on the

Tutorial video: https://www.youtube.com/watch?v=yYK_JAm1_hg

Find knowledge base here: https://shkeeper.io/kb/launch/what-is-shkeeper

Latest announcements: https://shkeeper.io/news


## Available coins
SHKeeper offers a direct way to receive BTC, ETH, LTC, DOGE, XMR, XRP, TRX, BNB, MATIC, AVAX, USDT (ERC20, TRC20, BEP-20, Polygon, Avalanche), USDC (ERC20, TRC20, BEP-20, Polygon, Avalanche).

![Coins](https://github.com/user-attachments/assets/b4137f13-0018-40b1-8c25-d639235b7fc2)

## Features

1. Multi-currency
2. No transaction fees
3. No third parties
4. Direct crypto payments
5. Ability to set your exchange rates, commissions, or fees
6. Crediting the overpayment to the balance
7. Partial payments
8. Setting auto-payments into a cold wallet
9. Increased privacy and security
10. No KYC or AML
11. Non-custodial
12. Multipayout
13. SegWit Support
14. Easily embed payment buttons / QR-code
15. Full internal wallet with hardware wallet integration

![image](https://github.com/user-attachments/assets/e7c637af-8da6-455b-80f5-9b054cfff03b)


## Installation

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

Login to Shkeeper: http://<ip>:5000/


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

After a few minutes your Shkeeper should be reachable on https://<your domain> and have a valid SSL.


## API for plugins

### Auth

To authenticate to shkeeper.io use `X-Shkeeper-Api-Key` HTTP header in a request:

```
X-Shkeeper-Api-Key: <api key>
```

Curl example:

```
curl -H "X-Shkeeper-Api-Key: wvoNQaHswSBk9rZu" https://<shkeeper.io_url>/api/v1/crypto
```

### List available cryptos with GET `/api/v1/crypto`

Request example:

```
curl -H "X-Shkeeper-Api-Key: wvoNQaHswSBk9rZu" https://<shkeeper.io_url>/api/v1/crypto
```

Response:

```jsonc
{
  "status": "success",
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
     -H "X-Shkeeper-Api-Key: wvoNQaHswSBk9rZu" \
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

Once shkeeper.io receives a payment it will send a payment notification to the `<callback_url>` using POST with json-encoded body and `X-Shkeeper-Api-Key` HTTP header to authenticate to your system:

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

### Wallet encryption

#### Enter decryption key

```
curl -d 'key=<decryption_key>' \
     -H "X-Shkeeper-Api-Key: wvoNQaHswSBk9rZu" \
     https://<shkeeper.io_url>/api/v1/decryption-key
```

Response (on success):

```jsonc
{
  "status": "success"
}
```

Response (on error):

```jsonc
{
    "status":"error",
    "message":"error description"
}
```

## Ready-made modules

### WHMCS

Shkeeper payment gateway module for WHMCS

Module has been tested on WHMCS Version: 8.10.1

Find module for WHMCS here: https://github.com/vsys-host/whmcs-shkeeper-gateway-module


### WooCommerce / WordPress

Shkeeper payment gateway plugin for CMS WordPress + WooCommerce

Plugin has been tested on CMS WordPress 5.9.3 + WooCommerce 6.3.1

Find module for WooCommerce / WordPress here: https://github.com/vsys-host/wp-shkeeper-plugin


### Opencart 3

SHKeeper payment gateway module for OpenCart 3

Module has been tested on CMS OpenCart Version 3.0.3.9

Find module for Opencart 3 here: https://github.com/vsys-host/opencart-3-shkeeper-payment-module 


## Be involved

![image](https://github.com/user-attachments/assets/2749c1b4-ed8f-4dd1-b186-903e3d4c7c84)

SHKeeper features open-source code available from GitHub, which also means an excellent opportunity to be involved in the community. You can contribute to us, and if you do, we will appreciate it very much. After the validation, review, and test, we will publish your data. Should you consider this opportunity, please get in touch here.


## Contact us

![image](https://github.com/user-attachments/assets/2d75394d-5efe-48ac-98c0-8692253ad0ad)

If you have experienced any problems using SHKeeper, you can contact the community listed on the [official website](https://shkeeper.io/). However, please ask questions on [Github Issues](https://github.com/vsys-host/shkeeper.io/issues) related to technical issues only. Thank you.




### CREATED BY

![VSYS logo](https://github.com/user-attachments/assets/eb563832-7965-4276-80fa-1e8b31374917)


### JOIN OUR COMMUNITY

[![Group 1790](https://github.com/user-attachments/assets/9829e615-2f22-4340-8d5d-eb5c156fcbcf)](https://www.reddit.com/user/shkeeper_io/)
[![Group 1795](https://github.com/user-attachments/assets/24ee0fac-9f4d-4274-a482-18663f8a8f3f)](https://medium.com/@shkeeper.io)
[![Group 1794](https://github.com/user-attachments/assets/e6803fff-7738-4148-a4d4-ed7d40faeeda)](https://x.com/shkeeper_io)
[![Group 1793](https://github.com/user-attachments/assets/bba26cfd-fcdf-44ac-8046-6a03e06648b3)](https://www.facebook.com/shkeeper.io)
[![Group 1792](https://github.com/user-attachments/assets/62be0ba8-6658-4822-a3f5-de445299eb32)](https://www.linkedin.com/company/86576569/admin/feed/posts/)
[![Group 1791](https://github.com/user-attachments/assets/dc12acee-6d70-489e-a351-750ca4d92e06)](https://www.youtube.com/channel/UCfJp6tIaiJ2bchDyF-LFnaw)




