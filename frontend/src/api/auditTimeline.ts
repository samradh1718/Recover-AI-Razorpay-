import {
  API_BASE_URL,
  TENANT_ID,
} from "./runtimeConfig";

export type AuditTimelineEvent = {
  id: string;
  event_type: string;
  title: string;
  description: string;
  source: string;
  status: string;
  occurred_at: string;
  details: Record<string, unknown>;
};

export type CaseAuditTimeline = {
  case_id: string;
  tenant_id: string;
  provider_payment_id: string | null;
  current_state: string;
  total_events: number;
  events: AuditTimelineEvent[];
};


export async function getCaseAuditTimeline(
  caseId: string,
  signal?: AbortSignal,
): Promise<CaseAuditTimeline> {
  const tenantId = encodeURIComponent(TENANT_ID);
  const encodedCaseId = encodeURIComponent(caseId);

  const response = await fetch(
    `${API_BASE_URL}/cases/${encodedCaseId}/timeline?tenant_id=${tenantId}`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      `Audit timeline request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<CaseAuditTimeline>;
}