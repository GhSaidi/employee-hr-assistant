# Build stage: install locked Python dependencies.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY backend/src/ ./backend/src/

RUN uv sync --locked --no-dev --no-editable


# Runtime stage: run the application without uv.
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Create a dedicated non-root user.
RUN groupadd --gid 10001 appuser \
    && useradd --no-log-init \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --home-dir /home/appuser \
        --shell /usr/sbin/nologin \
        appuser

ENV HOME=/home/appuser

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "employee_hr_assistant.api.app:app", "--host", "0.0.0.0", "--port", "8000"]