# Multipayout API (USDT only)

This API allows to create a payout task which can transfer USDT to multiple accounts at once.

The workflow with this API consist of 2 steps:
 - creating a payout task
 - checking for the task result

## Auth

Both endpoints requires HTTP Basic Auth using your Shkeeper's login and password.

## Create a multipayout task

To create a multipayout task you should make a POST request with list of JSON objects, each describing a recipient as TRON account address and amount of USDT tokens to transfer to the recipient. Both values should be strings.

### REQUEST

POST `/api/v1/USDT/multipayout`

```json
[
    { "dest": "<addr 1>", "amount": "100" },
    { "dest": "<addr 2>", "amount": "9.99" },
    { "dest": "<addr 3>", "amount": "1500" }
]
```

### RESPONSE

On success:

```json
{
    "status": "success",
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

On error:

```json
{
    "status": "error",
    "message": "error description"
}
```

## Check the task results

After you submitted the payout task you should poll for the task status:
 - `PENDING` means the task in in progress and no result available at this point yet
 - `SUCCESS` means the task is complete and you presented with the results

The task results is an array of objects, each having the original payout request, the transaction status (`success` or `error`) and a list of transaction IDs related to the payout.

If the transfer status happen to be an `error`, there will be a text description of the error in `message` field.

### REQUEST

GET `/api/v1/USDT/task/<task_id>`

### RESPONSE

When the task is in progress:

```json
{
  "result": null,
  "status": "PENDING"
}
```

When the task is complete:

```json
{
  "result": [
    { "dest": "<addr 1>", "amount":  "100", "status": "error", "message": "some error description" },
    { "dest": "<addr 2>", "amount": "9.99", "status": "success", "txids": ["cccc"] },
    { "dest": "<addr 3>", "amount": "1500", "status": "success", "txids": ["dddd", "eeee", "ffff", "gggg"] }
  ],
  "status": "SUCCESS"
}
```

## Curl example

### Create a payout task

```
$ curl -d '[{"dest":"TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ","amount":"100"},{"dest":"TYtD9md7cHuB4P6kDd362jhcUGP7cJybF7","amount":"200.11"}]' localhost:5000/api/v1/USDT/multipayout -u admin:admin
```

```json
{
  "task_id": "73af20e8-c8f4-49dd-a574-d6234fde3ad0"
}
```

### Check the task results

```
$ curl -u admin:admin localhost:5000/api/v1/USDT/task/73af20e8-c8f4-49dd-a574-d6234fde3ad0
```

```json
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