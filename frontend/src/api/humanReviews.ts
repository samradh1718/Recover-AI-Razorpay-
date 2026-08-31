import type {
  RecoveryActionType,
  RecoveryDecisionResponse,
} from "./decisions";
import {
  API_BASE_URL,
  TENANT_ID,
} from "./runtimeConfig";


export type HumanReviewOutcome =
  | "approved"
  | "rejected";


export type HumanReviewApprovedAction =
  | "retry_payment"
  | "send_payment_link"
  | "request_payment_method_update"
  | "request_customer_authorization";


export type HumanReviewSelectedAction =
  | HumanReviewApprovedAction
  | "stop_recovery";


export type HumanReviewResolution = {
  id: string;
  tenant_id: string;
  recovery_case_id: string;
  source_decision_id: string;
  resulting_decision_id: string;

  case_state_version_before: number;
  case_state_version_after: number;

  outcome: HumanReviewOutcome;
  selected_action: RecoveryActionType;

  reviewer_id: string;
  reviewer_name: string;
  reason: string;
  created_at: string;
};


export type ResolveHumanReviewRequest = {
  source_decision_id: string;
  expected_state_version: number;
  outcome: HumanReviewOutcome;
  selected_action: HumanReviewSelectedAction;
  reviewer_id: string;
  reviewer_name: string;
  reason: string;
};


export type ResolveHumanReviewResponse = {
  review: HumanReviewResolution;
  decision: RecoveryDecisionResponse;
  case_state: string;
  action_queued: boolean;
};


async function getErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = (await response.json()) as {
      detail?:
        | string
        | Array<{
            loc?: Array<string | number>;
            msg?: string;
          }>;
    };

    if (typeof body.detail === "string") {
      return body.detail;
    }

    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((item) => item.msg)
        .filter(
          (message): message is string =>
            typeof message === "string",
        );

      if (messages.length > 0) {
        return messages.join(", ");
      }
    }

    return fallback;
  } catch {
    return fallback;
  }
}


export async function getHumanReviews(
  caseId: string,
  signal?: AbortSignal,
): Promise<HumanReviewResolution[]> {
  const query = new URLSearchParams({
    tenant_id: TENANT_ID,
  });

  const response = await fetch(
    `${API_BASE_URL}/cases/${caseId}/human-reviews?${query.toString()}`,
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
        `Human Review request failed: ${response.status}`,
      ),
    );
  }

  return response.json() as Promise<
    HumanReviewResolution[]
  >;
}


export async function resolveHumanReview(
  caseId: string,
  request: ResolveHumanReviewRequest,
): Promise<ResolveHumanReviewResponse> {
  const response = await fetch(
    `${API_BASE_URL}/cases/${caseId}/human-review/resolve`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        source_decision_id:
          request.source_decision_id,
        expected_state_version:
          request.expected_state_version,
        outcome: request.outcome,
        selected_action:
          request.selected_action,
        reviewer_id: request.reviewer_id,
        reviewer_name:
          request.reviewer_name,
        reason: request.reason,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        `Human Review resolution failed: ${response.status}`,
      ),
    );
  }

  return response.json() as Promise<
    ResolveHumanReviewResponse
  >;
}