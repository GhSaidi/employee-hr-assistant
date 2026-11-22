# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PDF-based HR policy assistant using RAG. Python backend (CLI + FastAPI) in `backend/`, Next.js frontend in `frontend/`. Deployed on AWS ECS/Fargate behind an ALB as two containers in one task (frontend :3000 public via ALB, backend :8000 loopback only). AWS infra was configured by hand; there is no IaC in the repo. Python 3.12 only (`requires-python = ">=3.12.16,<3.13"`; Ruff and Pyright target 3.12), Node 24 for the frontend.

## Commands

All Python commands run from the **repository root**. `pyproject.toml` and `uv.lock` live at the root even though the code lives in `backend/src`. The local venv is `backend/venv`, not `.venv`, so set `UV_PROJECT_ENVIRONMENT`:

```bash
export UV_PROJECT_ENVIRONMENT=backend/venv
uv sync --locked --extra dev --group test --group quality   # full dev env

uv run pytest backend/tests                                  # all tests
uv run pytest backend/tests/test_api.py::test_health_returns_ok   # single test
uv run ruff check                                            # lint (import sorting included)
uv run ruff format --check                                   # formatting (CI enforces it; drop --check to apply)
uv run pyright                                               # strict type check of src + tests

source backend/venv/bin/activate   # needed for the next three commands (or prefix each with `uv run`)
hr-assistant index    # rebuild Chroma index from data/documents/*.pdf (billable OpenAI embeddings)
hr-assistant chat     # CLI chatbot
python -m uvicorn employee_hr_assistant.api.app:app --reload   # API at :8000/docs
```

The `test` and `quality` groups are not uv defaults. Pass them explicitly to `uv sync`/`uv run` (e.g. `--group test`), or run against a venv already synced with them. Pyright needs the `dev` extra (boto3 stubs) and the `test` group (pytest) to resolve imports. If dependencies change, run `uv lock` and commit `uv.lock`.

Frontend (from `frontend/`): `npm ci`, `npm run dev`, `npm run build`, `npm run lint`. There are no frontend tests.

Docker: `docker compose up --build` (needs `backend/.env` and an existing `data/chroma_db/`). Index inside Docker with `docker compose run --rm backend hr-assistant index`.

CI (`.github/workflows/ci.yaml`) runs on pushes to `main` and `feature/ci` (the branch for testing workflow changes before a PR), and on pull requests to `main`, on Ubuntu ARM64 runners: backend `ruff check`, `ruff format --check`, `pyright` and `pytest`; frontend `npm run lint` and `npm run build`; and `docker build --platform linux/arm64` for both images. It needs no secrets and doesn't deploy. Run the backend and frontend checks locally before pushing.

## Security rules

- Never hardcode API keys or passwords. Read them from environment variables with `os.environ` or `os.getenv`.
- Never use `eval()` or `exec()`.
- Ask before adding new network calls. The app's existing calls (OpenAI, S3, DynamoDB) are expected; any new external request needs explicit approval.

## Architecture

**Request path:** `Chat.tsx` → Next.js `src/app/api/chat/route.ts` (server-side proxy) → FastAPI `POST /chat` → `rag/direct.answer_question` → Chroma retrieval + OpenAI Responses API.

**`rag/direct.py`** holds all RAG logic, used by both the CLI (`main.py`) and the API. Paths come from `Path.cwd()` (`data/documents`, `data/chroma_db`, `backend/.env`), so processes must start from the repo root, or from a directory with the same layout (as the wheel-test instructions in README do). `DATABASE_DIR` is a module global that `api/app.py`'s lifespan reassigns when it loads the index from S3. `get_indexed_collection()` refuses to serve if the collection's stored `embedding_model` metadata differs from `EMBEDDING_MODEL`. If you change the embedding model or chunking, you must re-index.

**Index loading (`api/index_storage.py`):** if `CHROMA_S3_BUCKET` and `CHROMA_S3_KEY` are both set, the lifespan downloads a tar.gz of `chroma_db` into a temp dir (it accepts only regular files and dirs, using `filter="data"`). If neither is set, it uses local `data/chroma_db`. Setting only one is an error.

**Usage limits (`api/rate_limits.py`):** `create_usage_limiter()` picks one of three limiters via `USAGE_LIMIT_MODE`: `off` (the local default), `memory` (single process), or `dynamodb` (a single `TransactWriteItems` over three counters: global/day, client/day, client/minute; a `ConditionalCheckFailed` cancellation reason maps to 429). When `AWS_EXECUTION_ENV` starts with `AWS_ECS_`, `dynamodb` mode is required. Order in `/chat` matters: the concurrency slot (`BoundedSemaphore(2)`, 503 when full) is taken first, then the index and OpenAI client are initialized, and only then is quota reserved. That way, misconfiguration doesn't consume quota.

**Client IP trust chain:** in ECS, the frontend proxy requires `CLIENT_IP_SOURCE=alb`, takes the **last** `X-Forwarded-For` entry (the one the ALB appended), and sends it as `X-Client-IP`. The backend trusts `X-Client-IP` only in ECS and normalizes IPv4-mapped IPv6. Locally, both sides use `127.0.0.1`. Keep the two sides consistent when changing either.

**Error contract:** the backend maps failures to specific statuses: 422 validation, 400 unverifiable client IP (ECS only), 429 + `Retry-After` for quota, 503 busy/unavailable/limiter down (limiter down also sends `Retry-After: 5`), 502 OpenAI error. The proxy passes status, JSON body and `Retry-After` through and adds `Cache-Control: no-store`. The proxy also returns its own errors before or instead of calling the backend: 400 invalid JSON body or unusable `X-Forwarded-For`, 500 missing `BACKEND_URL` or invalid `CLIENT_IP_SOURCE`, 503 in ECS without `CLIENT_IP_SOURCE=alb`, 502 backend unreachable. Errors use the `{"detail": ...}` shape on both sides; `Chat.tsx` displays `detail` when it is a string and a generic message otherwise (FastAPI's 422 `detail` is a list).

## Testing conventions

Tests must never hit OpenAI, AWS, the real index, or the local `.env`. `test_api.py`'s `client` fixture patches `dotenv.load_dotenv` **before** importing the app module. It clears `AWS_EXECUTION_ENV`, `CHROMA_S3_BUCKET`, `CHROMA_S3_KEY` and `OPENAI_API_KEY`, sets `USAGE_LIMIT_MODE=off`, and replaces `download_index`, `get_indexed_collection`, `get_openai_client`, and `answer_question` with mocks that raise if called. Individual tests then override the specific mock they need. DynamoDB tests use a `Mock` client and a `ClientError` subclass in place of `TransactionCanceledException`. Add or update tests for changed behavior. Tests run under strict Pyright like `src`: silence a check only with a rule-specific `# pyright: ignore[ruleName]` plus a short reason comment, as `test_dynamodb_rate_limits.py` does for botocore's private stub types.

## Claude Code guardrails

`.claude/` holds this project's guardrails. Only a human edits `.claude/settings*.json` and `.claude/hooks/`; Claude proposes changes as exact text.

- **Permissions** (`.claude/settings.json`): deny reading or editing secrets (`.env` files, keys, `~/.ssh`, `~/.aws`), deleting files (`rm`, `rmdir`, `unlink`, `git rm`, `git clean`), network tools and force pushes. Ask before `git commit`, `git push`, `git reset --hard` and `docker`.
- **Hooks** (`.claude/hooks/`): `protect-files.sh` confines file tools to the project, `~/.claude` and Claude Code's temp folder, and blocks secrets and write-protected files. `validate-commands.sh` blocks deletions and other risky Bash patterns, and forces a prompt for Docker, commits, pushes and paths outside the project. Both fail closed and target `/bin/bash` 3.2.
- **Sandbox**: Bash runs in the OS sandbox with regular permission prompts. Writes are limited to the project, the temp folder and the uv/npm caches. `~/Documents`, `~/Desktop` and `~/Downloads` are unreadable, except the project itself. Network access is limited to package registries, GitHub and Google Fonts; `api.openai.com` is always denied. `docker` runs outside the sandbox.
- **Testing the guardrails**: `bash .claude/hooks/test-hooks.sh`, run by a human from the repository root (Claude's own Bash hook blocks it). The tested commands are strings and are never executed. Live tests of destructive commands only target throwaway files in a temp directory, never real files or secrets.

Known sandbox limitations:
- `npm run build` fails inside the sandbox: `next/font/google` downloads fonts with networking code that ignores the sandbox proxy. Run frontend builds outside the sandbox (approved per command). `npm run lint` works sandboxed.
- pytest collection would touch `backend/.env`, which the sandbox makes unreadable, so `pyproject.toml` sets `addopts = ["--ignore=backend/.env"]`. Keep it.
- `git push` over SSH fails inside the sandbox.

## Frontend note

`frontend/AGENTS.md`: this project uses Next.js 16 (with `cacheComponents`, `partialPrefetching`, standalone output, and Tailwind v4 via the Turbopack loader). APIs may differ from what you expect. Read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing Next.js code. `next dev` re-adds that AGENTS.md block automatically.
