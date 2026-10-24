FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY backend/src/ ./backend/src/

RUN python -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "employee_hr_assistant.api.app:app", "--host", "0.0.0.0", "--port", "8000"]