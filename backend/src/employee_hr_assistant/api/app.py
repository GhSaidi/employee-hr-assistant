import logging
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from ipaddress import IPv6Address, ip_address
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from openai import OpenAIError
from pydantic import BaseModel, StringConstraints

from ..rag import direct
from .index_storage import download_index
from .rate_limits import (
    DisabledUsageLimiter,
    UsageLimiter,
    UsageLimiterUnavailable,
    UsageLimitExceeded,
    create_usage_limiter,
)

logger = logging.getLogger(__name__)
MAX_CONCURRENT_CHATS = 2
chat_slots = BoundedSemaphore(MAX_CONCURRENT_CHATS)


def require_chat_slot() -> Generator[None, None, None]:
    if not chat_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="The demo is currently busy. Please try again shortly.",
        )

    try:
        yield
    finally:
        chat_slots.release()


def reserve_chat_allowance(http_request: Request) -> None:
    limiter = cast(UsageLimiter, http_request.app.state.usage_limiter)

    if isinstance(limiter, DisabledUsageLimiter):
        return

    running_in_ecs = os.getenv(
        "AWS_EXECUTION_ENV", ""
    ).startswith("AWS_ECS_")

    if running_in_ecs:
        # Next.js supplies this header after reading the ALB client address.
        raw_ip = http_request.headers.get("x-client-ip", "")
    else:
        # Local quota testing uses one shared client identifier.
        raw_ip = "127.0.0.1"

    try:
        address = ip_address(raw_ip.strip())

        if isinstance(address, IPv6Address):
            if address.scope_id is not None:
                raise ValueError("Scoped client addresses are unsupported.")

            if address.ipv4_mapped is not None:
                address = address.ipv4_mapped

        client_id = str(address)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to verify the request's client address.",
        ) from exc

    try:
        limiter.reserve(client_id)
    except UsageLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except UsageLimiterUnavailable:
        logger.error("The usage allowance check failed.")
        raise HTTPException(
            status_code=503,
            detail=(
                "The demo could not check its usage allowance. "
                "Please try again shortly."
            ),
            headers={"Retry-After": "5"},
        ) from None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.usage_limiter = create_usage_limiter()

    bucket = os.getenv("CHROMA_S3_BUCKET", "").strip()
    key = os.getenv("CHROMA_S3_KEY", "").strip()

    if not bucket and not key:
        # Local operation: use the existing data/chroma_db directory.
        yield
        return

    if not bucket or not key:
        raise RuntimeError(
            "Set both CHROMA_S3_BUCKET and CHROMA_S3_KEY, or neither."
        )

    original_database_dir = direct.DATABASE_DIR

    with TemporaryDirectory(prefix="hr-assistant-index-") as temporary_dir:
        destination = Path(temporary_dir)
        download_index(bucket, key, destination)
        direct.DATABASE_DIR = destination / "chroma_db"

        try:
            collection = direct.get_indexed_collection()
            logger.info(
                "S3 index loaded successfully: %s chunks",
                collection.count(),
            )
            yield
        finally:
            direct.DATABASE_DIR = original_database_dir


app = FastAPI(
    title="Employee HR Assistant API",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=2000,
        ),
    ]


class Source(BaseModel):
    number: int
    source: str
    page: int


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_chat_slot)])
def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    try:
        collection = direct.get_indexed_collection()
        openai_client = direct.get_openai_client().with_options(
            timeout=20.0,
            max_retries=0,
        )
    except RuntimeError as exc:
        logger.error("Chat initialization failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="The assistant is temporarily unavailable.",
        ) from exc

    reserve_chat_allowance(http_request)

    try:
        answer, metadata = direct.answer_question(
            request.question,
            collection,
            openai_client,
        )
    except OpenAIError as exc:
        logger.exception("OpenAI request failed")
        raise HTTPException(
            status_code=502,
            detail="The AI service could not complete the request.",
        ) from exc

    sources = [
        Source.model_validate(
            {
                "number": number,
                "source": item["source"],
                "page": item["page"],
            }
        )
        for number, item in enumerate(metadata, start=1)
    ]

    return ChatResponse(answer=answer, sources=sources)