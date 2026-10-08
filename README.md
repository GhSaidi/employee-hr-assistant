# Project Name

> This is a project to implement and deploy an Employee HR Assistant (a chatbot), where employees ask questions about company policies and their own HR-related information.


## Overview

**Employee HR Assistant** is a Python application that uses Retrieval Augmented Generation (RAG).

It is designed to answer questions about documents.

### Key Features

- ...


## Requirements

- Python 3.12
- An OpenAI API key

Tested with Python 3.12.14 and setuptools 84.0.0 on macOS.

## Installation

Clone the repository:

```bash
git clone https://github.com/GhSaidi/employee-hr-assistant.git
cd employee-hr-assistant
```

Create and activate a virtual environment:

### Linux / macOS

```bash
python3.12 -m venv venv
source venv/bin/activate
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
cp .env.example .env
```

Set your OpenAI API key in `.env`:

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

## Build and Test the Wheel

Build an installable wheel and verify that the packaged application runs correctly in a clean environment.

```bash
python -m pip install build
```

Build the source distribution and wheel distribution:

```bash
python -m build
```

Install the wheel (Use the generated wheel filename if the package version changes):

```bash
python -m pip install dist/employee_hr_assistant-0.1.0-py3-none-any.whl
python -m pip check
```

Verify the installed package location:

```bash
python -c "import employee_hr_assistant; print(employee_hr_assistant.__file__)"
```

The path should point to the environment's `site-packages` directory.

Run from the repository root:

```bash
hr-assistant index
hr-assistant chat
```

## Project Structure

```text
employee-hr-assistant/
├── src/
│   └── employee_hr_assistant/
│       ├── __init__.py
│       ├── main.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── app.py
│       └── rag/
│           ├── __init__.py
│           └── direct.py
├── data/
│   └── documents/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── LICENSE
```

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch:

```bash
git checkout -b feature/my-feature
```

3. Make your changes.
4. Add or update tests.
5. Run the test suite.
6. Commit your changes:

```bash
git commit -m "Add my feature"
```

7. Push the branch and open a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

**Author:** Ghassen Saidi

- GitHub: https://github.com/GhSaidi
- LinkedIn: https://www.linkedin.com/in/ghassensaidi/

---

If you find this project useful, consider giving it a ⭐ on GitHub.