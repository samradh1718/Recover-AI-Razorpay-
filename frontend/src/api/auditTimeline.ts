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

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000/api/v1";

const TENANT_ID =
  import.meta.env.VITE_TENANT_ID ??
  "11111111-1111-1111-1111-111111111111";

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