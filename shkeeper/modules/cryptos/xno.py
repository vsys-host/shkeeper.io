"""
Nano (XNO) cryptocurrency implementation.

Uses nanopy for local key management and works with any Nano RPC endpoint.

Environment variables:
    NANO_RPC_URL: Full URL to Nano RPC (default: https://rpc.nano.to)
    NANO_RPC_HOST: Alternative: just the host (will construct URL)
    NANO_RPC_PORT: Port if using NANO_RPC_HOST (default: 7076)
    NANO_REPRESENTATIVE: Representative for voting weight delegation
    XNO_WALLET: Set to 'enabled' to activate this crypto (default off)

Example setup with public RPC:
    XNO_WALLET=enabled
    NANO_RPC_URL=https://rpc.nano.to

Example setup with own node:
    XNO_WALLET=enabled
    NANO_RPC_HOST=localhost
    NANO_RPC_PORT=7076
"""

import os

from shkeeper.modules.classes.nano import Nano


class xno(Nano):
    """
    Nano (XNO) - The feeless, instant cryptocurrency.

    Features:
    - Feeless transactions
    - Near-instant confirmation
    - Local key management (works with any RPC)
    - Encrypted seed storage
    """

    _display_name = "Nano XNO"

    def __init__(self):
        super().__init__()
        self.crypto = "XNO"

        # Allow XNO-specific env vars to override NANO ones
        if xno_rpc_url := os.environ.get("XNO_RPC_URL"):
            self.NANO_RPC_URL = xno_rpc_url
        elif xno_rpc_host := os.environ.get("XNO_RPC_HOST"):
            port = os.environ.get("XNO_RPC_PORT", "7076")
            self.NANO_RPC_URL = f"http://{xno_rpc_host}:{port}"

        # Update setting names for XNO
        self._seed_setting_name = "xno_wallet_seed"
        self._addresses_setting_name = "xno_addresses"
        self._address_index_setting_name = "xno_address_index"

    def getname(self):
        return "Nano"
