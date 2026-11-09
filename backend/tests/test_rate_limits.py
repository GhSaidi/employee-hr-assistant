import pytest
from employee_hr_assistant.api import rate_limits


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    # A fixed time, exactly at the start of a minute.
    current = {"now": 120}
    monkeypatch.setattr(rate_limits, "time", lambda: current["now"])
    return current


def test_allows_three_requests_per_minute(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    for _ in range(3):
        limiter.reserve("192.0.2.1")


def test_rejects_fourth_request_per_minute(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    for _ in range(3):
        limiter.reserve("192.0.2.1")

    with pytest.raises(rate_limits.UsageLimitExceeded) as caught:
        limiter.reserve("192.0.2.1")

    assert caught.value.retry_after == 60


def test_allows_request_after_minute_resets(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    for _ in range(3):
        limiter.reserve("192.0.2.1")

    with pytest.raises(rate_limits.UsageLimitExceeded):
        limiter.reserve("192.0.2.1")

    clock["now"] = 180

    limiter.reserve("192.0.2.1")


def test_rejects_eleventh_request_per_day(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    # Spread requests across minutes to avoid the minute limit.
    for number in range(10):
        clock["now"] = 120 + number * 60
        limiter.reserve("192.0.2.1")

    clock["now"] = 720

    with pytest.raises(rate_limits.UsageLimitExceeded) as caught:
        limiter.reserve("192.0.2.1")

    assert caught.value.retry_after == 86400 - 720


def test_allows_request_after_day_resets(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    for number in range(10):
        clock["now"] = 120 + number * 60
        limiter.reserve("192.0.2.1")

    with pytest.raises(rate_limits.UsageLimitExceeded):
        limiter.reserve("192.0.2.1")

    # Start of the next UTC day.
    clock["now"] = 86400

    limiter.reserve("192.0.2.1")


def test_rejects_request_after_global_daily_limit(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    # Different clients avoid reaching any individual client's quota.
    for number in range(100):
        limiter.reserve(f"192.0.2.{number + 1}")

    with pytest.raises(rate_limits.UsageLimitExceeded) as caught:
        limiter.reserve("192.0.2.101")

    assert caught.value.retry_after == 86400 - clock["now"]


def test_global_daily_limit_resets_at_midnight(clock: dict[str, int]) -> None:
    limiter = rate_limits.MemoryUsageLimiter()

    for number in range(100):
        limiter.reserve(f"192.0.2.{number + 1}")

    with pytest.raises(rate_limits.UsageLimitExceeded):
        limiter.reserve("192.0.2.101")

    clock["now"] = 86400

    limiter.reserve("192.0.2.101")


@pytest.mark.parametrize("mode", [None, "off", "memory"])
def test_ecs_rejects_non_dynamodb_modes(
    monkeypatch: pytest.MonkeyPatch,
    mode: str | None,
) -> None:
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")

    if mode is None:
        monkeypatch.delenv("USAGE_LIMIT_MODE", raising=False)
    else:
        monkeypatch.setenv("USAGE_LIMIT_MODE", mode)

    with pytest.raises(
        RuntimeError,
        match="ECS deployments require USAGE_LIMIT_MODE=dynamodb",
    ):
        rate_limits.create_usage_limiter()
