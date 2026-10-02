import { useCallback, useEffect, useRef, useState } from "react";

export type ChatMessage = {
  id: string;
  role: "customer" | "assistant" | "human_agent";
  text: string;
};

type ConnectionStatus = "connecting" | "open" | "closed";

/** What the agent is doing right now, sent by the worker while it works.
 * The reply itself is never streamed token by token: it is only sent after
 * the verify groundedness check, so it arrives whole in one "reply" frame. */
export type AgentProgress = {
  stage: string;
  agent: string | null;
  label: string;
};

type Frame =
  | { type: "progress"; stage: string; agent?: string | null; label: string }
  | { type?: "reply"; text: string };

// A run that goes quiet this long has stalled or been handed to a person -
// stop showing a stale "Checking your order".
const PROGRESS_IDLE_MS = 30_000;

/** Owns the WebSocket connection to /channels/web/ws. Reconnects with a
 * short fixed backoff if the connection drops - good enough for a prototype
 * chat widget, not a general-purpose reconnection library.
 *
 * `history` seeds the initial message list (fetched separately over REST,
 * since the WS itself only forwards new replies going forward, never past
 * ones) - only read once, on mount, not re-applied on change. */
export function useWebChat(sessionId: string, history: ChatMessage[] = []) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => history);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [progress, setProgress] = useState<AgentProgress | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    function clearIdle() {
      if (idleTimer.current) clearTimeout(idleTimer.current);
      idleTimer.current = null;
    }

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(
        `${protocol}://${window.location.host}/channels/web/ws?session_id=${encodeURIComponent(sessionId)}`,
      );
      socketRef.current = socket;
      setStatus("connecting");
      clearIdle();
      setProgress(null);

      socket.onopen = () => setStatus("open");

      socket.onmessage = (event) => {
        let frame: Frame;
        try {
          frame = JSON.parse(event.data) as Frame;
        } catch {
          return;
        }
        if (frame.type === "progress") {
          setProgress({ stage: frame.stage, agent: frame.agent ?? null, label: frame.label });
          clearIdle();
          idleTimer.current = setTimeout(() => setProgress(null), PROGRESS_IDLE_MS);
          return;
        }
        // Frames with no "type" are the pre-progress reply shape.
        if (typeof frame.text !== "string") return;
        clearIdle();
        setProgress(null);
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", text: frame.text },
        ]);
      };

      socket.onclose = () => {
        // A socket closed by cleanup (StrictMode remount, session change) can
        // report its close after the new socket has opened - ignore it.
        if (cancelled) return;
        setStatus("closed");
        setTimeout(() => {
          if (!cancelled) connect();
        }, 1500);
      };
    }

    connect();
    return () => {
      cancelled = true;
      clearIdle();
      socketRef.current?.close();
    };
  }, [sessionId]);

  const sendMessage = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed || socketRef.current?.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "customer", text: trimmed }]);
    socketRef.current.send(JSON.stringify({ text: trimmed }));
  }, []);

  // The reply to a voice note arrives the same way a typed message's reply
  // does - over the WS pub/sub channel already wired above - so this only
  // needs to upload the recording and show its transcript optimistically.
  const sendVoiceNote = useCallback(
    async (blob: Blob) => {
      const form = new FormData();
      form.append("session_id", sessionId);
      form.append("file", blob, "voice-note.webm");

      const response = await fetch("/channels/voice/upload", { method: "POST", body: form });
      if (!response.ok) {
        throw new Error(`voice upload failed (${response.status})`);
      }
      const data = (await response.json()) as { transcript: string };
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "customer", text: data.transcript },
      ]);
    },
    [sessionId],
  );

  return { messages, status, progress, sendMessage, sendVoiceNote };
}
