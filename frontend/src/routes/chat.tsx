import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useVoiceRecorder } from "../hooks/useVoiceRecorder";
import { type ChatMessage, useWebChat } from "../hooks/useWebChat";
import {
  clearCustomer,
  fetchCurrentMessages,
  fetchMyTickets,
  getStoredCustomer,
  loginByEmail,
  storeCustomer,
  type CustomerSession,
  type CustomerTicket,
} from "../lib/customer";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

const STATUS_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  open: "Connected",
  closed: "Reconnecting…",
};

function ChatPage() {
  const [customer, setCustomer] = useState<CustomerSession | null>(getStoredCustomer);

  if (!customer) {
    return <EmailGate onLogin={setCustomer} />;
  }

  return (
    <ChatWindow
      customer={customer}
      onSwitchUser={() => {
        clearCustomer();
        setCustomer(null);
      }}
    />
  );
}

function EmailGate({ onLogin }: { onLogin: (customer: CustomerSession) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed || busy) return;

    setBusy(true);
    setError(null);
    try {
      const session = await loginByEmail(trimmed);
      storeCustomer(session);
      onLogin(session);
    } catch {
      setError("Could not sign in. Check the email and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-dvh max-w-sm flex-col items-center justify-center gap-4 bg-neutral-50 px-6">
      <h1 className="text-lg font-semibold text-neutral-900">Support Chat</h1>
      <p className="text-center text-sm text-neutral-500">
        Enter your email to start a new chat or continue a past conversation. New here? Just
        type your email — an account is created automatically.
      </p>
      <form onSubmit={handleSubmit} className="flex w-full flex-col gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="rounded-full border border-neutral-300 px-4 py-2 text-sm outline-none focus:border-neutral-500"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Signing in…" : "Continue"}
        </button>
      </form>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

function ChatWindow({
  customer,
  onSwitchUser,
}: {
  customer: CustomerSession;
  onSwitchUser: () => void;
}) {
  const [history, setHistory] = useState<ChatMessage[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCurrentMessages(customer.customerId)
      .then((data) => {
        if (cancelled) return;
        setHistory(data.map((m) => ({ id: String(m.id), role: m.role, text: m.text })));
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      });
    return () => {
      cancelled = true;
    };
  }, [customer.customerId]);

  if (history === null) {
    return (
      <div className="flex h-dvh items-center justify-center bg-neutral-50 text-sm text-neutral-400">
        Loading…
      </div>
    );
  }

  return <ChatWindowConnected customer={customer} onSwitchUser={onSwitchUser} history={history} />;
}

function ChatWindowConnected({
  customer,
  onSwitchUser,
  history,
}: {
  customer: CustomerSession;
  onSwitchUser: () => void;
  history: ChatMessage[];
}) {
  const { messages, status, sendMessage, sendVoiceNote } = useWebChat(customer.email, history);
  const [draft, setDraft] = useState("");
  const [showTickets, setShowTickets] = useState(false);
  const recorder = useVoiceRecorder(sendVoiceNote);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(draft);
    setDraft("");
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-6xl min-w-0 bg-neutral-50">
      {/* Permanent sidebar from tablet width up; a toggled panel below that
       * (see the mobile-only button+panel further down) covers narrow
       * screens where there isn't room for both columns at once. */}
      <aside className="hidden w-72 shrink-0 flex-col overflow-y-auto border-r border-neutral-200 bg-white md:flex lg:w-80">
        <TicketSidebar customerId={customer.customerId} />
      </aside>

      <div className="flex h-dvh min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-white px-4 py-3">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-neutral-900">Support Chat</h1>
            <p className="truncate text-xs text-neutral-400">{customer.email}</p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setShowTickets((v) => !v)}
              className="text-xs font-medium text-neutral-600 underline md:hidden"
            >
              My tickets
            </button>
            <button
              type="button"
              onClick={onSwitchUser}
              className="text-xs font-medium text-neutral-400 underline"
            >
              Not you?
            </button>
            <span className="flex items-center gap-1.5 text-xs text-neutral-500">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  status === "open" ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
              {STATUS_LABEL[status]}
            </span>
          </div>
        </header>

        {showTickets && (
          <div className="border-b border-neutral-200 bg-white md:hidden">
            <TicketSidebar customerId={customer.customerId} compact />
          </div>
        )}

        <main className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-4">
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

        <form
          onSubmit={handleSubmit}
          className="flex gap-2 border-t border-neutral-200 bg-white p-3"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a message…"
            className="min-w-0 flex-1 rounded-full border border-neutral-300 px-4 py-2 text-sm outline-none focus:border-neutral-500"
          />
          <button
            type="button"
            disabled={status !== "open" || recorder.status === "processing"}
            onClick={recorder.status === "recording" ? recorder.stop : recorder.start}
            aria-label={recorder.status === "recording" ? "Stop recording" : "Record a voice note"}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium disabled:opacity-40 ${
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
            className="shrink-0 rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

function TicketSidebar({
  customerId,
  compact = false,
}: {
  customerId: number;
  compact?: boolean;
}) {
  const [tickets, setTickets] = useState<CustomerTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMyTickets(customerId)
      .then((data) => {
        if (!cancelled) setTickets(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load past tickets.");
      });
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  return (
    <div className={compact ? "max-h-48 overflow-y-auto px-4 py-2" : "flex-1 px-3 py-3"}>
      {!compact && (
        <h2 className="px-1 pb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
          My tickets
        </h2>
      )}
      {error && <p className="px-1 text-xs text-red-600">{error}</p>}
      {!error && tickets === null && <p className="px-1 text-xs text-neutral-400">Loading…</p>}
      {!error && tickets?.length === 0 && (
        <p className="px-1 text-xs text-neutral-400">No past tickets yet.</p>
      )}
      <ul className="space-y-1">
        {tickets?.map((t) => (
          <li
            key={t.id}
            className="rounded-lg border border-neutral-100 px-3 py-2 text-xs hover:bg-neutral-50"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-neutral-700">{t.reference}</span>
              <span className="shrink-0 rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-600">
                {t.status}
              </span>
            </div>
            <div className="mt-0.5 truncate text-neutral-400">{t.intent ?? "—"}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
