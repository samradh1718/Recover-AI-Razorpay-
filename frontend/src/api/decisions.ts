import { API_BASE_URL } from "./runtimeConfig";
export type RecoveryActionType =
  | "retry_payment"
  | "send_payment_link"
  | "request_payment_method_update"
  | "request_customer_authorization"
  | "human_review"
  | "stop_recovery";

export type PolicyResult =
  | "pending"
  | "approved"
  | "modified"
  | "rejected"
  | "escalated";

export type RecoveryDecisionStatus =
  | "proposed"
  | "scheduled"
  | "executed"
  | "cancelled"
  | "failed";

export type DecisionAlternative = {
  action: RecoveryActionType;
  probability: string;
  expected_recovery_rupees: string;
  estimated_action_cost_rupees: string;
  expected_net_value_rupees: string;
  delay_minutes: number | null;
  reason_code: string;
};

export type RecoveryDecisionResponse = {
  id: string;
  tenant_id: string;
  recovery_case_id: string;
  case_state_version: number;
  recommended_action: RecoveryActionType;
  final_action: RecoveryActionType | null;
  policy_result: PolicyResult;
  status: RecoveryDecisionStatus;
  recovery_probability: string;
  expected_recovery_rupees: string;
  estimated_action_cost_rupees: string;
  expected_net_value_rupees: string;
  explanation: string;
  reason_codes: string[];
  decision_inputs: Record<string, unknown>;
  alternatives: DecisionAlternative[];
  model_source: string;
  scheduled_for: string | null;
  executed_at: string | null;
  created_at: string;
  updated_at: string;
};



async function getErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = (await response.json()) as {
      detail?: string;
    };

    return body.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export async function getRecoveryCaseDecisions(
  caseId: string,
  signal?: AbortSignal,
): Promise<RecoveryDecisionResponse[]> {
  const response = await fetch(
    `${API_BASE_URL}/cases/${caseId}/decisions`,
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
      await getErrorMessage(
        response,
        `Decision request failed: ${response.status}`,
      ),
    );
  }

  return response.json() as Promise<
    RecoveryDecisionResponse[]
  >;
}

export async function evaluateRecoveryCase(
  caseId: string,
): Promise<RecoveryDecisionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/cases/${caseId}/evaluate`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        `Evaluation request failed: ${response.status}`,
      ),
    );
  }

  return response.json() as Promise<RecoveryDecisionResponse>;
}