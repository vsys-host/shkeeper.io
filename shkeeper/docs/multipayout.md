# Multipayout API (USDT only) - work in progress

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
curl -d '[{"dest":"<addr1>","amount":"100"},{"dest":"<addr2>","amount":"9.99"},{"dest":"<addr3>","amount":"1500"}]' \
     -u "<shkeeper login>:<shkeeper password>" \
     http://<shkeeper_url>/api/v1/USDT/multipayout
```

### Check the task results

```
curl -u "<shkeeper login>:<shkeeper password>" \
     http://<shkeeper_url>/api/v1/USDT/task/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```