import { useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  IndianRupee,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

import type { RecoveryCaseResponse } from "../api/cases";
import {
  evaluateRecoveryCase,
  getRecoveryCaseDecisions,
  type PolicyResult,
  type RecoveryActionType,
  type RecoveryDecisionResponse,
} from "../api/decisions";

import "./DecisionPanel.css";


type DecisionPanelProps = {
  recoveryCase: RecoveryCaseResponse;
  onClose: () => void;
  onCaseUpdated: () => void | Promise<void>;
};

type PanelState = "loading" | "ready" | "error";

const EVALUABLE_STATES = [
  "DETECTED",
  "DIAGNOSED",
  "EVALUATING",
  "READY",
];

const actionLabels: Record<RecoveryActionType, string> = {
  retry_payment: "Retry payment",
  send_payment_link: "Send payment link",
  request_payment_method_update: "Request payment method update",
  request_customer_authorization: "Request customer authorization",
  human_review: "Send to human review",
  stop_recovery: "Stop recovery",
};

const policyLabels: Record<PolicyResult, string> = {
  pending: "Pending",
  approved: "Approved",
  modified: "Modified",
  rejected: "Rejected",
  escalated: "Escalated",
};

function money(value: string, currency = "INR"): string {
  const amount = Number(value);

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function percentage(value: string): string {
  const probability = Number(value);
  return Number.isFinite(probability)
    ? `${(probability * 100).toFixed(0)}%`
    : "—";
}

function readableCode(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function dateTime(value: string | null): string {
  if (!value) return "Not scheduled";

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function DecisionPanel({
  recoveryCase,
  onClose,
  onCaseUpdated,
}: DecisionPanelProps) {
  const [panelState, setPanelState] =
    useState<PanelState>("loading");
  const [decision, setDecision] =
    useState<RecoveryDecisionResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    setPanelState("loading");
    setErrorMessage("");
    setDecision(null);

    getRecoveryCaseDecisions(
      recoveryCase.id,
      controller.signal,
    )
      .then((decisions) => {
        setDecision(decisions[0] ?? null);
        setPanelState("ready");
      })
      .catch((error: unknown) => {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Unable to load decision history",
        );
        setPanelState("error");
      });

    return () => controller.abort();
  }, [recoveryCase.id]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleEscape);
    document.body.classList.add("decision-panel-open");

    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.classList.remove("decision-panel-open");
    };
  }, [onClose]);

  const canEvaluate = EVALUABLE_STATES.includes(
    recoveryCase.current_state,
  );

  async function handleEvaluate() {
    setIsEvaluating(true);
    setErrorMessage("");

    try {
      const createdDecision = await evaluateRecoveryCase(
        recoveryCase.id,
      );
      setDecision(createdDecision);
      setPanelState("ready");
      await onCaseUpdated();
    } catch (error: unknown) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to evaluate this recovery case",
      );
    } finally {
      setIsEvaluating(false);
    }
  }

  const reference =
    recoveryCase.provider_payment_id ??
    recoveryCase.provider_subscription_id ??
    recoveryCase.id;

  return (
    <div
      className="decision-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="decision-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="decision-panel-title"
      >
        <header className="decision-drawer-header">
          <div>
            <span className="decision-eyebrow">Recovery case</span>
            <h2 id="decision-panel-title">Decision review</h2>
            <p>{reference}</p>
          </div>

          <button
            className="decision-close"
            type="button"
            aria-label="Close decision panel"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>

        <div className="decision-case-strip">
          <div>
            <span>Recoverable amount</span>
            <strong>
              {money(
                recoveryCase.recoverable_amount_rupees,
                recoveryCase.currency,
              )}
            </strong>
          </div>

          <div>
            <span>Current state</span>
            <strong>
              {readableCode(recoveryCase.current_state)}
            </strong>
          </div>

          <div>
            <span>Failure</span>
            <strong>
              {recoveryCase.failure_category
                ? readableCode(recoveryCase.failure_category)
                : "Not classified"}
            </strong>
          </div>
        </div>

        <div className="decision-drawer-body">
          {panelState === "loading" && (
            <div className="decision-loading">
              <LoaderCircle className="spin" size={24} />
              <p>Loading decision history...</p>
            </div>
          )}

          {panelState === "error" && (
            <div className="decision-error">
              <AlertCircle size={20} />
              <div>
                <strong>Decision history unavailable</strong>
                <p>{errorMessage}</p>
              </div>
            </div>
          )}

          {panelState === "ready" && !decision && (
            <section className="decision-empty">
              <div className="decision-empty-icon">
                <BrainCircuit size={27} />
              </div>

              <h3>No decision generated yet</h3>
              <p>
                RecoverAI will compare recovery actions by success
                probability, estimated recovery and action cost. Policy
                checks are applied before the final action is selected.
              </p>

              <div className="decision-formula">
                <span>Expected net value</span>
                <strong>
                  (Amount × Probability) − Action cost
                </strong>
              </div>

              {errorMessage && (
                <div className="decision-inline-error">
                  <AlertCircle size={16} />
                  {errorMessage}
                </div>
              )}

              <button
                className="decision-evaluate-button"
                type="button"
                disabled={!canEvaluate || isEvaluating}
                onClick={handleEvaluate}
              >
                {isEvaluating ? (
                  <LoaderCircle className="spin" size={17} />
                ) : (
                  <Sparkles size={17} />
                )}
                {isEvaluating
                  ? "Evaluating case..."
                  : canEvaluate
                    ? "Evaluate case"
                    : "Case cannot be evaluated"}
              </button>
            </section>
          )}

          {panelState === "ready" && decision && (
            <>
              <section className="decision-result-card">
                <div className="decision-result-heading">
                  <div className="decision-result-icon">
                    <BrainCircuit size={22} />
                  </div>

                  <div>
                    <span>Final recovery action</span>
                    <h3>
                      {decision.final_action
                        ? actionLabels[decision.final_action]
                        : "Awaiting policy decision"}
                    </h3>
                  </div>

                  <span
                    className={`policy-badge policy-badge--${decision.policy_result}`}
                  >
                    {decision.policy_result === "approved" && (
                      <CheckCircle2 size={14} />
                    )}
                    {policyLabels[decision.policy_result]}
                  </span>
                </div>

                <div className="decision-metrics">
                  <div>
                    <span>Probability</span>
                    <strong>
                      {percentage(decision.recovery_probability)}
                    </strong>
                  </div>
                  <div>
                    <span>Expected recovery</span>
                    <strong>
                      {money(
                        decision.expected_recovery_rupees,
                        recoveryCase.currency,
                      )}
                    </strong>
                  </div>
                  <div className="decision-net-value">
                    <span>Expected net value</span>
                    <strong>
                      {money(
                        decision.expected_net_value_rupees,
                        recoveryCase.currency,
                      )}
                    </strong>
                  </div>
                </div>
              </section>

              <section className="decision-section">
                <div className="decision-section-title">
                  <ShieldCheck size={17} />
                  <h3>Recommendation and policy</h3>
                </div>

                <div className="decision-action-flow">
                  <div>
                    <span>Recommended</span>
                    <strong>
                      {actionLabels[decision.recommended_action]}
                    </strong>
                  </div>

                  <ArrowRight size={18} />

                  <div>
                    <span>Final</span>
                    <strong>
                      {decision.final_action
                        ? actionLabels[decision.final_action]
                        : "Pending"}
                    </strong>
                  </div>
                </div>

                <p className="decision-explanation">
                  {decision.explanation}
                </p>

                <div className="decision-reasons">
                  {decision.reason_codes.map((reason) => (
                    <span key={reason}>{readableCode(reason)}</span>
                  ))}
                </div>
              </section>

              <section className="decision-section">
                <div className="decision-section-title">
                  <IndianRupee size={17} />
                  <h3>Value calculation</h3>
                </div>

                <div className="decision-calculation-row">
                  <span>Recoverable amount</span>
                  <strong>
                    {money(
                      recoveryCase.recoverable_amount_rupees,
                      recoveryCase.currency,
                    )}
                  </strong>
                </div>
                <div className="decision-calculation-row">
                  <span>Expected recovery</span>
                  <strong>
                    {money(
                      decision.expected_recovery_rupees,
                      recoveryCase.currency,
                    )}
                  </strong>
                </div>
                <div className="decision-calculation-row">
                  <span>Estimated action cost</span>
                  <strong>
                    − {money(
                      decision.estimated_action_cost_rupees,
                      recoveryCase.currency,
                    )}
                  </strong>
                </div>
                <div className="decision-calculation-row decision-calculation-row--total">
                  <span>Expected net value</span>
                  <strong>
                    {money(
                      decision.expected_net_value_rupees,
                      recoveryCase.currency,
                    )}
                  </strong>
                </div>
              </section>

              {decision.alternatives.length > 0 && (
                <section className="decision-section">
                  <div className="decision-section-title">
                    <BrainCircuit size={17} />
                    <h3>Compared alternatives</h3>
                  </div>

                  <div className="decision-alternatives">
                    {decision.alternatives.map((alternative) => (
                      <div key={alternative.action}>
                        <div>
                          <strong>
                            {actionLabels[alternative.action]}
                          </strong>
                          <span>
                            {percentage(alternative.probability)} chance
                          </span>
                        </div>

                        <strong>
                          {money(
                            alternative.expected_net_value_rupees,
                            recoveryCase.currency,
                          )}
                        </strong>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="decision-audit">
                <div>
                  <Clock3 size={15} />
                  <span>
                    {decision.scheduled_for
                      ? `Scheduled ${dateTime(decision.scheduled_for)}`
                      : `Created ${dateTime(decision.created_at)}`}
                  </span>
                </div>

                <span>{decision.model_source}</span>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}