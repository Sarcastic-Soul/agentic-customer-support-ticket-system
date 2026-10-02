import { request } from "./api";

export type TicketSummary = {
  id: number;
  reference: string;
  channel: string;
  intent: string | null;
  status: string;
  priority: string;
  sentiment: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  assigned_agent: string | null;
};

export type TicketListResponse = { items: TicketSummary[]; total: number };

export type TicketMessage = {
  id: number;
  role: string;
  body: string;
  direction: string;
  delivery_status: string | null;
  created_at: string;
};

export type TicketEventOut = {
  event_type: string;
  actor_type: string;
  from_status: string | null;
  to_status: string | null;
  created_at: string;
};

export type TicketDetail = TicketSummary & {
  ai_turns: number;
  resolution: string | null;
  resolution_summary: string | null;
  first_response_at: string | null;
  messages: TicketMessage[];
  events: TicketEventOut[];
};

export type ToolCallOut = {
  tool_name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  authorized: boolean;
  deny_reason: string | null;
  latency_ms: number | null;
};

export type AgentStepOut = {
  ordinal: number;
  node: string;
  /** Specialist that ran this step: "orders" | "logistics" | "payments" |
   * "knowledge". null/absent for shared nodes (classify, supervisor,
   * verify...). Older runs predate specialists and never set it. */
  agent?: string | null;
  model: string | null;
  output: Record<string, unknown> | null;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  error: string | null;
  tool_calls: ToolCallOut[];
};

export type AgentRunOut = {
  id: number;
  trigger: string;
  outcome: string | null;
  intent: string | null;
  confidence: number | null;
  total_tokens_in: number;
  total_tokens_out: number;
  est_cost_usd: string;
  latency_ms: number | null;
  started_at: string;
  finished_at: string | null;
  steps: AgentStepOut[];
  /** Specialists dispatched this run, in dispatch order. */
  specialists?: string[];
  conflicts?: ConflictOut[];
};

/** One disagreement between specialists and how it was settled. */
export type ConflictOut = {
  kind: "action" | "fact" | "duplicate";
  agents: string[];
  subject: string;
  detail: string;
  resolution: "rule" | "escalated";
  rule: string;
  kept: string | null;
  dropped: string[];
};

export type AgentMetric = {
  agent: string;
  runs: number;
  tool_calls: number;
  denied: number;
  conflicts: number;
};

export type MetricsOverview = {
  total_tickets: number;
  open_tickets: number;
  closed_tickets: number;
  ai_resolution_rate: number | null;
  escalation_rate: number | null;
  avg_first_response_seconds: number | null;
  avg_resolution_seconds: number | null;
  total_est_cost_usd: number;
};

export type ChannelMetric = { channel: string; count: number; ai_resolved: number; escalated: number };
export type IntentMetric = { intent: string; count: number; escalation_rate: number };
export type EscalationMetric = { reason_code: string; count: number };

export type KBDocumentSummary = {
  id: number;
  title: string;
  category: string | null;
  source: string;
  version: number;
  is_active: boolean;
  updated_at: string;
};

export type KBDocumentDetail = KBDocumentSummary & { body: string };

export type KBDocumentCreate = {
  title: string;
  body: string;
  source?: string;
  category?: string | null;
};

export type KBDocumentUpdate = {
  title?: string;
  body?: string;
  category?: string | null;
  is_active?: boolean;
};

export type TicketFilters = {
  status?: string;
  channel?: string;
  intent?: string;
  priority?: string;
  q?: string;
  sort_by?: "created_at" | "updated_at" | "priority" | "status";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
};

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const adminApi = {
  tickets: (filters: TicketFilters = {}) =>
    request<TicketListResponse>(`/api/admin/tickets${qs(filters)}`),

  ticket: (id: number) => request<TicketDetail>(`/api/admin/tickets/${id}`),

  ticketRuns: (id: number) => request<AgentRunOut[]>(`/api/admin/tickets/${id}/runs`),

  metricsOverview: (rangeDays: number) =>
    request<MetricsOverview>(`/api/admin/metrics/overview?range=${rangeDays}`),

  metricsChannels: (rangeDays: number) =>
    request<ChannelMetric[]>(`/api/admin/metrics/channels?range=${rangeDays}`),

  metricsIntents: (rangeDays: number) =>
    request<IntentMetric[]>(`/api/admin/metrics/intents?range=${rangeDays}`),

  metricsEscalations: (rangeDays: number) =>
    request<EscalationMetric[]>(`/api/admin/metrics/escalations?range=${rangeDays}`),

  metricsAgents: (rangeDays: number) =>
    request<AgentMetric[]>(`/api/admin/metrics/agents?range=${rangeDays}`),

  kbList: () => request<KBDocumentSummary[]>(`/api/admin/kb/documents`),

  kbGet: (id: number) => request<KBDocumentDetail>(`/api/admin/kb/documents/${id}`),

  kbCreate: (body: KBDocumentCreate) =>
    request<KBDocumentDetail>(`/api/admin/kb/documents`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  kbUpdate: (id: number, body: KBDocumentUpdate) =>
    request<KBDocumentDetail>(`/api/admin/kb/documents/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
