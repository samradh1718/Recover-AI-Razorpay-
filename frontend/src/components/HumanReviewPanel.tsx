import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getRecoveryCaseDecisions,
  type RecoveryActionType,
  type RecoveryDecisionResponse,
} from "../api/decisions";
import {
  getHumanReviews,
  resolveHumanReview,
  type HumanReviewApprovedAction,
  type HumanReviewResolution,
  type HumanReviewOutcome,
  type ResolveHumanReviewResponse,
} from "../api/humanReviews";


type HumanReviewPanelProps = {
  caseId: string;
  caseState: string;
  caseStateVersion: number;
  onResolved: () => void | Promise<void>;
};


const APPROVABLE_ACTIONS: ReadonlySet<
  RecoveryActionType
> = new Set([
  "retry_payment",
  "send_payment_link",
  "request_payment_method_update",
  "request_customer_authorization",
]);


const ACTION_LABELS: Record<
  HumanReviewApprovedAction,
  string
> = {
  retry_payment: "Retry payment",
  send_payment_link: "Send payment link",
  request_payment_method_update:
    "Request payment method update",
  request_customer_authorization:
    "Request customer authorization",
};


function isApprovedAction(
  action: RecoveryActionType,
): action is HumanReviewApprovedAction {
  return APPROVABLE_ACTIONS.has(action);
}


function formatAction(
  action: RecoveryActionType | null,
): string {
  if (
    action !== null
    && isApprovedAction(action)
  ) {
    return ACTION_LABELS[action];
  }

  if (action === "human_review") {
    return "Human Review";
  }

  if (action === "stop_recovery") {
    return "Stop recovery";
  }

  return "Unknown action";
}


function findSourceDecision(
  decisions: RecoveryDecisionResponse[],
): RecoveryDecisionResponse | null {
  return (
    [...decisions]
      .reverse()
      .find(
        (decision) =>
          decision.final_action
            === "human_review"
          && decision.policy_result
            === "escalated"
          && decision.status
            === "proposed",
      )
    ?? null
  );
}


function availableReviewActions(
  decision: RecoveryDecisionResponse | null,
): HumanReviewApprovedAction[] {
  if (decision === null) {
    return [];
  }

  const actions: RecoveryActionType[] = [
    decision.recommended_action,
    ...decision.alternatives.map(
      (alternative) =>
        alternative.action,
    ),
  ];

  return Array.from(
    new Set(actions),
  ).filter(isApprovedAction);
}


export function HumanReviewPanel({
  caseId,
  caseState,
  caseStateVersion,
  onResolved,
}: HumanReviewPanelProps) {
  const [
    sourceDecision,
    setSourceDecision,
  ] = useState<
    RecoveryDecisionResponse | null
  >(null);

  const [
    existingReview,
    setExistingReview,
  ] = useState<
    HumanReviewResolution | null
  >(null);

  const [
    selectedAction,
    setSelectedAction,
  ] = useState<
    HumanReviewApprovedAction | ""
  >("");

  const [
    reviewerId,
    setReviewerId,
  ] = useState("reviewer_samradh");

  const [
    reviewerName,
    setReviewerName,
  ] = useState("Samradh Dubey");

  const [
    reason,
    setReason,
  ] = useState("");

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    submitting,
    setSubmitting,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);

  const [
    resolution,
    setResolution,
  ] = useState<
    ResolveHumanReviewResponse | null
  >(null);


  const actions = useMemo(
    () =>
      availableReviewActions(
        sourceDecision,
      ),
    [sourceDecision],
  );


  useEffect(() => {
    if (
      caseState !== "HUMAN_REVIEW"
      || !caseId
    ) {
      return;
    }

    const controller = (
      new AbortController()
    );

    async function loadReviewContext() {
      setLoading(true);
      setError(null);
      setResolution(null);
      setExistingReview(null);

      try {
        const [
          decisions,
          reviews,
        ] = await Promise.all([
          getRecoveryCaseDecisions(
            caseId,
            controller.signal,
          ),
          getHumanReviews(
            caseId,
            controller.signal,
          ),
        ]);

        const decision = (
          findSourceDecision(decisions)
        );

        setSourceDecision(decision);

        if (decision === null) {
          setError(
            "No unresolved Human Review decision was found for this case.",
          );

          return;
        }

        const completedReview = (
          reviews.find(
            (review) =>
              review.source_decision_id
              === decision.id,
          )
          ?? null
        );

        setExistingReview(
          completedReview,
        );
      } catch (loadError) {
        if (
          loadError instanceof DOMException
          && loadError.name
            === "AbortError"
        ) {
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load Human Review context.",
        );
      } finally {
        if (
          !controller.signal.aborted
        ) {
          setLoading(false);
        }
      }
    }

    void loadReviewContext();

    return () => {
      controller.abort();
    };
  }, [
    caseId,
    caseState,
  ]);


  useEffect(() => {
    if (actions.length === 0) {
      setSelectedAction("");

      return;
    }

    setSelectedAction(
      (currentAction) =>
        currentAction
        && actions.includes(
          currentAction,
        )
          ? currentAction
          : actions[0],
    );
  }, [actions]);


  if (caseState !== "HUMAN_REVIEW") {
    return null;
  }


  async function submitResolution(
    outcome: HumanReviewOutcome,
  ) {
    if (sourceDecision === null) {
      setError(
        "Human Review source decision is unavailable.",
      );

      return;
    }

    const cleanedReviewerId = (
      reviewerId.trim()
    );

    const cleanedReviewerName = (
      reviewerName.trim()
    );

    const cleanedReason = (
      reason.trim()
    );

    if (!cleanedReviewerId) {
      setError(
        "Reviewer ID is required.",
      );

      return;
    }

    if (!cleanedReviewerName) {
      setError(
        "Reviewer name is required.",
      );

      return;
    }

    if (cleanedReason.length < 10) {
      setError(
        "Enter a clear review reason of at least 10 characters.",
      );

      return;
    }

    if (
      outcome === "approved"
      && !selectedAction
    ) {
      setError(
        "Select the approved recovery action.",
      );

      return;
    }

    if (
      outcome === "rejected"
      && !window.confirm(
        "Reject this recovery case and permanently stop further recovery?",
      )
    ) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const result = (
        await resolveHumanReview(
          caseId,
          {
            source_decision_id:
              sourceDecision.id,
            expected_state_version:
              caseStateVersion,
            outcome,
            selected_action:
              outcome === "approved"
                ? (selectedAction as HumanReviewApprovedAction)
                : "stop_recovery",
            reviewer_id:
              cleanedReviewerId,
            reviewer_name:
              cleanedReviewerName,
            reason: cleanedReason,
          },
        )
      );

      setResolution(result);
      setExistingReview(
        result.review,
      );

      await onResolved();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to resolve Human Review.",
      );
    } finally {
      setSubmitting(false);
    }
  }


  return (
    <section
      className="human-review-panel"
      aria-labelledby="human-review-title"
    >
      <div className="human-review-panel__header">
        <div>
          <p className="human-review-panel__eyebrow">
            POLICY ESCALATION
          </p>

          <h2 id="human-review-title">
            Human Review required
          </h2>

          <p className="human-review-panel__description">
            Automatic execution is paused.
            Review the policy evidence and
            authorize a safe recovery action.
          </p>
        </div>

        <span className="human-review-panel__status">
          Awaiting operator
        </span>
      </div>


      {loading && (
        <div
          className="human-review-panel__message"
          role="status"
        >
          Loading review evidence…
        </div>
      )}


      {!loading && sourceDecision && (
        <>
          <div className="human-review-evidence">
            <div>
              <span>Policy result</span>
              <strong>
                {sourceDecision.policy_result}
              </strong>
            </div>

            <div>
              <span>Recommended action</span>
              <strong>
                {formatAction(
                  sourceDecision
                    .recommended_action,
                )}
              </strong>
            </div>

            <div>
              <span>Recovery probability</span>
              <strong>
                {(
                  Number(
                    sourceDecision
                      .recovery_probability,
                  ) * 100
                ).toFixed(0)}
                %
              </strong>
            </div>

            <div>
              <span>Recoverable value</span>
              <strong>
                ₹
                {Number(
                  sourceDecision
                    .decision_inputs[
                      "recoverable_amount_rupees"
                    ]
                  ?? sourceDecision
                    .expected_recovery_rupees,
                ).toLocaleString(
                  "en-IN",
                  {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  },
                )}
              </strong>
            </div>
          </div>


          <div className="human-review-reasons">
            <span>Escalation reasons</span>

            <div className="human-review-reasons__list">
              {sourceDecision.reason_codes.map(
                (reasonCode) => (
                  <code key={reasonCode}>
                    {reasonCode}
                  </code>
                ),
              )}
            </div>
          </div>


          <div className="human-review-form">
            <label>
              Approved recovery action

              <select
                value={selectedAction}
                onChange={(event) => {
                  setSelectedAction(
                    event.target
                      .value as HumanReviewApprovedAction,
                  );
                }}
                disabled={
                  submitting
                  || existingReview !== null
                }
              >
                {actions.map((action) => (
                  <option
                    key={action}
                    value={action}
                  >
                    {ACTION_LABELS[action]}
                  </option>
                ))}
              </select>
            </label>


            <div className="human-review-form__reviewer">
              <label>
                Reviewer ID

                <input
                  type="text"
                  value={reviewerId}
                  onChange={(event) => {
                    setReviewerId(
                      event.target.value,
                    );
                  }}
                  disabled={
                    submitting
                    || existingReview !== null
                  }
                  autoComplete="off"
                />
              </label>

              <label>
                Reviewer name

                <input
                  type="text"
                  value={reviewerName}
                  onChange={(event) => {
                    setReviewerName(
                      event.target.value,
                    );
                  }}
                  disabled={
                    submitting
                    || existingReview !== null
                  }
                  autoComplete="name"
                />
              </label>
            </div>


            <label>
              Review reason

              <textarea
                value={reason}
                onChange={(event) => {
                  setReason(
                    event.target.value,
                  );
                }}
                placeholder={
                  "Explain the provider evidence and why this action is safe."
                }
                rows={4}
                disabled={
                  submitting
                  || existingReview !== null
                }
              />
            </label>
          </div>


          {error && (
            <div
              className="human-review-panel__error"
              role="alert"
            >
              {error}
            </div>
          )}


          {existingReview && (
            <div
              className="human-review-panel__success"
              role="status"
            >
              <strong>
                Review{" "}
                {existingReview.outcome}
              </strong>

              <span>
                {existingReview.reviewer_name}
                {" selected "}
                {formatAction(
                  existingReview
                    .selected_action,
                )}
                .
              </span>
            </div>
          )}


          {resolution && (
            <div className="human-review-panel__execution">
              Action queued:{" "}
              <strong>
                {resolution.action_queued
                  ? "Yes"
                  : "No"}
              </strong>
            </div>
          )}


          {!existingReview && (
            <div className="human-review-panel__actions">
              <button
                type="button"
                className="human-review-panel__reject"
                onClick={() => {
                  void submitResolution(
                    "rejected",
                  );
                }}
                disabled={submitting}
              >
                Reject and stop
              </button>

              <button
                type="button"
                className="human-review-panel__approve"
                onClick={() => {
                  void submitResolution(
                    "approved",
                  );
                }}
                disabled={
                  submitting
                  || !selectedAction
                }
              >
                {submitting
                  ? "Submitting…"
                  : "Approve action"}
              </button>
            </div>
          )}
        </>
      )}


      {!loading && error && !sourceDecision && (
        <div
          className="human-review-panel__error"
          role="alert"
        >
          {error}
        </div>
      )}
    </section>
  );
}