"use client";

import { useState, type FormEvent } from "react";

type Source = {
  number: number;
  source: string;
  page: number;
};

type ChatResponse = {
  answer: string;
  sources: Source[];
};

function isChatResponse(value: unknown): value is ChatResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  if (
    !("answer" in value) ||
    typeof value.answer !== "string" ||
    !("sources" in value) ||
    !Array.isArray(value.sources)
  ) {
    return false;
  }

  return value.sources.every(
    (item: unknown) =>
      typeof item === "object" &&
      item !== null &&
      "number" in item &&
      typeof item.number === "number" &&
      "source" in item &&
      typeof item.source === "string" &&
      "page" in item &&
      typeof item.page === "number",
  );
}

function getErrorMessage(value: unknown): string {
  if (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "string"
  ) {
    return value.detail;
  }

  return "The request failed. Please check your question and try again.";
}

export default function Chat() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedQuestion = question.trim();

    if (!trimmedQuestion || isLoading) {
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmedQuestion }),
      });

      const data: unknown = await response.json();

      if (!response.ok) {
        throw new Error(getErrorMessage(data));
      }

      if (!isChatResponse(data)) {
        throw new Error("The server returned an unexpected response.");
      }

      setResult(data);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Unable to send your question. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="space-y-6">
      <form onSubmit={handleSubmit} className="space-y-4">
        <label htmlFor="question" className="block text-lg font-medium">
          Your question
        </label>

        <textarea
          id="question"
          name="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What is the parental leave policy?"
          rows={4}
          maxLength={2000}
          required
          disabled={isLoading}
          className="block w-full rounded-lg border border-zinc-400 bg-background p-3 text-foreground focus:outline-2 focus:outline-offset-2 focus:outline-blue-600 disabled:opacity-60"
        />

        <p className="text-sm">
          Each question is answered independently, without conversation history.
        </p>

        <button
          type="submit"
          disabled={isLoading || !question.trim()}
          className="rounded-lg bg-blue-700 px-5 py-3 font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? "Answering…" : "Ask"}
        </button>
      </form>

      {isLoading && (
        <p role="status">Looking for relevant information and preparing an answer…</p>
      )}

      {error && (
        <p role="alert" className="rounded-lg border border-red-500 p-4">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-6">
          <section aria-labelledby="answer-heading">
            <h2 id="answer-heading" className="mb-3 text-xl font-semibold">
              Answer
            </h2>

            <p className="whitespace-pre-wrap leading-7">{result.answer}</p>
          </section>

          {result.sources.length > 0 && (
            <section aria-labelledby="sources-heading">
              <h2 id="sources-heading" className="mb-3 text-xl font-semibold">
                Sources
              </h2>

              <ul className="space-y-2">
                {result.sources.map((source) => (
                  <li key={source.number} className="break-words">
                    [{source.number}] {source.source} — page {source.page}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </section>
  );
}