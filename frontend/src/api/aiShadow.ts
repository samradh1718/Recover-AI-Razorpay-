export type AIShadowStatus =
  | "pending"
  | "completed"
  | "failed"
  | "invalid";

export type AIShadowSummary = {
  total_evaluations: number;
  completed_count: number;
  failed_count: number;
  invalid_count: number;
  pending_count: number;
  agreement_count: number;
  disagreement_count: number;
  agreement_rate_percent: number;
  average_latency_ms: number | null;
  latest_evaluation_at: string | null;
};

export type AIShadowDecision = {
  id: string;
  recovery_case_id: string;
  production_decision_id: string;

  provider_payment_id: string | null;
  failure_category: string | null;

  model_name: string;
  prompt_version: string;
  status: AIShadowStatus;

  production_action: string | null;
  ai_recommended_action: string | null;
  agrees_with_production: boolean | null;

  recovery_probability: string | null;
  expected_recovery_rupees: string | null;
  estimated_action_cost_rupees: string | null;
  expected_net_value_rupees: string | null;

  explanation: string | null;
  reason_codes: string[];
  latency_ms: number | null;
  error_message: string | null;

  created_at: string;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000/api/v1";

const TENANT_ID =
  import.meta.env.VITE_TENANT_ID ??
  "11111111-1111-1111-1111-111111111111";

async function request<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
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
      `AI Insights request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

export function getAIShadowSummary(
  signal?: AbortSignal,
): Promise<AIShadowSummary> {
  const tenantId = encodeURIComponent(TENANT_ID);

  return request<AIShadowSummary>(
    `/ai-shadow/summary?tenant_id=${tenantId}`,
    signal,
  );
}

export function getAIShadowDecisions(
  signal?: AbortSignal,
): Promise<AIShadowDecision[]> {
  const tenantId = encodeURIComponent(TENANT_ID);

  return request<AIShadowDecision[]>(
    `/ai-shadow/decisions?tenant_id=${tenantId}&offset=0&limit=100`,
    signal,
  );
}