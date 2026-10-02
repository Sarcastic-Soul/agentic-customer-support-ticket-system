import {
  MicrophoneIcon,
  PaperPlaneRightIcon,
  StopIcon,
  TrayIcon,
  UserSwitchIcon,
  WarningCircleIcon,
  XIcon,
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";
import { type AgentProgress, type ChatMessage, useWebChat } from "../../hooks/useWebChat";
import { cx } from "../../lib/cx";
import { fetchCurrentMessages, type CustomerSession } from "../../lib/customer";
import { TicketList } from "./TicketList";

const STATUS_LABEL: Record<string, string> = {
  connecting: "Connecting",
  open: "Online",
  closed: "Reconnecting",
};

const SPRING = { type: "spring", bounce: 0, duration: 0.3 } as const;

/** Loads the customer's open conversation over REST first, then hands it
 * to the live WebSocket view so a refresh doesn't start a blank chat. */
export function ChatWindow({ customer, onSwitchUser }: { customer: CustomerSession; onSwitchUser: () => void }) {
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
      <div className="flex h-dvh items-center justify-center bg-paper text-sm text-ink-3" aria-busy="true">
        Loading your conversation…
      </div>
    );
  }

  return <ConnectedChat customer={customer} onSwitchUser={onSwitchUser} history={history} />;
}

function ConnectedChat({
  customer,
  onSwitchUser,
  history,
}: {
  customer: CustomerSession;
  onSwitchUser: () => void;
  history: ChatMessage[];
}) {
  const { messages, status, progress, sendMessage, sendVoiceNote } = useWebChat(customer.email, history);
  const [draft, setDraft] = useState("");
  const [showTickets, setShowTickets] = useState(false);
  const recorder = useVoiceRecorder(sendVoiceNote);
  const endRef = useRef<HTMLDivElement>(null);
  const historyCount = useRef(history.length);

  // Keep the newest message in view. Instant on first paint (restored
  // history), smooth after that.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: messages.length > historyCount.current ? "smooth" : "auto" });
  }, [messages.length]);

  const waitingForReply = messages.length > 0 && messages[messages.length - 1].role === "customer";
  const online = status === "open";
  const working = (waitingForReply || progress !== null) && online;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    sendMessage(draft);
    setDraft("");
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-6xl min-w-0 bg-paper xl:border-x xl:border-rule">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-rule bg-surface md:flex lg:w-80">
        <div className="border-b border-rule px-4 py-4">
          <h2 className="font-display text-base font-semibold">Your tickets</h2>
          <p className="mt-0.5 truncate text-xs text-ink-3">{customer.email}</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <TicketList customerId={customer.customerId} />
        </div>
        <button
          type="button"
          onClick={onSwitchUser}
          className="flex items-center gap-2 border-t border-rule px-4 py-3 text-sm text-ink-3 transition-colors hover:bg-paper hover:text-ink"
        >
          <UserSwitchIcon size={16} aria-hidden />
          Not you? Switch account
        </button>
      </aside>

      <div className="flex h-dvh min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-rule bg-surface px-4 py-3">
          <div className="min-w-0">
            <h1 className="font-display text-base leading-tight font-semibold">Support</h1>
            <p className="flex items-center gap-1.5 text-xs text-ink-3" aria-live="polite">
              <span
                aria-hidden
                className={cx("size-1.5 rounded-full", online ? "bg-moss" : "pulse-dot bg-ochre")}
              />
              {STATUS_LABEL[status]}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1 md:hidden">
            <button
              type="button"
              onClick={() => setShowTickets((v) => !v)}
              aria-expanded={showTickets}
              className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm text-ink-2 hover:bg-sunk"
            >
              {showTickets ? <XIcon size={16} aria-hidden /> : <TrayIcon size={16} aria-hidden />}
              My tickets
            </button>
            <button
              type="button"
              onClick={onSwitchUser}
              aria-label="Not you? Switch account"
              className="inline-flex size-9 items-center justify-center rounded-md text-ink-3 hover:bg-sunk hover:text-ink"
            >
              <UserSwitchIcon size={18} aria-hidden />
            </button>
          </div>
        </header>

        <AnimatePresence initial={false}>
          {showTickets && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={SPRING}
              className="overflow-hidden border-b border-rule bg-surface md:hidden"
            >
              <div className="max-h-64 overflow-y-auto">
                <TicketList customerId={customer.customerId} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <main className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6" aria-live="polite" aria-label="Conversation">
          {messages.length === 0 ? (
            <div className="mx-auto mt-6 max-w-md">
              <p className="font-display text-xl leading-snug font-medium text-ink">What can we help with?</p>
              <p className="mt-2 text-sm text-ink-3">
                Ask about an order, a delivery, a return or a refund. Include the order number if you have it, for
                example ORD-1042. If the assistant can't sort it out, a person from our team takes over.
              </p>
            </div>
          ) : (
            <ol className="mx-auto max-w-2xl space-y-3">
              <AnimatePresence initial={false}>
                {messages.map((m) => (
                  <motion.li
                    key={m.id}
                    layout="position"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={SPRING}
                    className={cx("flex", m.role === "customer" ? "justify-end" : "justify-start")}
                  >
                    <Bubble message={m} />
                  </motion.li>
                ))}
                {working && <WorkingIndicator key="typing" progress={progress} />}
              </AnimatePresence>
            </ol>
          )}
          <div ref={endRef} />
        </main>

        {recorder.error && (
          <p role="alert" className="flex items-center gap-2 border-t border-rule bg-accent-soft px-4 py-2 text-sm text-accent-strong">
            <WarningCircleIcon size={16} aria-hidden className="shrink-0" />
            {recorder.error === "microphone access denied or unavailable"
              ? "Microphone blocked or not found. Allow microphone access in your browser, or type instead."
              : "Could not send the voice note. Try again or type your message."}
          </p>
        )}

        <form
          onSubmit={handleSubmit}
          className="border-t border-rule bg-surface px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4"
        >
          <div className="mx-auto flex max-w-2xl items-end gap-2">
            <label htmlFor="chat-input" className="sr-only">
              Message
            </label>
            <input
              id="chat-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={recorder.status === "recording" ? "Recording… tap stop when done" : "Type a message"}
              disabled={recorder.status === "recording"}
              autoComplete="off"
              className="h-11 min-w-0 flex-1 rounded-md border border-rule-strong bg-paper px-3.5 text-[15px] text-ink placeholder:text-ink-4 hover:border-ink-4 focus:border-ink focus:outline-none disabled:bg-sunk"
            />
            <button
              type="button"
              disabled={!online || recorder.status === "processing"}
              onClick={recorder.status === "recording" ? recorder.stop : recorder.start}
              aria-label={recorder.status === "recording" ? "Stop recording and send" : "Record a voice note"}
              className={cx(
                "inline-flex size-11 shrink-0 items-center justify-center rounded-md transition-colors duration-150 disabled:opacity-40",
                recorder.status === "recording"
                  ? "bg-accent text-on-accent hover:bg-accent-strong"
                  : "border border-rule-strong bg-paper text-ink-2 hover:border-ink-4 hover:text-ink",
              )}
            >
              {recorder.status === "recording" ? (
                <StopIcon size={18} aria-hidden />
              ) : recorder.status === "processing" ? (
                <span className="pulse-dot size-2 rounded-full bg-ink-3" aria-hidden />
              ) : (
                <MicrophoneIcon size={18} aria-hidden />
              )}
            </button>
            <button
              type="submit"
              disabled={!online || !draft.trim()}
              aria-label="Send"
              className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-md bg-ink px-3.5 text-sm font-medium text-paper transition-colors duration-150 hover:bg-ink-2 active:translate-y-px disabled:opacity-40 sm:px-4"
            >
              <PaperPlaneRightIcon size={18} aria-hidden />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Typing dots plus what the agent is doing right now ("Checking your
 * order"). Only the customer-safe label is shown, never which specialist is
 * working. The reply itself arrives whole, after the verify check. */
function WorkingIndicator({ progress }: { progress: AgentProgress | null }) {
  const reduce = useReducedMotion();
  const label = progress?.label ?? "Looking into it";
  return (
    <motion.li
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={reduce ? { duration: 0 } : { delay: progress ? 0 : 0.4, duration: 0.2 }}
      className="flex items-center gap-2 text-xs text-ink-3"
      role="status"
      data-testid="agent-progress"
    >
      <span className="flex gap-1" aria-hidden>
        <span className="pulse-dot size-1.5 rounded-full bg-ink-4" />
        <span className="pulse-dot size-1.5 rounded-full bg-ink-4 [animation-delay:200ms]" />
        <span className="pulse-dot size-1.5 rounded-full bg-ink-4 [animation-delay:400ms]" />
      </span>
      <span className="relative inline-grid">
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={label}
            initial={{ opacity: 0, y: reduce ? 0 : 3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: reduce ? 0 : -3 }}
            transition={reduce ? { duration: 0 } : { duration: 0.16, ease: "easeOut" }}
          >
            {label}
          </motion.span>
        </AnimatePresence>
      </span>
    </motion.li>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === "customer") {
    return (
      <div className="max-w-[85%] rounded-lg rounded-br-[3px] bg-ink px-3.5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap break-words text-paper sm:max-w-[75%]">
        {message.text}
      </div>
    );
  }
  const human = message.role === "human_agent";
  return (
    <div className="max-w-[88%] sm:max-w-[78%]">
      {human && <p className="mb-1 text-xs font-medium text-ochre">Support team</p>}
      <div
        className={cx(
          "rounded-lg rounded-bl-[3px] border bg-surface px-3.5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap break-words text-ink",
          human ? "border-ochre/50" : "border-rule",
        )}
      >
        {message.text}
      </div>
    </div>
  );
}
