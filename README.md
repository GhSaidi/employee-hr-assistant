# Employee HR Assistant

A PDF-based chatbot that helps employees find answers to questions about company policies, with references to the source documents.

## Overview

Employee HR Assistant uses Retrieval-Augmented Generation (RAG) to retrieve relevant PDF passages and generate answers grounded in those passages.

The Python backend provides a command-line interface and a FastAPI API. A Next.js frontend, built with React and TypeScript, provides a chatbot interface and forwards requests to the backend.

The current application answers questions from indexed PDFs. Access to individual employee records is a planned capability and is not implemented yet.

### Key Features

- PDF text extraction, chunking and indexing.
- Persistent storage of document passages and embeddings in ChromaDB.
- OpenAI-powered answer generation with document and page references.
- Command-line interface for indexing documents and asking questions.
- FastAPI endpoints with interactive API documentation.
- Web interface with loading and error states.
- Independent questions without conversation history.

## Requirements

- Python 3.12
- An OpenAI API key
- Node.js and npm to run the frontend

Tested with Python 3.12.14 and setuptools 84.0.0 on macOS.

See the [frontend README](frontend/README.md) for the tested Node.js and npm versions.

## Installation

Clone the repository:

```bash
git clone https://github.com/GhSaidi/employee-hr-assistant.git
cd employee-hr-assistant
```

Create and activate a virtual environment:

### Linux / macOS

```bash
python3.12 -m venv backend/venv
source backend/venv/bin/activate
```

Install the package and its dependencies, as defined in `pyproject.toml`:

```bash
python -m pip install .
```

For development, use an editable installation instead:

```bash
python -m pip install -e .
```

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

The `/chat` endpoint requires a configured `OPENAI_API_KEY` and indexed PDFs, as described in Configuration. Each question is processed independently, without conversation history.

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

## Build and Test the Wheel

Build an installable wheel and verify that the packaged application runs correctly in a clean environment.

```bash
python -m pip install build
```

From the repository root, with `backend/venv` activated, build the source distribution and wheel into `backend/dist/`:

```bash
python -m build --outdir backend/dist
```

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
│   │       │   └── app.py
│   │       ├── rag/
│   │       │   ├── __init__.py
│   │       │   └── direct.py
│   │       ├── __init__.py
│   │       └── main.py
│   └── .env.example
├── data/
│   ├── documents/
│   └── chroma_db/
├── frontend/
├── .gitignore
├── LICENSE
├── pyproject.toml
└── README.md
```

Local environment files, virtual environments and build outputs are omitted from this tree. Backend distributions are generated in `backend/dist/`.

## Contributing

Contributions are welcome.

1. Fork the repository and create a feature branch:

   ```bash
   git switch -c feature/my-feature
   ```

2. Make your changes and update the relevant documentation.
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