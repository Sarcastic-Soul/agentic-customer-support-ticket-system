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

  return { messages, status, sendMessage };
}
