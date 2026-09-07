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
  resolved_at: string | null;
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
