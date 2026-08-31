import {
  API_BASE_URL,
} from "./runtimeConfig";


export type RecoveryCaseState =
  | "DETECTED"
  | "DIAGNOSED"
  | "EVALUATING"
  | "READY"
  | "SCHEDULED"
  | "EXECUTING"
  | "WAITING_FOR_RETRY"
  | "WAITING_FOR_CUSTOMER"
  | "HUMAN_REVIEW"
  | "RECOVERED"
  | "EXHAUSTED"
  | "STOPPED"
  | "EXPIRED";


export type FailureCategory =
  | "temporary_gateway_or_bank"
  | "insufficient_funds"
  | "invalid_or_expired_method"
  | "mandate_or_authorization"
  | "unknown";


export type RecoveryCaseResponse = {
  id: string;
  tenant_id: string;

  // Original Razorpay payment that failed.
  provider_payment_id: string | null;

  // New captured Razorpay payment that
  // successfully recovered the revenue.
  recovered_provider_payment_id:
    | string
    | null;

  provider_subscription_id:
    | string
    | null;

  provider_customer_id:
    | string
    | null;

  currency: string;

  original_amount_rupees: string;
  recoverable_amount_rupees: string;
  recovered_amount_rupees: string;
  intervention_cost_rupees: string;

  failure_category:
    | FailureCategory
    | null;

  current_state: RecoveryCaseState;

  state_version: number;
  attempt_count: number;
  communication_count: number;

  next_action_at: string | null;
  recovery_deadline_at: string;
  recovered_at: string | null;
  closed_at: string | null;

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


export async function getRecoveryCases(
  signal?: AbortSignal,
): Promise<RecoveryCaseResponse[]> {
  const response = await fetch(
    `${API_BASE_URL}/cases?offset=0&limit=100`,
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
        `Cases request failed: ${response.status}`,
      ),
    );
  }

  return response.json() as Promise<
    RecoveryCaseResponse[]
  >;
}