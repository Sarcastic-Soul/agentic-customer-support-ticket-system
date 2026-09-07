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


export const consoleApi = {
  queue: (skill?: string) =>
    request<EscalationSummary[]>(`/api/console/queue${skill ? `?skill=${skill}` : ""}`),

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
};
