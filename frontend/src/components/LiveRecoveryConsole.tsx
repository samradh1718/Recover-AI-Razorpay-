import {
  Activity,
  BellRing,
  BrainCircuit,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  IndianRupee,
  Link2,
  LoaderCircle,
  Play,
  RefreshCcw,
  ShieldCheck,
  TriangleAlert,
  Webhook,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getCaseAuditTimeline,
  type AuditTimelineEvent,
  type CaseAuditTimeline,
} from "../api/auditTimeline";
import type { RecoveryCaseResponse } from "../api/cases";
import {
  getRecoveryCaseDecisions,
  type RecoveryDecisionResponse,
} from "../api/decisions";

import "./LiveRecoveryConsole.css";


type DataState = "loading" | "ready" | "error";

type LiveRecoveryConsoleProps = {
  recoveryCases: RecoveryCaseResponse[];
  caseLoadState: DataState;
  casesError: string;
  onRefreshCases: () => void | Promise<void>;
  onOpenCase: (caseId: string) => void;
};

type PipelineStage = {
  key: string;
  label: string;
  description: string;
  completed: boolean;
  active: boolean;
};


const actionLabels: Record<string, string> = {
  retry_payment: "Retry payment",
  send_payment_link: "Send payment link",
  request_payment_method_update:
    "Request payment method update",
  request_customer_authorization:
    "Request customer authorization",
  human_review: "Human review",
  stop_recovery: "Stop recovery",
};


function readable(value: string): string {
  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase() + word.slice(1),
    )
    .join(" ");
}


function formatMoney(
  value: unknown,
  currency = "INR",
): string {
  const amount = Number(value);

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}


function formatDate(value: string): string {
  const date = new Date(value);

  if (!Number.isFinite(date.getTime())) {
    return "Unknown time";
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}


function actionLabel(value: unknown): string {
  if (typeof value !== "string") {
    return "Waiting for decision";
  }

  return actionLabels[value] ?? readable(value);
}


function detailValue(
  event: AuditTimelineEvent | undefined,
  key: string,
): unknown {
  return event?.details[key];
}


function isSafeHttpsUrl(
  value: unknown,
): value is string {
  if (typeof value !== "string") {
    return false;
  }

  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}


function eventExists(
  events: AuditTimelineEvent[],
  eventType: string,
): boolean {
  return events.some(
    (event) => event.event_type === eventType,
  );
}


export function LiveRecoveryConsole({
  recoveryCases,
  caseLoadState,
  casesError,
  onRefreshCases,
  onOpenCase,
}: LiveRecoveryConsoleProps) {
  const [selectedCaseId, setSelectedCaseId] =
    useState("");

  const [timeline, setTimeline] =
    useState<CaseAuditTimeline | null>(null);

  const [decision, setDecision] =
    useState<RecoveryDecisionResponse | null>(null);

  const [loadState, setLoadState] =
    useState<DataState>("loading");

  const [errorMessage, setErrorMessage] =
    useState("");

  const [followNewest, setFollowNewest] =
    useState(true);

  const [lastUpdatedAt, setLastUpdatedAt] =
    useState<Date | null>(null);

  const refreshCasesRef = useRef(onRefreshCases);

  useEffect(() => {
    refreshCasesRef.current = onRefreshCases;
  }, [onRefreshCases]);

  const newestCaseId = recoveryCases[0]?.id ?? "";

  useEffect(() => {
    if (recoveryCases.length === 0) {
      setSelectedCaseId("");
      return;
    }

    const selectedStillExists = recoveryCases.some(
      (recoveryCase) =>
        recoveryCase.id === selectedCaseId,
    );

    if (
      !selectedStillExists ||
      (followNewest &&
        newestCaseId !== selectedCaseId)
    ) {
      setSelectedCaseId(newestCaseId);
    }
  }, [
    followNewest,
    newestCaseId,
    recoveryCases,
    selectedCaseId,
  ]);

  const selectedCase = useMemo(
    () =>
      recoveryCases.find(
        (recoveryCase) =>
          recoveryCase.id === selectedCaseId,
      ) ?? null,
    [recoveryCases, selectedCaseId],
  );

  const loadEvidence = useCallback(
    async (
      caseId: string,
      signal?: AbortSignal,
      showLoading = false,
    ) => {
      if (!caseId) return;

      if (showLoading) {
        setLoadState("loading");
      }

      setErrorMessage("");

      try {
        const [timelineResult, decisions] =
          await Promise.all([
            getCaseAuditTimeline(caseId, signal),
            getRecoveryCaseDecisions(caseId, signal),
          ]);

        setTimeline(timelineResult);
        setDecision(decisions[0] ?? null);
        setLoadState("ready");
        setLastUpdatedAt(new Date());
      } catch (error: unknown) {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Unable to load recovery evidence",
        );

        setLoadState("error");
      }
    },
    [],
  );

  useEffect(() => {
    if (!selectedCaseId) {
      setTimeline(null);
      setDecision(null);
      return;
    }

    const controller = new AbortController();

    void loadEvidence(
      selectedCaseId,
      controller.signal,
      true,
    );

    const evidenceInterval = window.setInterval(
      () => {
        void loadEvidence(selectedCaseId);
      },
      3000,
    );

    return () => {
      controller.abort();
      window.clearInterval(evidenceInterval);
    };
  }, [loadEvidence, selectedCaseId]);

  useEffect(() => {
    const casesInterval = window.setInterval(() => {
      void refreshCasesRef.current();
    }, 5000);

    return () => window.clearInterval(casesInterval);
  }, []);

  const events = timeline?.events ?? [];

  const failedEvent = events.find(
    (event) =>
      event.event_type === "webhook_received" &&
      event.details.event_type === "payment.failed",
  );

  const linkEvent = events.find(
    (event) =>
      event.event_type === "provider_action_created",
  );

  const notificationEvent = events.find(
    (event) =>
      event.event_type ===
      "customer_notification_requested",
  );

  const confirmedEvent = events.find(
    (event) =>
      event.event_type ===
      "provider_payment_confirmed",
  );

  const recoveredEvent = events.find(
    (event) =>
      event.event_type === "payment_recovered",
  );

  const mlEvent = events.find(
    (event) =>
      event.event_type === "ml_shadow_decision",
  );

  const aiEvent = events.find(
    (event) =>
      event.event_type === "ai_shadow_decision",
  );

  const paymentLink = detailValue(
    linkEvent,
    "provider_action_url",
  );

  const providerActionId = detailValue(
    linkEvent,
    "provider_action_id",
  );

  const notificationChannel = detailValue(
    notificationEvent,
    "notification_channel",
  );

  const notificationStatus = detailValue(
    notificationEvent,
    "notification_status",
  );

  const recoveredAmount =
    detailValue(
      recoveredEvent,
      "recovered_amount_rupees",
    ) ??
    selectedCase?.recovered_amount_rupees ??
    "0";

  const interventionCost =
    detailValue(
      recoveredEvent,
      "intervention_cost_rupees",
    ) ??
    selectedCase?.intervention_cost_rupees ??
    "0";

  const netRecovered =
    detailValue(
      recoveredEvent,
      "net_recovered_rupees",
    ) ??
    (
      Number(recoveredAmount) -
      Number(interventionCost)
    );

  const productionAction =
    decision?.final_action ??
    decision?.recommended_action;

  const pipelineStages: PipelineStage[] = [
    {
      key: "failed",
      label: "Payment failed",
      description: "Signed provider event",
      completed: Boolean(failedEvent),
      active: !failedEvent,
    },
    {
      key: "diagnosed",
      label: "Diagnosed",
      description:
        selectedCase?.failure_category
          ? readable(selectedCase.failure_category)
          : "Failure classification",
      completed: eventExists(events, "case_created"),
      active:
        Boolean(failedEvent) &&
        !eventExists(events, "case_created"),
    },
    {
      key: "decision",
      label: "Decision made",
      description: actionLabel(productionAction),
      completed: eventExists(
        events,
        "production_decision",
      ),
      active:
        eventExists(events, "case_created") &&
        !eventExists(events, "production_decision"),
    },
    {
      key: "executed",
      label: "Action executed",
      description:
        decision?.status === "scheduled"
          ? "Waiting for schedule"
          : actionLabel(productionAction),
      completed: eventExists(events, "action_executed"),
      active:
        eventExists(events, "production_decision") &&
        !eventExists(events, "action_executed"),
    },
    {
      key: "contacted",
      label: "Customer contacted",
      description: notificationEvent
        ? `${readable(
            String(notificationChannel ?? "provider"),
          )} request accepted`
        : "When action requires contact",
      completed: Boolean(notificationEvent),
      active:
        Boolean(linkEvent) &&
        !notificationEvent &&
        !confirmedEvent,
    },
    {
      key: "paid",
      label: "Provider paid",
      description: confirmedEvent
        ? "Razorpay payment confirmed"
        : "Waiting for customer",
      completed: Boolean(confirmedEvent),
      active:
        Boolean(linkEvent) && !confirmedEvent,
    },
    {
      key: "recovered",
      label: "Revenue recovered",
      description: recoveredEvent
        ? formatMoney(
            recoveredAmount,
            selectedCase?.currency,
          )
        : "Awaiting outcome",
      completed: Boolean(recoveredEvent),
      active:
        Boolean(confirmedEvent) && !recoveredEvent,
    },
  ];

  async function handleRefresh() {
    await refreshCasesRef.current();

    if (selectedCaseId) {
      await loadEvidence(
        selectedCaseId,
        undefined,
        true,
      );
    }
  }

  if (
    caseLoadState === "loading" &&
    recoveryCases.length === 0
  ) {
    return (
      <section className="live-console-state">
        <LoaderCircle className="spin" size={24} />
        Loading recovery cases...
      </section>
    );
  }

  if (
    caseLoadState === "error" &&
    recoveryCases.length === 0
  ) {
    return (
      <section className="live-console-state live-console-state--error">
        <TriangleAlert size={22} />
        <div>
          <strong>Recovery console unavailable</strong>
          <p>{casesError}</p>
        </div>
      </section>
    );
  }

  if (recoveryCases.length === 0) {
    return (
      <section className="live-console-state">
        <CircleDashed size={24} />
        No recovery case is available yet.
      </section>
    );
  }

  return (
    <section className="live-console">
      <header className="live-console-header">
        <div>
          <span className="live-console-eyebrow">
            Hackathon live evidence
          </span>

          <h1>Recovery Control Room</h1>

          <p>
            Payment failure se provider-confirmed
            recovery tak complete live journey.
          </p>
        </div>

        <div className="live-console-actions">
          <label>
            <span>Case</span>

            <select
              value={selectedCaseId}
              onChange={(event) => {
                setFollowNewest(false);
                setSelectedCaseId(event.target.value);
              }}
            >
              {recoveryCases.map((recoveryCase) => (
                <option
                  value={recoveryCase.id}
                  key={recoveryCase.id}
                >
                  {recoveryCase.provider_payment_id ??
                    recoveryCase.id}
                  {" · "}
                  {formatMoney(
                    recoveryCase
                      .recoverable_amount_rupees,
                    recoveryCase.currency,
                  )}
                </option>
              ))}
            </select>
          </label>

          <button
            className={
              followNewest
                ? "live-follow-button live-follow-button--active"
                : "live-follow-button"
            }
            type="button"
            onClick={() => {
              setFollowNewest(true);
              setSelectedCaseId(newestCaseId);
            }}
          >
            <Activity size={15} />
            Follow newest
          </button>

          <button
            className="live-refresh-button"
            type="button"
            aria-label="Refresh recovery evidence"
            onClick={() => void handleRefresh()}
          >
            <RefreshCcw
              size={16}
              className={
                loadState === "loading" ? "spin" : ""
              }
            />
          </button>
        </div>
      </header>

      {selectedCase && (
        <>
          <section className="live-case-banner">
            <div>
              <span>Payment</span>
              <strong>
                {selectedCase.provider_payment_id ??
                  "Provider ID unavailable"}
              </strong>
            </div>

            <div>
              <span>Customer</span>
              <strong>
                {selectedCase.provider_customer_id ??
                  "Not provided"}
              </strong>
            </div>

            <div>
              <span>Recoverable</span>
              <strong>
                {formatMoney(
                  selectedCase
                    .recoverable_amount_rupees,
                  selectedCase.currency,
                )}
              </strong>
            </div>

            <div>
              <span>Current state</span>
              <strong className="live-state-value">
                {readable(
                  timeline?.current_state ??
                    selectedCase.current_state,
                )}
              </strong>
            </div>

            <button
              type="button"
              onClick={() => onOpenCase(selectedCase.id)}
            >
              Full decision
              <ExternalLink size={13} />
            </button>
          </section>

          <section className="live-pipeline-card">
            <div className="live-section-heading">
              <div>
                <span>Live pipeline</span>
                <h2>Customer recovery journey</h2>
              </div>

              <small>
                Auto-refresh every 3 seconds
                {lastUpdatedAt
                  ? ` · ${lastUpdatedAt.toLocaleTimeString(
                      "en-IN",
                    )}`
                  : ""}
              </small>
            </div>

            <div className="live-pipeline">
              {pipelineStages.map((stage, index) => (
                <div
                  className={
                    stage.completed
                      ? "live-stage live-stage--completed"
                      : stage.active
                        ? "live-stage live-stage--active"
                        : "live-stage"
                  }
                  key={stage.key}
                >
                  <div className="live-stage-marker">
                    {stage.completed ? (
                      <CheckCircle2 size={17} />
                    ) : stage.active ? (
                      <LoaderCircle
                        className="spin"
                        size={17}
                      />
                    ) : (
                      <CircleDashed size={17} />
                    )}
                  </div>

                  {index <
                    pipelineStages.length - 1 && (
                    <div className="live-stage-line" />
                  )}

                  <strong>{stage.label}</strong>
                  <span>{stage.description}</span>
                </div>
              ))}
            </div>
          </section>

          {loadState === "error" && (
            <div className="live-console-error">
              <TriangleAlert size={17} />
              {errorMessage}
            </div>
          )}

          <section className="live-proof-grid">
            <article className="live-proof-card">
              <div className="live-proof-icon live-proof-icon--failure">
                <Webhook size={19} />
              </div>

              <span>Failure evidence</span>
              <h3>
                {failedEvent
                  ? "Signed webhook processed"
                  : "Waiting for payment failure"}
              </h3>

              <dl>
                <div>
                  <dt>Failure</dt>
                  <dd>
                    {selectedCase.failure_category
                      ? readable(
                          selectedCase.failure_category,
                        )
                      : "Not classified"}
                  </dd>
                </div>

                <div>
                  <dt>Received</dt>
                  <dd>
                    {failedEvent
                      ? formatDate(
                          failedEvent.occurred_at,
                        )
                      : "—"}
                  </dd>
                </div>
              </dl>
            </article>

            <article className="live-proof-card">
              <div className="live-proof-icon live-proof-icon--decision">
                <ShieldCheck size={19} />
              </div>

              <span>Production decision</span>
              <h3>{actionLabel(productionAction)}</h3>

              <dl>
                <div>
                  <dt>Policy</dt>
                  <dd>
                    {decision
                      ? readable(decision.policy_result)
                      : "Pending"}
                  </dd>
                </div>

                <div>
                  <dt>Probability</dt>
                  <dd>
                    {decision
                      ? `${(
                          Number(
                            decision.recovery_probability,
                          ) * 100
                        ).toFixed(0)}%`
                      : "—"}
                  </dd>
                </div>
              </dl>
            </article>

            <article className="live-proof-card">
              <div className="live-proof-icon live-proof-icon--notification">
                <BellRing size={19} />
              </div>

              <span>Customer notification</span>
              <h3>
                {notificationEvent
                  ? "Request accepted"
                  : "Not requested yet"}
              </h3>

              <dl>
                <div>
                  <dt>Channel</dt>
                  <dd>
                    {notificationChannel
                      ? readable(
                          String(notificationChannel),
                        )
                      : "—"}
                  </dd>
                </div>

                <div>
                  <dt>Provider status</dt>
                  <dd>
                    {notificationStatus
                      ? readable(
                          String(notificationStatus),
                        )
                      : "—"}
                  </dd>
                </div>
              </dl>

              <small>
                Inbox arrival is shown separately during
                the live demo.
              </small>
            </article>

            <article className="live-proof-card">
              <div className="live-proof-icon live-proof-icon--provider">
                <Link2 size={19} />
              </div>

              <span>Razorpay execution</span>
              <h3>
                {linkEvent
                  ? confirmedEvent
                    ? "Payment confirmed"
                    : "Payment Link created"
                  : "Waiting for execution"}
              </h3>

              <dl>
                <div>
                  <dt>Payment Link ID</dt>
                  <dd>
                    {providerActionId
                      ? String(providerActionId)
                      : "—"}
                  </dd>
                </div>
              </dl>

              {isSafeHttpsUrl(paymentLink) && (
                <a
                  href={paymentLink}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  Open Razorpay Test Link
                  <ExternalLink size={13} />
                </a>
              )}
            </article>
          </section>

          <section className="live-outcome-grid">
            <article>
              <IndianRupee size={20} />
              <div>
                <span>Gross recovered</span>
                <strong>
                  {formatMoney(
                    recoveredAmount,
                    selectedCase.currency,
                  )}
                </strong>
              </div>
            </article>

            <article>
              <Play size={20} />
              <div>
                <span>Intervention cost</span>
                <strong>
                  {formatMoney(
                    interventionCost,
                    selectedCase.currency,
                  )}
                </strong>
              </div>
            </article>

            <article className="live-outcome-card--net">
              <CheckCircle2 size={20} />
              <div>
                <span>Net recovered</span>
                <strong>
                  {formatMoney(
                    netRecovered,
                    selectedCase.currency,
                  )}
                </strong>
              </div>
            </article>
          </section>

          <section className="live-lower-grid">
            <article className="live-model-card">
              <div className="live-section-heading">
                <div>
                  <span>Decision intelligence</span>
                  <h2>Production vs shadow models</h2>
                </div>

                <BrainCircuit size={20} />
              </div>

              <div className="live-model-row">
                <span>Rules production</span>
                <strong>
                  {actionLabel(productionAction)}
                </strong>
                <small>Execution authority</small>
              </div>

              <div className="live-model-row">
                <span>CatBoost shadow</span>
                <strong>
                  {actionLabel(
                    detailValue(
                      mlEvent,
                      "selected_action",
                    ),
                  )}
                </strong>
                <small>
                  {detailValue(
                    mlEvent,
                    "agrees_with_production",
                  ) === true
                    ? "Agrees with production"
                    : "Independent comparison"}
                </small>
              </div>

              <div className="live-model-row">
                <span>Ollama shadow</span>
                <strong>
                  {actionLabel(
                    detailValue(
                      aiEvent,
                      "recommended_action",
                    ),
                  )}
                </strong>
                <small>
                  {detailValue(
                    aiEvent,
                    "agrees_with_production",
                  ) === true
                    ? "Agrees with production"
                    : "Independent comparison"}
                </small>
              </div>
            </article>

            <article className="live-audit-card">
              <div className="live-section-heading">
                <div>
                  <span>Persisted evidence</span>
                  <h2>Latest audit events</h2>
                </div>

                <strong>{events.length} events</strong>
              </div>

              <div className="live-audit-list">
                {[...events]
                  .reverse()
                  .slice(0, 8)
                  .map((event) => (
                    <div key={event.id}>
                      <CheckCircle2 size={15} />

                      <div>
                        <strong>{event.title}</strong>
                        <span>
                          {formatDate(
                            event.occurred_at,
                          )}
                        </span>
                      </div>

                      <small>
                        {readable(event.source)}
                      </small>
                    </div>
                  ))}
              </div>
            </article>
          </section>
        </>
      )}
    </section>
  );
}