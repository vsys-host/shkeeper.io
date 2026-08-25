from unittest.mock import Mock, patch

import pytest

from shkeeper.modules.cryptos.trx import trx


@pytest.fixture
def tron():
    return trx()


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("stake_trx", ("10", "ENERGY")),
        ("undelegate_trx", ("TRecipient", "10", "ENERGY")),
    ],
)
def test_staking_mutation_rejects_store_id_above_default(tron, method, args):
    with patch("shkeeper.modules.classes.tron_token.requests.post") as post:
        with pytest.raises(ValueError, match="store_id > 1"):
            getattr(tron, method)(*args, store_id=2)

    post.assert_not_called()


@pytest.mark.parametrize(
    ("method", "args", "path", "store_id", "headers"),
    [
        (
            "stake_trx",
            ("10", "ENERGY"),
            "/staking/freeze/10/ENERGY",
            None,
            {},
        ),
        (
            "stake_trx",
            ("10", "ENERGY"),
            "/staking/freeze/10/ENERGY",
            1,
            {"X-Store-ID": "1"},
        ),
        (
            "undelegate_trx",
            ("TRecipient", "10", "ENERGY"),
            "/staking/undelegate/TRecipient/10/ENERGY",
            None,
            {},
        ),
        (
            "undelegate_trx",
            ("TRecipient", "10", "ENERGY"),
            "/staking/undelegate/TRecipient/10/ENERGY",
            1,
            {"X-Store-ID": "1"},
        ),
    ],
)
def test_staking_mutation_allows_default_store(
    tron, method, args, path, store_id, headers
):
    response = Mock()
    response.json.return_value = {"status": "success"}

    with patch(
        "shkeeper.modules.classes.tron_token.requests.post", return_value=response
    ) as post:
        getattr(tron, method)(*args, store_id=store_id)

    post.assert_called_once_with(
        f"http://{tron.gethost()}{path}",
        auth=tron.get_auth_creds(),
        headers=headers,
    )
