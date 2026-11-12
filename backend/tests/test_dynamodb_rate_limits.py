from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from employee_hr_assistant.api import rate_limits

if TYPE_CHECKING:
    from botocore.exceptions import (
        _CancellationReasonTypeDef,
        _ClientErrorResponseTypeDef,
    )
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.type_defs import TransactWriteItemTypeDef


class FakeTransactionCanceledException(ClientError):
    """Stand-in for the client's transaction cancellation exception."""


@pytest.mark.parametrize(
    "error",
    [
        BotoCoreError(),
        ClientError(
            {
                "Error": {
                    "Code": "InternalServerError",
                    "Message": "Simulated service failure",
                }
            },
            "TransactWriteItems",
        ),
    ],
    ids=["sdk-error", "service-error"],
)
def test_dynamodb_failure_makes_allowance_unavailable(
    error: BotoCoreError | ClientError,
) -> None:
    client = Mock()
    client.exceptions.TransactionCanceledException = (
        FakeTransactionCanceledException
    )
    client.transact_write_items.side_effect = error

    limiter = rate_limits.DynamoDBUsageLimiter(
        client=cast("DynamoDBClient", client),
        table_name="test-usage-limits",
    )

    with pytest.raises(rate_limits.UsageLimiterUnavailable):
        limiter.reserve("192.0.2.1")

    client.transact_write_items.assert_called_once()


@pytest.mark.parametrize(
    ("failed_rule", "expected_retry_after"),
    [
        (0, 86400 - 120),
        (1, 86400 - 120),
        (2, 60),
    ],
    ids=["global-day", "client-day", "client-minute"],
)
def test_dynamodb_quota_rejection(
    monkeypatch: pytest.MonkeyPatch,
    failed_rule: int,
    expected_retry_after: int,
) -> None:
    monkeypatch.setattr(rate_limits, "time", lambda: 120)

    reasons: list[_CancellationReasonTypeDef] = [
    {"Code": "None"} for _ in range(3)
    ]
    reasons[failed_rule] = {"Code": "ConditionalCheckFailed"}

    error = FakeTransactionCanceledException(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "Simulated quota rejection",
            },
            "CancellationReasons": reasons,
        },
        "TransactWriteItems",
    )

    client = Mock()
    client.exceptions.TransactionCanceledException = (
        FakeTransactionCanceledException
    )
    client.transact_write_items.side_effect = error

    limiter = rate_limits.DynamoDBUsageLimiter(
        client=cast("DynamoDBClient", client),
        table_name="test-usage-limits",
    )

    with pytest.raises(rate_limits.UsageLimitExceeded) as caught:
        limiter.reserve("192.0.2.1")

    assert caught.value.retry_after == expected_retry_after
    client.transact_write_items.assert_called_once()


@pytest.mark.parametrize(
    "reason_code",
    [None, "TransactionConflict"],
    ids=["missing-reasons", "transaction-conflict"],
)
def test_other_transaction_cancellations_make_allowance_unavailable(
    reason_code: str | None,
) -> None:
    error_response: _ClientErrorResponseTypeDef = {
        "Error": {
            "Code": "TransactionCanceledException",
            "Message": "Simulated transaction cancellation",
        },
    }

    if reason_code is not None:
        error_response["CancellationReasons"] = [{"Code": reason_code}]

    error = FakeTransactionCanceledException(
        error_response,
        "TransactWriteItems",
    )

    client = Mock()
    client.exceptions.TransactionCanceledException = (
        FakeTransactionCanceledException
    )
    client.transact_write_items.side_effect = error

    limiter = rate_limits.DynamoDBUsageLimiter(
        client=cast("DynamoDBClient", client),
        table_name="test-usage-limits",
    )

    with pytest.raises(rate_limits.UsageLimiterUnavailable):
        limiter.reserve("192.0.2.1")

    client.transact_write_items.assert_called_once()


def test_dynamodb_reserves_all_quotas_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limits, "time", lambda: 120)

    client = Mock()
    limiter = rate_limits.DynamoDBUsageLimiter(
        client=cast("DynamoDBClient", client),
        table_name="test-usage-limits",
    )

    limiter.reserve("192.0.2.1")

    client.transact_write_items.assert_called_once()
    call = client.transact_write_items.call_args
    assert call is not None

    items = cast(
        "list[TransactWriteItemTypeDef]",
        call.kwargs["TransactItems"],
    )

    assert len(items) == 3

    expected_rules = [
        ("global:day:0", 100, 172800),
        ("client:192.0.2.1:day:0", 10, 172800),
        ("client:192.0.2.1:minute:2", 3, 86580),
    ]

    for item, (key, maximum, expires_at) in zip(
        items, expected_rules, strict=True
    ):
        assert "Update" in item
        update = item["Update"]

        assert update["TableName"] == "test-usage-limits"
        assert update["Key"] == {"counter_key": {"S": key}}

        assert "ConditionExpression" in update
        assert update["ConditionExpression"] == (
            "attribute_not_exists(#count) OR #count < :maximum"
        )

        assert update["UpdateExpression"] == (
            "SET #count = if_not_exists(#count, :zero) + :one, "
            "#expires = :expires"
        )

        assert "ExpressionAttributeNames" in update
        assert update["ExpressionAttributeNames"] == {
            "#count": "request_count",
            "#expires": "expires_at",
        }

        assert "ExpressionAttributeValues" in update
        assert update["ExpressionAttributeValues"] == {
            ":zero": {"N": "0"},
            ":one": {"N": "1"},
            ":maximum": {"N": str(maximum)},
            ":expires": {"N": str(expires_at)},
        }

    token = call.kwargs["ClientRequestToken"]
    assert isinstance(token, str)
    assert token
