from marshmallow import Schema, fields


class ErrorSchema(Schema):
    status = fields.String(example="error", description="Request status")
    message = fields.String(description="Error message")
    traceback = fields.String(load_default=None)


class SuccessSchema(Schema):
    status = fields.String(example="success", description="Request status")


class CryptoItemSchema(Schema):
    name = fields.String(
        description="Crypto identifier used in API endpoints", example="ETH"
    )
    display_name = fields.String(
        description="Human-readable crypto name", example="Ethereum"
    )


class GetCryptoResponseSchema(Schema):
    status = fields.String(description="Response status", example="success")
    crypto = fields.List(
        fields.String(),
        description="Legacy list of crypto identifiers (backward compatibility)",
        example=["BNB", "BTC", "ETH"],
    )
    crypto_list = fields.List(
        fields.Nested(CryptoItemSchema),
        description="Preferred list of available cryptocurrencies",
    )


class PayoutCallbackTransactionSchema(Schema):
    payout_id = fields.Integer(description="Internal payout ID", example=14)
    external_id = fields.String(
        description="External ID assigned to the payout", example="435345534"
    )
    tx_hash = fields.String(
        description="Blockchain transaction hash",
        example="AF732D1D1254C97A77F4DD08553725E6ECC011CA6DCD12BC65FA1D8551E54E6D",
    )
    status = fields.String(
        description="Payout status: SUCCESS, FAILURE, or IN_PROGRESS", example="SUCCESS"
    )
    amount = fields.String(
        description="Amount in cryptocurrency", example="2.0000000000"
    )
    crypto = fields.String(description="Cryptocurrency code", example="XRP")
    amount_fiat = fields.String(
        description="Amount in fiat currency", example="4.364200000000000000"
    )
    currency_fiat = fields.String(description="Fiat currency code", example="USD")
    timestamp = fields.String(
        description="Timestamp of payout", example="2024-11-27T13:49:22"
    )


class TransactionCallbackSchema(Schema):
    txid = fields.String(
        description="Blockchain transaction ID",
        example="0x518a10b13a708fd11aa98db88c625dd45130db6656ba822600b01d0c53c85078",
    )
    date = fields.String(description="Transaction date", example="2024-06-25 15:45:38")
    amount_crypto = fields.String(
        description="Transaction amount in crypto", example="7.80000000"
    )
    amount_fiat = fields.String(
        description="Transaction amount in fiat", example="7.80"
    )
    trigger = fields.Boolean(
        description="True if this transaction triggered the callback", example=True
    )
    crypto = fields.String(description="Transaction cryptocurrency", example="ETH-USDT")


class PaymentCallbackSchema(Schema):
    external_id = fields.String(
        description="Invoice or order ID in external system", example="147"
    )
    crypto = fields.String(description="Cryptocurrency used", example="ETH-USDT")
    addr = fields.String(
        description="Wallet address that received the payment",
        example="0x6f2Fc9D7205B7D9037dDE45B5f9e12B18EA07e27",
    )
    fiat = fields.String(description="Fiat currency used", example="USD")
    balance_fiat = fields.String(description="Amount in fiat", example="7.80")
    balance_crypto = fields.String(description="Amount in crypto", example="7.80000000")
    paid = fields.Boolean(description="True if fully paid", example=True)
    status = fields.String(
        description="Invoice status: PARTIAL, PAID, OVERPAID", example="PAID"
    )
    transactions = fields.List(
        fields.Nested(TransactionCallbackSchema),
        description="Transactions related to the payment request",
    )
    fee_percent = fields.String(
        description="Fee percentage added to invoice", example="2"
    )
    overpaid_fiat = fields.String(description="Overpaid amount in fiat", example="0.00")


class PayoutCallbackSchema(Schema):
    """Callback sent after payout completion."""

    payouts = fields.List(
        fields.Nested(PayoutCallbackTransactionSchema),
        required=True,
        description="List of completed payouts",
    )


class PaymentRequestSchema(Schema):
    external_id = fields.String(
        required=False,
        example="order_123456",
        description="External order ID in merchant system",
    )
    fiat = fields.String(
        required=True, example="USD", description="Fiat currency code (ISO 4217)"
    )
    amount = fields.String(
        required=True,
        example="100.00",
        description="Order amount in fiat currency as string",
    )
    callback_url = fields.Url(
        required=False,
        example="https://example.com/payment/callback",
        description="URL that will receive payment status callbacks",
    )


class PaymentResponseSchema(Schema):
    status = fields.String(example="success", description="Payment processing status")
    amount = fields.String(
        example="0.01080125",
        description="Payment amount as a string to preserve precision",
    )
    exchange_rate = fields.String(
        example="3379.24", description="Exchange rate at the time of payment"
    )
    display_name = fields.String(
        example="Ethereum", description="Human-readable cryptocurrency name"
    )
    wallet = fields.String(
        example="0x8695f1a224e28adf362E6f8a8E695EDCc5D64960",
        description="Destination wallet address",
    )
    recalculate_after = fields.Integer(
        example=0,
        description="Seconds after which the exchange rate should be recalculated",
    )


class MetricsItemSchema(Schema):
    name = fields.String(
        description="Metric name", example="ethereum_fullnode_last_block"
    )
    value = fields.Float(description="Metric value", example=6415394)
    labels = fields.Dict(
        keys=fields.String(),
        values=fields.String(),
        description="Optional labels for the metric",
        example={"version": "1.14.6"},
    )


class MetricsResponseSchema(Schema):
    metrics = fields.List(
        fields.Nested(MetricsItemSchema),
        description="List of system and crypto metrics",
    )


class ErrorPaymentResponseSchema(Schema):
    status = fields.String(example="error", description="Error status")
    message = fields.String(
        example="BTC payment gateway is unavailable",
        description="Human-readable error message",
    )


class BalanceItemSchema(Schema):
    name = fields.String(description="Crypto symbol", example="BTC")
    display_name = fields.String(
        description="Human-readable crypto name", example="Bitcoin"
    )
    amount_crypto = fields.String(description="Amount in crypto", example="0.12345678")
    rate = fields.String(
        description="Current exchange rate to fiat", example="70616.07"
    )
    fiat = fields.String(description="Fiat currency", example="USD")
    amount_fiat = fields.String(
        description="Amount in fiat currency", example="8700.12"
    )
    server_status = fields.String(
        description="Backend node/server status", example="online"
    )


class BalancesResponseSchema(Schema):
    status = fields.String(description="Response status", example="success")
    balances = fields.List(
        fields.Nested(BalanceItemSchema), description="List of balances"
    )


class BalancesErrorSchema(Schema):
    status = fields.String(description="Response status", example="error")
    message = fields.String(
        description="Error message", example="No valid cryptos requested"
    )


class QuoteRequestSchema(Schema):
    fiat = fields.String(required=True, example="USD")
    amount = fields.String(required=True, example="10.00")


class QuoteResponseSchema(Schema):
    status = fields.String(example="success")
    crypto_amount = fields.String()
    exchange_rate = fields.String()


class BalanceResponseSchema(Schema):
    name = fields.String(description="Crypto symbol", example="ETH")
    display_name = fields.String(
        description="Human-readable crypto name", example="Ethereum"
    )
    amount_crypto = fields.String(
        description="Balance in crypto units", example="0.0213590094"
    )
    rate = fields.String(
        description="Current exchange rate to fiat", example="4158.44000000"
    )
    fiat = fields.String(description="Fiat currency", example="USD")
    amount_fiat = fields.String(
        description="Balance converted to fiat", example="88.8201590493"
    )
    server_status = fields.String(
        description="Current status of crypto server", example="Synced"
    )


class PayoutRequestSchema(Schema):
    amount = fields.String(
        required=True, description="The amount to send", example="107"
    )
    destination = fields.String(
        required=True,
        description="Destination address",
        example="0xBD26e3512ce84F315e90E3FE75907bfbB5bD0c44",
    )
    fee = fields.String(
        required=True,
        description="Transaction fee (sat/vByte for BTC, sat/Byte for LTC/DOGE, integer for XMR, ignored for others)",
        example="10",
    )
    callback_url = fields.String(
        required=False,
        description="Optional callback URL to receive payout notifications",
        example="https://my.payout.com/notification",
    )
    external_id = fields.String(
        required=False, description="Optional external order ID", example="435345534"
    )


class PayoutResponseSchema(Schema):
    task_id = fields.String(
        description="ID of the payout task",
        example="b2a01bb0-8abe-403b-a3fa-8124c84bcf23",
    )
    external_id = fields.String(
        description="Echoed external ID if provided", example="435345534"
    )


class TaskResultItemSchema(Schema):
    dest = fields.String(
        description="Destination address", example="TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ"
    )
    amount = fields.String(description="Amount sent", example="100")
    status = fields.String(description="Status of payout item", example="success")
    txids = fields.List(
        fields.String(),
        description="Transaction IDs associated with this payout",
        example=[
            "4c32969220743644e3480d96e95a423d351049ac6296b8315103225709881ae3",
            "da2996bae7a8a4d655a1288f8f4c79ce0aa3640e61f8ae8de08ae9c70c72d90d",
        ],
    )


class TaskResponseSchema(Schema):
    result = fields.List(
        fields.Nested(TaskResultItemSchema),
        allow_none=True,
        description="Task results or null if pending",
    )
    status = fields.String(
        required=True, description="Task status", example="PENDING / SUCCESS / FAILURE"
    )


class MultipayoutItemSchema(Schema):
    dest = fields.String(
        required=True,
        description="Destination address",
        example="0xE77895BAda700d663f033510f73f1E988CF55756",
    )
    amount = fields.String(
        required=True,
        description="Amount to send",
        example="100.0",
    )
    external_id = fields.String(
        required=False,
        description="Optional external ID",
        example="43234",
    )
    callback_url = fields.String(
        required=False,
        description="Optional callback URL",
        example="https://my.payout.com/notification",
    )
    dest_tag = fields.Integer(
        required=False,
        description="Optional XRP destination tag",
        example=12345,
    )


class MultipayoutResponseSchema(Schema):
    task_id = fields.String(example="0471adec-5de5-4668-bc1d-e8e7729cb676")
    external_ids = fields.List(fields.String(), example=["43234", "43235"])


class ListAddressesResponseSchema(Schema):
    status = fields.String(description="Response status", example="success")
    addresses = fields.List(
        fields.String(),
        description="List of wallet addresses for the given crypto",
        example=[
            "0x0A71f4741DcaD3C06AA51eE6cF0E22675507d0d0",
            "0x8695f1a224e28adf362E6f8a8E695EDCc5D64960",
        ],
    )


class InvoiceTransactionSchema(Schema):
    txid = fields.String(description="Transaction ID")
    amount = fields.String(description="Transaction amount in crypto")
    crypto = fields.String(description="Crypto currency symbol")
    addr = fields.String(description="Crypto address")
    status = fields.String(description="Transaction status")


class InvoiceSchema(Schema):
    external_id = fields.String(description="External invoice ID")
    fiat = fields.String(description="Fiat currency code, e.g., USD")
    amount_fiat = fields.String(description="Amount in fiat")
    balance_fiat = fields.String(description="Balance in fiat")
    status = fields.String(description="Invoice status, e.g., UNPAID")
    txs = fields.List(
        fields.Nested(InvoiceTransactionSchema),
        description="Transactions linked to this invoice",
    )


class InvoicesListResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    invoices = fields.List(
        fields.Nested(InvoiceSchema), required=True, description="List of invoices"
    )


class TxInfoSchema(Schema):
    addr = fields.String(
        required=True,
        description="Transaction address",
        example="0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
    )
    amount = fields.String(
        required=True,
        description="Transaction amount",
        example="0.295503",
    )
    crypto = fields.String(
        required=True,
        description="Cryptocurrency code",
        example="ETH",
    )


class TxInfoResponseSchema(Schema):
    status = fields.String(
        example="success",
    )
    info = fields.Nested(
        TxInfoSchema,
        description="Transaction info. Empty object if transaction not found.",
        example={
            "addr": "0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
            "amount": "0.295503",
            "crypto": "ETH",
        },
    )


class TransactionSchema(Schema):
    addr = fields.String(
        description="Cryptocurrency address",
        example="0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
    )
    amount = fields.String(description="Transaction amount", example="0.0001000000")
    crypto = fields.String(description="Cryptocurrency symbol", example="ETH")
    status = fields.String(description="Transaction status", example="CONFIRMED")
    txid = fields.String(
        description="Transaction ID",
        example="0xbcf68720db79454f40b2acf6bfb18897d497ab4d8bc9faf243c859d14d5d6b66",
    )


class RetrieveTransactionsResponseSchema(Schema):
    status = fields.String(example="success", description="Request status")
    transactions = fields.List(
        fields.Nested(TransactionSchema),
        description="List of transactions for the requested address",
    )


class DecryptionKeySuccessSchema(Schema):
    status = fields.String(example="success", description="Request status")
    message = fields.String(
        example="Decryption key was already entered",
        description="Optional message if key was already submitted",
    )


class DecryptionKeyErrorSchema(Schema):
    status = fields.String(example="error", description="Request status")
    message = fields.String(
        example="Invalid decryption key",
        description="Error message describing what went wrong",
    )


class DecryptionKeyFormSchema(Schema):
    key = fields.String(
        description="The decryption key to unlock the wallet",
        example="asdfasfasgasgasgasgdeagweg",
    )


class PayoutStatusResponseSchema(Schema):
    id = fields.Int(example=114, description="Internal payout ID")
    external_id = fields.String(
        example="abc123", description="External payout ID provided by merchant"
    )
    crypto = fields.String(example="BTC", description="Cryptocurrency code")
    status = fields.String(
        example="SUCCESS", description="Payout status: SUCCESS, IN_PROGRESS, FAIL"
    )
    amount = fields.String(example="100.50", description="Payout amount")
    destination = fields.String(
        example="0x1234567890abcdef...", description="Destination address"
    )
    txid = fields.String(
        example="0f999d988641395b38943d8a9c01581c19fcaa4dcdd4bb35f99e16510fdd10d6",
        description="Blockchain transaction ID (null if not yet broadcasted)",
    )


class PayoutStatusErrorSchema(Schema):
    error = fields.String(example="Payout not found", description="Error message")
