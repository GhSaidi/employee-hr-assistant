from collections.abc import Generator
from threading import BoundedSemaphore
from unittest.mock import Mock

import dotenv
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    # Prevent application imports from loading the local .env file.
    monkeypatch.setattr(dotenv, "load_dotenv", Mock(return_value=False))

    from employee_hr_assistant.api import app as api_module

    # Use controlled local startup settings.
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
    monkeypatch.delenv("CHROMA_S3_BUCKET", raising=False)
    monkeypatch.delenv("CHROMA_S3_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("USAGE_LIMIT_MODE", "off")

    # These tests must never access external services or the real index.
    for target, name in (
        (api_module, "download_index"),
        (api_module.direct, "get_indexed_collection"),
        (api_module.direct, "get_openai_client"),
        (api_module.direct, "answer_question"),
    ):
        monkeypatch.setattr(
            target,
            name,
            Mock(side_effect=AssertionError(f"Unexpected call to {name}")),
        )

    with TestClient(api_module.app) as test_client:
        yield test_client


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "question",
    ["", "   ", "x" * 2001],
    ids=["empty", "whitespace-only", "too-long"],
)
def test_chat_rejects_invalid_question(
    client: TestClient,
    question: str,
) -> None:
    response = client.post("/chat", json={"question": question})

    assert response.status_code == 422


def test_chat_returns_answer_and_sources(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from employee_hr_assistant.api import app as api_module

    collection = object()
    openai_client = Mock()
    configured_client = Mock()
    openai_client.with_options.return_value = configured_client

    answer_question = Mock(
        return_value=(
            "Example policy answer [1].",
            [{"source": "example-policy.pdf", "page": 2}],
        )
    )

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=collection),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=openai_client),
    )
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "  What is the policy?  "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Example policy answer [1].",
        "sources": [
            {"number": 1, "source": "example-policy.pdf", "page": 2},
        ],
    }

    openai_client.with_options.assert_called_once_with(
        timeout=20.0,
        max_retries=0,
    )
    answer_question.assert_called_once_with(
        "What is the policy?",
        collection,
        configured_client,
    )


def test_chat_returns_429_when_quota_is_exhausted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from employee_hr_assistant.api import app as api_module

    limiter = Mock()
    limiter.reserve.side_effect = api_module.UsageLimitExceeded(
        "Test quota exhausted.",
        retry_after=30,
    )
    monkeypatch.setattr(api_module.app.state, "usage_limiter", limiter)

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )

    answer_question = Mock(
        side_effect=AssertionError("Answer generation must not run")
    )
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {"detail": "Test quota exhausted."}

    limiter.reserve.assert_called_once_with("127.0.0.1")
    answer_question.assert_not_called()


def test_chat_fails_closed_when_quota_store_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from employee_hr_assistant.api import app as api_module

    limiter = Mock()
    limiter.reserve.side_effect = api_module.UsageLimiterUnavailable(
        "Simulated quota-store failure"
    )
    monkeypatch.setattr(api_module.app.state, "usage_limiter", limiter)

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )

    answer_question = Mock(
        side_effect=AssertionError("Answer generation must not run")
    )
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {
        "detail": (
            "The demo could not check its usage allowance. "
            "Please try again shortly."
        ),
    }

    answer_question.assert_not_called()

    health_response = client.get("/health")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    limiter.reserve.assert_called_once_with("127.0.0.1")


def test_chat_returns_502_when_openai_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from employee_hr_assistant.api import app as api_module

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )

    answer_question = Mock(
        side_effect=api_module.OpenAIError("Simulated upstream failure")
    )
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The AI service could not complete the request.",
    }
    answer_question.assert_called_once()


@pytest.mark.parametrize(
    "failed_component",
    ["get_indexed_collection", "get_openai_client"],
    ids=["index-unavailable", "openai-configuration-unavailable"],
)
def test_chat_returns_503_when_initialization_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    failed_component: str,
) -> None:
    from employee_hr_assistant.api import app as api_module

    limiter = Mock()
    monkeypatch.setattr(api_module.app.state, "usage_limiter", limiter)

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        api_module.direct,
        failed_component,
        Mock(side_effect=RuntimeError("Simulated initialization failure")),
    )

    answer_question = Mock(
        side_effect=AssertionError("Answer generation must not run")
    )
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The assistant is temporarily unavailable.",
    }

    limiter.reserve.assert_not_called()
    answer_question.assert_not_called()


def test_chat_returns_503_when_all_slots_are_occupied(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from employee_hr_assistant.api import app as api_module

    slots = BoundedSemaphore(api_module.MAX_CONCURRENT_CHATS)
    monkeypatch.setattr(api_module, "chat_slots", slots)

    get_collection = Mock(
        side_effect=AssertionError("Chat initialization must not run")
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        get_collection,
    )

    for _ in range(api_module.MAX_CONCURRENT_CHATS):
        assert slots.acquire(blocking=False)

    try:
        response = client.post(
            "/chat",
            json={"question": "What is the policy?"},
        )

        assert response.status_code == 503
        assert response.json() == {
            "detail": "The demo is currently busy. Please try again shortly."
        }
        get_collection.assert_not_called()

        health_response = client.get("/health")

        assert health_response.status_code == 200
        assert health_response.json() == {"status": "ok"}
    finally:
        for _ in range(api_module.MAX_CONCURRENT_CHATS):
            slots.release()


@pytest.mark.parametrize(
    "upstream_fails",
    [False, True],
    ids=["success", "openai-failure"],
)
def test_chat_releases_slot_after_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    upstream_fails: bool,
) -> None:
    from employee_hr_assistant.api import app as api_module

    slots = BoundedSemaphore(api_module.MAX_CONCURRENT_CHATS)
    monkeypatch.setattr(api_module, "chat_slots", slots)

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )

    answer_question = Mock(return_value=("Example answer.", []))
    if upstream_fails:
        answer_question.side_effect = api_module.OpenAIError(
            "Simulated upstream failure"
        )

    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
    )

    assert response.status_code == (502 if upstream_fails else 200)
    answer_question.assert_called_once()

    # Every slot must be available again after the request finishes.
    acquired_slots = 0
    try:
        for _ in range(api_module.MAX_CONCURRENT_CHATS):
            assert slots.acquire(blocking=False)
            acquired_slots += 1

        assert not slots.acquire(blocking=False)
    finally:
        for _ in range(acquired_slots):
            slots.release()


@pytest.mark.parametrize(
    "client_ip",
    [None, "", "not-an-ip", "192.0.2.1, 192.0.2.2", "fe80::1%eth0"],
    ids=["missing", "empty", "invalid", "multiple-addresses", "scoped-ipv6"],
)
def test_chat_rejects_invalid_client_ip_in_ecs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    client_ip: str | None,
) -> None:
    from employee_hr_assistant.api import app as api_module

    # Simulate ECS request handling after the test client's local startup.
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")

    limiter = Mock()
    monkeypatch.setattr(api_module.app.state, "usage_limiter", limiter)

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )

    answer_question = Mock(
        side_effect=AssertionError("Answer generation must not run")
    )
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    headers = {}
    if client_ip is not None:
        headers["x-client-ip"] = client_ip

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unable to verify the request's client address."
    }
    limiter.reserve.assert_not_called()
    answer_question.assert_not_called()


@pytest.mark.parametrize(
    ("running_in_ecs", "client_ip", "expected_client_id"),
    [
        (True, "192.0.2.1", "192.0.2.1"),
        (True, " 192.0.2.1 ", "192.0.2.1"),
        (True, "2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        (True, "::ffff:192.0.2.1", "192.0.2.1"),
        (False, "192.0.2.99", "127.0.0.1"),
    ],
    ids=[
        "ecs-ipv4",
        "ecs-whitespace",
        "ecs-ipv6-normalization",
        "ecs-ipv4-mapped-ipv6",
        "local-ignores-client-header",
    ],
)
def test_chat_reserves_quota_for_expected_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    running_in_ecs: bool,
    client_ip: str,
    expected_client_id: str,
) -> None:
    from employee_hr_assistant.api import app as api_module

    if running_in_ecs:
        monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")
    else:
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)

    limiter = Mock()
    monkeypatch.setattr(api_module.app.state, "usage_limiter", limiter)

    monkeypatch.setattr(
        api_module.direct,
        "get_indexed_collection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        api_module.direct,
        "get_openai_client",
        Mock(return_value=Mock()),
    )

    answer_question = Mock(return_value=("Example answer.", []))
    monkeypatch.setattr(
        api_module.direct,
        "answer_question",
        answer_question,
    )

    response = client.post(
        "/chat",
        json={"question": "What is the policy?"},
        headers={"x-client-ip": client_ip},
    )

    assert response.status_code == 200
    limiter.reserve.assert_called_once_with(expected_client_id)
    answer_question.assert_called_once()
