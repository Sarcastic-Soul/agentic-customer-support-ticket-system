import { request } from "./api";

export type EscalationSummary = {
  id: number;
  ticket_id: number;
  ticket_reference: string;
  reason_code: string;
  priority: string;
  status: string;
  required_skill: string | null;
  created_at: string;
};

export type HandoffPacket = {
  ticket_reference: string;
  escalation_reason: string;
  reason_detail: string;
  priority: string;
  required_skill: string | null;
  customer: { id: number; name: string | null; tier: string; verified: boolean };
  summary: string;
  timeline: { who: string; what: string }[];
  entities: Record<string, string>;
  suggested_reply: string | null;
  ai_confidence: number | null;
  intent: string | null;
  generated_at: string;
};

export type EscalationDetail = EscalationSummary & {
  handoff_packet: HandoffPacket;
  claimed_by: number | null;
  human_note: string | null;
};

export type TranscriptMessage = {
  id: number;
  role: string;
  body: string;
  direction: string;
  created_at: string;
};

/** A refund the AI was not allowed to approve itself, waiting for a person.
 * Amounts are decimals serialised as strings. */
export type ApprovalOut = {
  refund_id: number;
  ticket_id: number | null;
  ticket_reference: string | null;
  customer_name: string | null;
  order_number: string | null;
  txn_ref: string;
  payment_amount: string;
  amount: string;
  reason: string | null;
  requested_by_type: string;
  created_at: string;
};

/** Query key shared by the approvals page and the nav badge. */
export const APPROVALS_KEY = ["console", "approvals"] as const;

export const consoleApi = {
  queue: (opts?: { skill?: string; mine?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.skill) params.set("skill", opts.skill);
    if (opts?.mine) params.set("mine", "true");
    const qs = params.toString();
    return request<EscalationSummary[]>(`/api/console/queue${qs ? `?${qs}` : ""}`);
  },

  detail: (id: number) => request<EscalationDetail>(`/api/console/escalations/${id}`),

  transcript: (id: number) =>
    request<TranscriptMessage[]>(`/api/console/escalations/${id}/transcript`),

  claim: (id: number) =>
    request<{ claimed: boolean; escalation: EscalationDetail | null }>(
      `/api/console/escalations/${id}/claim`,
      { method: "POST" },
    ),

  reply: (id: number, text: string) =>
    request<{ sent: boolean }>(`/api/console/escalations/${id}/reply`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  returnToAI: (id: number, note: string) =>
    request<{ resumed: boolean; outcome: string | null }>(
      `/api/console/escalations/${id}/return-to-ai`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  resolve: (id: number, summary: string) =>
    request<{ resolved: boolean }>(`/api/console/escalations/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ summary }),
    }),

  approvals: () => request<ApprovalOut[]>("/api/console/approvals"),

  approve: (refundId: number) =>
    request<{ approved: boolean }>(`/api/console/approvals/${refundId}/approve`, { method: "POST" }),

  reject: (refundId: number, note: string) =>
    request<{ rejected: boolean }>(`/api/console/approvals/${refundId}/reject`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
};
