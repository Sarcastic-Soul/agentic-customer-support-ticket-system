import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useVoiceRecorder } from "../hooks/useVoiceRecorder";
import { useWebChat } from "../hooks/useWebChat";
import { getOrCreateSessionId } from "../lib/session";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

const STATUS_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  open: "Connected",
  closed: "Reconnecting…",
};

function ChatPage() {
  const [sessionId] = useState(getOrCreateSessionId);
  const { messages, status, sendMessage, sendVoiceNote } = useWebChat(sessionId);
  const [draft, setDraft] = useState("");
  const recorder = useVoiceRecorder(sendVoiceNote);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(draft);
    setDraft("");
  }

  return (
    <div className="mx-auto flex h-dvh max-w-lg flex-col bg-neutral-50">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
        <h1 className="text-sm font-semibold text-neutral-900">Support Chat</h1>
        <span className="flex items-center gap-1.5 text-xs text-neutral-500">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              status === "open" ? "bg-emerald-500" : "bg-amber-400"
            }`}
          />
          {STATUS_LABEL[status]}
        </span>
      </header>

      <main className="flex-1 space-y-2 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-neutral-400">
            Send a message to start the conversation.
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex ${m.role === "customer" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                m.role === "customer"
                  ? "bg-neutral-900 text-white"
                  : "bg-white text-neutral-900 shadow-sm ring-1 ring-neutral-200"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
      </main>

      {recorder.error && (
        <p className="border-t border-red-100 bg-red-50 px-4 py-1.5 text-xs text-red-600">
          {recorder.error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-neutral-200 bg-white p-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message…"
          className="flex-1 rounded-full border border-neutral-300 px-4 py-2 text-sm outline-none focus:border-neutral-500"
        />
        <button
          type="button"
          disabled={status !== "open" || recorder.status === "processing"}
          onClick={recorder.status === "recording" ? recorder.stop : recorder.start}
          aria-label={recorder.status === "recording" ? "Stop recording" : "Record a voice note"}
          className={`rounded-full px-4 py-2 text-sm font-medium disabled:opacity-40 ${
            recorder.status === "recording"
              ? "bg-red-600 text-white"
              : "bg-neutral-100 text-neutral-700"
          }`}
        >
          {recorder.status === "recording" ? "● Stop" : recorder.status === "processing" ? "…" : "🎤"}
        </button>
        <button
          type="submit"
          disabled={status !== "open"}
          className="rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}
