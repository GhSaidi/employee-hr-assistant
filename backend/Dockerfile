FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY backend/src/ ./backend/src/

RUN python -m pip install --no-cache-dir --upgrade "pip==26.3" \
    && python -m pip install --no-cache-dir .

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