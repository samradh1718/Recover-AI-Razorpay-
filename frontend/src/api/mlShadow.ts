export type MLShadowStatus =
  | "pending"
  | "completed"
  | "failed"
  | "invalid";

export type MLActionAlternative = {
  rank: number;
  action: string;
  raw_probability: string;
  calibrated_probability: string;
  expected_recovery_rupees: string;
  estimated_action_cost_rupees: string;
  expected_net_value_rupees: string;
  model_features: Record<
    string,
    string | number | boolean | null
  >;
};

export type MLShadowSummary = {
  total_evaluations: number;
  completed_count: number;
  failed_count: number;
  invalid_count: number;
  pending_count: number;

  agreement_count: number;
  disagreement_count: number;
  agreement_rate_percent: number;

  average_raw_probability: string | null;
  average_calibrated_probability: string | null;
  average_expected_net_value_rupees: string | null;
  average_latency_ms: number | null;

  latest_evaluation_at: string | null;
};

export type MLShadowDecision = {
  id: string;
  recovery_case_id: string;
  production_decision_id: string;

  provider_payment_id: string | null;
  failure_category: string | null;

  model_name: string;
  model_version: string;
  calibration_method: string;
  status: MLShadowStatus;

  production_action: string | null;
  ml_selected_action: string | null;

  raw_probability: string | null;
  calibrated_probability: string | null;

  expected_recovery_rupees: string | null;
  estimated_action_cost_rupees: string | null;
  expected_net_value_rupees: string | null;

  agrees_with_production: boolean | null;
  alternatives: MLActionAlternative[];

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
      `ML Insights request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

export function getMLShadowSummary(
  signal?: AbortSignal,
): Promise<MLShadowSummary> {
  const tenantId = encodeURIComponent(TENANT_ID);

  return request<MLShadowSummary>(
    `/ml-shadow/summary?tenant_id=${tenantId}`,
    signal,
  );
}

export function getMLShadowDecisions(
  signal?: AbortSignal,
): Promise<MLShadowDecision[]> {
  const tenantId = encodeURIComponent(TENANT_ID);

  return request<MLShadowDecision[]>(
    `/ml-shadow/decisions?tenant_id=${tenantId}&offset=0&limit=100`,
    signal,
  );
}