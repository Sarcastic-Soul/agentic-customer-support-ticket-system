import { useCallback, useEffect, useRef, useState } from "react";

export type ChatMessage = {
  id: string;
  role: "customer" | "assistant";
  text: string;
};

type ConnectionStatus = "connecting" | "open" | "closed";

/** Owns the WebSocket connection to /channels/web/ws. Reconnects with a
 * short fixed backoff if the connection drops - good enough for a prototype
 * chat widget, not a general-purpose reconnection library. */
export function useWebChat(sessionId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket;

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(
        `${protocol}://${window.location.host}/channels/web/ws?session_id=${sessionId}`,
      );
      socketRef.current = socket;
      setStatus("connecting");

      socket.onopen = () => setStatus("open");

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data) as { text: string };
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", text: data.text },
        ]);
      };

      socket.onclose = () => {
        setStatus("closed");
        if (!cancelled) setTimeout(connect, 1500);
      };
    }

    connect();
    return () => {
      cancelled = true;
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

  return { messages, status, sendMessage, sendVoiceNote };
}
