const STORAGE_KEY = "support-chat-session-id";

/** One chat session per browser, persisted so a page refresh keeps the same
 * conversation thread server-side (external_thread_id == session_id). */
export function getOrCreateSessionId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const created = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, created);
    return created;
  } catch {
    // localStorage unavailable (private mode, etc.) - fall back to an
    // in-memory id that is stable for this page load only.
    return crypto.randomUUID();
  }
}
