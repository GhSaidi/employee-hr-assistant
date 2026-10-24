# Employee HR Assistant — Frontend

Next.js frontend for the Employee HR Assistant, built with React and TypeScript.

The `/api/chat` route forwards questions to the Python FastAPI backend and returns its responses. The web interface lets users submit questions and view answers with document sources. It displays loading and error states. Each question is processed independently, without conversation history.

For backend installation, document indexing, and CLI usage, see the [main README](../README.md).

## Requirements

- Node.js compatible with the installed Next.js version
- npm
- The FastAPI backend configured and running

Tested with Node.js v24.21.0 and npm 11.19.0

## Installation

From the repository root:

```bash
cd frontend
npm ci
```

`npm ci` installs the dependencies recorded in `package-lock.json`.

## Configuration

From the `frontend` directory, copy the configuration template:

```bash
cp .env.example .env.local
```

Set the backend address in `.env.local`:

```dotenv
BACKEND_URL=http://127.0.0.1:8000
```

Keep `.env.local` in the `frontend` directory, alongside `package.json`.

`BACKEND_URL` is read by the Next.js development server when forwarding requests to FastAPI. The OpenAI API key is configured separately in `backend/.env`, relative to the repository root.

## Run with Docker Compose

To run the frontend and backend together in containers, follow [Run with Docker Compose](../README.md#run-with-docker-compose) in the main README.

The frontend Dockerfile uses a multi-stage build and Next.js standalone output. Docker Compose supplies `BACKEND_URL=http://backend:8000`; `frontend/.env.local` is not required for this setup.

The instructions below describe running the frontend locally without Docker.

## Local Development

Start the FastAPI backend in a separate terminal, from the repository root with `backend/venv` activated:

```bash
python -m uvicorn employee_hr_assistant.api.app:app --reload
```

Then start Next.js from the `frontend` directory:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Both servers must be running to test the API integration.

## API Integration

Send a POST request to the Next.js `/api/chat` endpoint:

```bash
curl -i http://localhost:3000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": "What is the parental leave policy?"}'
```

Next.js forwards the request to the backend's `/chat` endpoint. FastAPI validates the question and generates an answer using the indexed documents.

Successful responses contain `answer` and `sources` fields. Backend JSON responses and HTTP status codes are passed back to the caller.

A valid question requires a configured OpenAI API key and an existing document index. It makes OpenAI API calls.

To check request forwarding and validation without making an OpenAI call:

```bash
curl -i http://localhost:3000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": ""}'
```

The expected response is HTTP `422`, because the question is empty.

## Project Structure

```text
frontend/
├── public/
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   └── chat/
│   │   │       └── route.ts 
│   │   ├── favicon.ico
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   └── components/
│       └── Chat.tsx
├── .env.example
├── .gitignore
├── AGENTS.md
├── Dockerfile
├── eslint.config.mjs
├── next.config.ts
├── package-lock.json
├── package.json
├── README.md
└── tsconfig.json 
```
