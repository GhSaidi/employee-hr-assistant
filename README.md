# Employee HR Assistant

A publicly deployed, PDF-based HR policy assistant that uses Retrieval-Augmented Generation (RAG) to answer employee questions with references to source documents.

**Live demo:** [hr-assistant.ghassensaidi.com](https://hr-assistant.ghassensaidi.com/)

## Overview

For each question, the backend retrieves relevant passages from the indexed PDFs and generates an answer grounded in that evidence.

The Python backend provides a command-line interface and a FastAPI API. A Next.js frontend, built with React and TypeScript, provides the chatbot interface and proxies requests to the backend. The demo is deployed on AWS ECS/Fargate and accessible over HTTPS through an Application Load Balancer (ALB).

The current application answers questions from indexed PDFs. Access to individual employee records is a planned capability and is not implemented yet.

### Key Features

- PDF text extraction, chunking and indexing.
- Persistent storage of document passages and embeddings in ChromaDB.
- OpenAI-powered answer generation with document and page references.
- Command-line interface for indexing documents and asking questions.
- FastAPI endpoints with interactive API documentation.
- Web interface with loading and error states.
- Independent questions without conversation history.
- Public HTTPS demo deployed to AWS ECS/Fargate.
- Per-visitor and global usage quotas backed by DynamoDB in production.
- Request-length, concurrency, and OpenAI output limits.

## Architecture and AWS Deployment

The production demo follows this request path:

```text
Browser
  │ HTTPS
  ▼
Application Load Balancer (ACM TLS certificate)
  │ forwards to port 3000
  ▼
ECS/Fargate task (Linux/ARM64)
  ├── Next.js frontend (port 3000)
  │     └── /api/chat → FastAPI at 127.0.0.1:8000
  └── FastAPI backend (port 8000)
        ├── ChromaDB index downloaded from private S3 at startup
        ├── DynamoDB usage counters
        └── OpenAI API for embeddings and answers
```

- **Container registry and compute:** Backend and frontend images are stored in private Amazon ECR repositories and run as separate containers within the same ECS/Fargate task.
- **Networking:** An internet-facing ALB handles HTTPS traffic and HTTP/canonical-hostname redirects. The ECS task is reachable on frontend port `3000` only from the ALB security group; backend port `8000` is not exposed to the public internet. The containers communicate over the task's loopback interface.
- **Domain and TLS:** DNS for `hr-assistant.ghassensaidi.com` is managed through Porkbun. AWS Certificate Manager (ACM) supplies the HTTPS certificate.
- **Data and secrets:** The Chroma index is downloaded from a private S3 object at startup. The OpenAI API key is supplied through AWS Systems Manager Parameter Store via the ECS task definition, not stored in the container image.
- **IAM and observability:** Separate ECS task and task-execution IAM roles provide scoped application and platform permissions. Container logs are sent to Amazon CloudWatch Logs.

The AWS infrastructure was configured through the AWS Console and CLI. **Infrastructure-as-code is not yet part of this repository.** The local setup instructions below do not recreate the AWS deployment automatically.

### Usage Limits and Security

The public demo enforces the following limits in the FastAPI backend before calling OpenAI:

| Control | Production setting |
|---|---|
| Questions per visitor | 3 per minute; 10 per UTC day |
| Questions across all visitors | 100 per UTC day |
| Concurrent chats | 2 per Python process |
| Question length | 1–2,000 characters after trimming whitespace |
| Model output | Maximum 500 output tokens; concise answers requested |
| OpenAI client | 20-second timeout per SDK request; automatic retries disabled |

Visitor quotas are based on IP addresses, not authenticated accounts. The ALB appends the connecting client's IP to `X-Forwarded-For`; the Next.js proxy validates the ALB-appended address and forwards a new `X-Client-IP` to FastAPI. The backend validates that address and reserves the visitor-minute, visitor-day, and global-day counters in one DynamoDB transaction. Exceeded limits return HTTP `429` with `Retry-After`. If the quota store cannot be checked, the backend returns HTTP `503` without generating an answer.

Locally, usage limits are **disabled by default** so a developer can use their own OpenAI API key without the public demo's DynamoDB table. Set `USAGE_LIMIT_MODE=memory` to exercise in-process quotas locally; this mode is not suitable for multi-task production deployments. ECS requires `USAGE_LIMIT_MODE=dynamodb`, a configured `USAGE_LIMIT_TABLE`, and an AWS region.

## Requirements

- Python `>=3.12.16,<3.13` (as required by `pyproject.toml`)
- uv for locked local backend installation (not required for Docker Compose)
- An OpenAI API key
- Node.js and npm to run the frontend (or Docker and Docker Compose for containerized development)

The backend was tested with Python 3.12.16 and uv 0.13.7. The deployed frontend container runs Node.js 24.22.2. See the [frontend README](frontend/README.md) for locally tested Node.js and npm versions.

## Installation

Clone the repository:

```bash
git clone https://github.com/GhSaidi/employee-hr-assistant.git
cd employee-hr-assistant
```

### Linux / macOS

From the repository root, create or synchronize `backend/venv` using the exact dependency versions recorded in `uv.lock`, then activate it:

```bash
UV_PROJECT_ENVIRONMENT=backend/venv uv sync --locked --no-dev
source backend/venv/bin/activate
```

uv installs the project in editable mode by default for local development. To include the optional AWS type stubs, add `--extra dev` to the `uv sync` command. When dependencies in `pyproject.toml` change, run `uv lock` and commit the updated `uv.lock`.

Unlike `uv sync`, a direct `pip install .` does not use `uv.lock` and may resolve different dependency versions.

### Configuration

Copy the configuration template:

```bash
cp backend/.env.example backend/.env
```

Set your OpenAI API key in `backend/.env`:

```dotenv
OPENAI_API_KEY=your_openai_api_key
```

## Quick Start

Run the following commands from the repository root, with the virtual environment activated.

Index the PDF documents:

```bash
hr-assistant index
```

Start the chatbot:

```bash
hr-assistant chat
```

Type `exit` or `quit` to end the chat.

## API usage

Start the development server from the repository root:

```bash
python -m uvicorn employee_hr_assistant.api.app:app --reload
```

Open <http://127.0.0.1:8000/docs> to explore and test the API.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check whether the API responds |
| POST | `/chat` | Ask a question and receive an answer with sources |

The `/chat` endpoint requires a configured `OPENAI_API_KEY` and indexed PDFs, as described in Configuration. Each question is processed independently, without conversation history. Production requests are also subject to the [usage limits](#usage-limits-and-security) described above.

## Frontend Development

The frontend provides a chatbot interface for submitting questions and viewing answers with document sources, including loading and error states. Its `/api/chat` endpoint forwards POST requests to the FastAPI backend.

Start the backend as described in [API usage](#api-usage), with the Python virtual environment activated. Leave it running.

In a separate terminal, from the repository root, install the frontend dependencies and copy the configuration template:

```bash
cd frontend
npm ci
cp .env.example .env.local
```

These commands are for initial setup. If `.env.local` already exists, retain your existing configuration.

Start the Next.js development server from the `frontend` directory:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Both servers must be running for chat requests to work. Answer generation also requires the configured OpenAI API key and indexed PDF documents.

See the [frontend README](frontend/README.md) for frontend configuration, API integration, and project structure.

## Run with Docker Compose

Docker Compose runs the FastAPI backend and Next.js frontend in separate containers. The backend uses a two-stage Docker build: uv installs the dependencies locked in `uv.lock` and the packaged application into `/opt/venv`; the runtime image copies this environment and runs without uv as a non-root user. The backend Dockerfile obtains uv from its official container image during the build. Therefore, uv does not need to be installed locally when running the application through Docker Compose.

The lockfile fixes Python dependency versions; the `python:3.12-slim` base-image tag may still receive updates between builds.

### Prerequisites

- Docker Engine and Docker Compose available and running. On macOS, Docker Desktop provides both.
- An OpenAI API key configured in `backend/.env`.
- A document index in `data/chroma_db/`. For first-time setup, follow [Index Documents — Operator CLI](#index-documents--operator-cli) below before starting the application.

The current version answers questions using pre-indexed documents. The web interface and HTTP API do not provide file uploads or indexing.

Tested with Docker Engine 29.8.2 and Docker Compose 5.5.1 on macOS.

### Initial Configuration

From the repository root, create the backend environment file if it does not already exist:

```bash
cp -n backend/.env.example backend/.env
```

Set `OPENAI_API_KEY` in `backend/.env`.

Compose supplies the frontend's `BACKEND_URL` automatically. A frontend `.env.local` file is not required for this Docker setup.

### Start the Application

From the repository root:

```bash
docker compose up --build
```

Open:

- Web interface: http://localhost:3000
- Backend API documentation: http://localhost:8000/docs

To run in the background instead:

```bash
docker compose up --build -d
```

View logs:

```bash
docker compose logs -f
```

### Stop the Application

```bash
docker compose down
```

This removes the containers and Compose network. The images and local `data/` folder are preserved.

### Data Storage

Compose mounts the repository's `data/` directory at `/app/data` inside the backend container.

PDFs and ChromaDB files are not included in either image. Database changes made through the mount persist in the local `data/chroma_db/` directory.

### Index Documents — Operator CLI

Indexing is a separate operator task, not an HTTP API or web-interface feature.

For initial setup, or when deliberately rebuilding the index, place PDFs in `data/documents/`. Stop the application before rebuilding:

```bash
docker compose down
docker compose build backend
docker compose run --rm backend hr-assistant index
```

This rebuilds the collection in `data/chroma_db/` and makes billable OpenAI embedding requests. Do not run it for ordinary application restarts.

After indexing finishes successfully, start the application:

```bash
docker compose up -d
```

Local PDF ingestion is implemented through the CLI. User uploads and automatically triggered ingestion are planned for a later stage.

## Build and Test the Wheel

Build an installable wheel and verify that the packaged application runs correctly in a clean environment. From the repository root, build the source distribution and wheel into `backend/dist/`:

```bash
uv build --out-dir backend/dist
```

This uses the setuptools build backend defined in `pyproject.toml` without requiring pip in `backend/venv`. The standalone wheel installation test below uses pip in a separate test environment and resolves requirements from package metadata; it does not install from `uv.lock`.

Create a fresh test environment outside the repository. Run these commands from the repository root, using a test directory that does not already exist:

```bash
python3.12 -m venv ../project_tests-employee_hr_assistant/venv
../project_tests-employee_hr_assistant/venv/bin/python -m pip install backend/dist/employee_hr_assistant-0.1.0-py3-none-any.whl
```

Use the generated wheel filename if the package version changes.

Move outside the repository and verify the installation:

```bash
cd ../project_tests-employee_hr_assistant
venv/bin/python -m pip check
venv/bin/python -c "import employee_hr_assistant; print(employee_hr_assistant.__file__)"
venv/bin/hr-assistant --help
```

The printed package path should point into the test environment's `site-packages` directory.

To test answering questions, copy the existing database and backend configuration from the development repository. Stop both the development and test backend servers before copying the database.

From `project_tests-employee_hr_assistant`, run:

```bash
mkdir -p data backend
cp -R ../employee-hr-assistant/data/chroma_db data/
cp -n ../employee-hr-assistant/backend/.env backend/.env
```

These commands assume the fresh test directory created above. They copy the existing index and API-key configuration without modifying the development repository. Keep the copied `.env` private.

Start the wheel-installed backend from the test directory:

```bash
venv/bin/python -m uvicorn employee_hr_assistant.api.app:app
```

Open http://127.0.0.1:8000/docs and submit a question about the indexed documents through `POST /chat`. Verify that it returns HTTP 200 with an answer and source references.

The original PDFs are not required for this chat test because the copied database already contains the indexed passages. Rebuilding the index would additionally require PDFs in `data/documents/`.

Stop the test server with Ctrl+C when finished.

To test the command-line chatbot using the same installed wheel and copied index, run from `project_tests-employee_hr_assistant`:

```bash
venv/bin/hr-assistant chat
```

Ask a question about the indexed documents. Type `exit` or `quit` to finish.

To also test rebuilding the index, first copy the PDF documents into the test directory:

```bash
cp -R ../employee-hr-assistant/data/documents data/
venv/bin/hr-assistant index
venv/bin/hr-assistant chat
```

Indexing rebuilds the test database and makes OpenAI embedding API requests, which incur usage costs. The development database remains unchanged.

## Project Structure

```text
employee-hr-assistant/
├── backend/
│   ├── src/
│   │   └── employee_hr_assistant/
│   │       ├── api/
│   │       │   ├── __init__.py
│   │       │   ├── app.py
│   │       │   ├── index_storage.py
│   │       │   └── rate_limits.py
│   │       ├── rag/
│   │       │   ├── __init__.py
│   │       │   └── direct.py
│   │       ├── __init__.py
│   │       └── main.py
│   ├── .env.example
│   └── Dockerfile
├── data/
│   ├── documents/
│   └── chroma_db/
├── frontend/
│   ├── src/
│   │   ├── app/               # Pages and /api/chat proxy
│   │   └── components/        # Chat UI
│   ├── Dockerfile
│   ├── package.json
│   ├── package-lock.json
│   └── README.md
├── .dockerignore
├── .gitignore
├── compose.yaml
├── LICENSE
├── pyproject.toml
├── uv.lock
└── README.md
```

Sensitive files are excluded for security, and generated files for storage efficiency and maintainability. The project structure is simplified for readability. Backend distributions are generated in `backend/dist/`.

## Contributing

Contributions are welcome.

1. Fork the repository and create a feature branch:

   ```bash
   git switch -c feature/my-feature
   ```

2. Make your changes and update the relevant documentation. If Python dependency requirements change, run `uv lock` and commit the updated `uv.lock`.
3. Verify the affected functionality. For backend changes, follow the wheel build and testing instructions above. For frontend changes, follow the checks in the [frontend README](frontend/README.md).
4. Review and stage your changes, then commit your changes:

   ```bash
   git commit -m "feat: Add my feature"
   ```

5. Push your branch and open a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

**Author:** Ghassen Saidi

- GitHub: https://github.com/GhSaidi
- LinkedIn: https://www.linkedin.com/in/ghassensaidi/

---

If you find this project useful, consider giving it a ⭐ on GitHub.