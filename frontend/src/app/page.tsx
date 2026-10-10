import Chat from "@/components/Chat";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
      <header className="mb-8 space-y-3">
        <h1 className="text-3xl font-bold">Employee HR Assistant</h1>

        <p className="text-lg">
          Ask questions about company policies and get answers based on the
          indexed documents.
        </p>
      </header>

      <Chat />
    </main>
  );
}