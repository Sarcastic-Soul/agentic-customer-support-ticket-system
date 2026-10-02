/** Display helpers shared by every route. Pure functions, no React. */

const STATUS_LABELS: Record<string, string> = {
  new: "New",
  ai_working: "AI working",
  escalated: "Escalated",
  human_working: "With an agent",
  closed: "Closed",
  queued: "Waiting",
  claimed: "Claimed",
  resolved: "Resolved",
  returned_to_ai: "Back with AI",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? humanize(status);
}

/** snake_case codes from the backend -> "Sentence case" for people. */
export function humanize(code: string | null | undefined): string {
  if (!code) return "—";
  const words = code.replace(/[_-]+/g, " ").trim();
  const fixed = words.replace(/\bai\b/gi, "AI").replace(/\bkb\b/gi, "KB");
  return fixed.charAt(0).toUpperCase() + fixed.slice(1);
}

const AGENT_LABELS: Record<string, string> = {
  orders: "Orders",
  logistics: "Logistics",
  payments: "Payments",
  knowledge: "Knowledge",
};

export function agentLabel(agent: string): string {
  return AGENT_LABELS[agent] ?? humanize(agent);
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });

export function relativeTime(iso: string, now = Date.now()): string {
  const diffSec = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(diffSec);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  if (abs < 86400 * 7) return rtf.format(Math.round(diffSec / 86400), "day");
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function clockTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function ms(value: number | null | undefined): string {
  if (value == null) return "—";
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(1)}s`;
}

export function percent(rate: number | null | undefined): string {
  if (rate == null) return "—";
  return `${(rate * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

export function usd(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = Number(value);
  return n < 1 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

const inrFormat = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Order and refund amounts are INR decimals sent as strings. */
export function inr(value: number | string | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? inrFormat.format(n) : String(value);
}

export function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "Something went wrong.";
  const match = /^(\d{3})\b/.exec(error.message);
  if (match?.[1] === "404") return "Not found. It may have been removed.";
  if (match?.[1]?.startsWith("5")) return "The server had a problem. Try again in a moment.";
  if (error.message === "Failed to fetch") return "Could not reach the server. Check that the API is running.";
  const detail = fastApiDetail(error.message);
  if (detail) return detail;
  return error.message;
}

/** request() throws "409 Conflict: {"detail":"refund is already approved"}".
 * Pull out FastAPI's string detail so people see "Refund is already approved." */
function fastApiDetail(message: string): string | null {
  const body = /^\d{3}[^:]*: (.*)$/s.exec(message)?.[1];
  if (!body) return null;
  try {
    const detail: unknown = JSON.parse(body).detail;
    if (typeof detail !== "string" || !detail) return null;
    const text = detail[0].toUpperCase() + detail.slice(1);
    return /[.!?]$/.test(text) ? text : `${text}.`;
  } catch {
    return null;
  }
}
