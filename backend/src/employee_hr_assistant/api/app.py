import logging
from typing import Annotated

from fastapi import FastAPI, HTTPException
from openai import OpenAIError
from pydantic import BaseModel, StringConstraints

from ..rag import direct

logger = logging.getLogger(__name__)

app = FastAPI(title="Employee HR Assistant API")


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


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        collection = direct.get_indexed_collection()
        openai_client = direct.get_openai_client()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

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