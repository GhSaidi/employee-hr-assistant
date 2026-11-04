from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from time import time
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.type_defs import TransactWriteItemTypeDef

QUESTIONS_PER_MINUTE = 3
QUESTIONS_PER_DAY = 10
GLOBAL_QUESTIONS_PER_DAY = 100


@dataclass(frozen=True)
class CounterRule:
    key: str
    maximum: int
    reset_at: int
    message: str


class UsageLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UsageLimiterUnavailable(Exception):
    """The usage allowance could not be checked safely."""


class UsageLimiter(Protocol):
    def reserve(self, client_id: str) -> None:
        """Reserve one question, or raise an exception."""
        ...


class DisabledUsageLimiter:
    """Allow requests without enforcing question quotas."""

    def reserve(self, client_id: str) -> None:
        pass


def build_counter_rules(client_id: str, now: int) -> list[CounterRule]:
    minute = now // 60
    day = now // 86400

    return [
        CounterRule(
            key=f"global:day:{day}",
            maximum=GLOBAL_QUESTIONS_PER_DAY,
            reset_at=(day + 1) * 86400,
            message=(
                "The demo has reached its daily question allowance. "
                "Please try again after midnight UTC."
            ),
        ),
        CounterRule(
            key=f"client:{client_id}:day:{day}",
            maximum=QUESTIONS_PER_DAY,
            reset_at=(day + 1) * 86400,
            message=(
                "Your network has reached its daily question allowance. "
                "Please try again after midnight UTC."
            ),
        ),
        CounterRule(
            key=f"client:{client_id}:minute:{minute}",
            maximum=QUESTIONS_PER_MINUTE,
            reset_at=(minute + 1) * 60,
            message=(
                "You are sending questions too quickly. "
                "Please wait a moment and try again."
            ),
        ),
    ]


class MemoryUsageLimiter:
    """Enforce question quotas within one Python process."""

    def __init__(self) -> None:
        self._counters: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def reserve(self, client_id: str) -> None:
        now = int(time())
        rules = build_counter_rules(client_id, now)

        with self._lock:
            self._counters = {
                key: (count, reset_at)
                for key, (count, reset_at) in self._counters.items()
                if reset_at > now
            }

            for rule in rules:
                count, _ = self._counters.get(
                    rule.key, (0, rule.reset_at)
                )

                if count >= rule.maximum:
                    raise UsageLimitExceeded(
                        rule.message,
                        retry_after=max(1, rule.reset_at - now),
                    )

            for rule in rules:
                count, _ = self._counters.get(
                    rule.key, (0, rule.reset_at)
                )
                self._counters[rule.key] = (
                    count + 1,
                    rule.reset_at,
                )


class DynamoDBUsageLimiter:
    """Enforce shared question quotas using DynamoDB transactions."""

    def __init__(
        self,
        client: DynamoDBClient,
        table_name: str,
    ) -> None:
        self._client = client
        self._table_name = table_name

    def reserve(self, client_id: str) -> None:
        now = int(time())
        rules = build_counter_rules(client_id, now)

        updates: list[TransactWriteItemTypeDef] = []

        for rule in rules:
            updates.append(
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "counter_key": {"S": rule.key},
                        },
                        "UpdateExpression": (
                            "SET #count = if_not_exists(#count, :zero) + :one, "
                            "#expires = :expires"
                        ),
                        "ConditionExpression": (
                            "attribute_not_exists(#count) OR #count < :maximum"
                        ),
                        "ExpressionAttributeNames": {
                            "#count": "request_count",
                            "#expires": "expires_at",
                        },
                        "ExpressionAttributeValues": {
                            ":zero": {"N": "0"},
                            ":one": {"N": "1"},
                            ":maximum": {"N": str(rule.maximum)},
                            ":expires": {
                                "N": str(rule.reset_at + 86400),
                            },
                        },
                    }
                }
            )

        try:
            self._client.transact_write_items(
                TransactItems=updates,
                ClientRequestToken=str(uuid4()),
            )
        except self._client.exceptions.TransactionCanceledException as exc:
            reasons = exc.response.get("CancellationReasons", [])

            for rule, reason in zip(rules, reasons):
                if reason.get("Code") == "ConditionalCheckFailed":
                    raise UsageLimitExceeded(
                        rule.message,
                        retry_after=max(1, rule.reset_at - int(time())),
                    ) from exc

            raise UsageLimiterUnavailable(
                "The demo could not check its usage allowance. "
                "Please try again shortly."
            ) from exc
        except (BotoCoreError, ClientError) as exc:
            raise UsageLimiterUnavailable(
                "The demo could not check its usage allowance. "
                "Please try again shortly."
            ) from exc


def create_usage_limiter() -> UsageLimiter:
    """Select and configure the usage limiter for this application."""
    mode = os.getenv("USAGE_LIMIT_MODE", "off").strip().lower()
    execution_env = os.getenv("AWS_EXECUTION_ENV", "")
    running_in_ecs = execution_env.startswith("AWS_ECS_")

    if running_in_ecs and mode != "dynamodb":
        raise RuntimeError(
            "ECS deployments require USAGE_LIMIT_MODE=dynamodb."
        )

    if mode == "off":
        return DisabledUsageLimiter()

    if mode == "memory":
        return MemoryUsageLimiter()

    if mode != "dynamodb":
        raise RuntimeError(
            "USAGE_LIMIT_MODE must be off, memory, or dynamodb."
        )

    table_name = os.getenv("USAGE_LIMIT_TABLE", "").strip()
    if not table_name:
        raise RuntimeError(
            "USAGE_LIMIT_TABLE is required in dynamodb mode."
        )

    region = (
        os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
    )
    if not region:
        raise RuntimeError(
            "Set AWS_REGION or AWS_DEFAULT_REGION in dynamodb mode."
        )

    client: DynamoDBClient = boto3.client(
        "dynamodb",
        region_name=region,
        config=Config(
            connect_timeout=3,
            read_timeout=3,
            retries={
                "mode": "standard",
                "total_max_attempts": 2,
            },
        ),
    )

    return DynamoDBUsageLimiter(
        client=client,
        table_name=table_name,
    )