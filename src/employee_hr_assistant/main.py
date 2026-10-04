import argparse

from .rag import direct


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask questions about employee HR documents. Use 'index' to index PDFs and 'chat' to ask questions."
    )
    parser.add_argument(
        "command", 
        choices=["index", "chat"],
        help="Index the PDFs or start the chatbot."
    )
    args = parser.parse_args()

    if args.command == "index":
        direct.index_documents()
    else:
        direct.chat()

if __name__ == "__main__":
    main()