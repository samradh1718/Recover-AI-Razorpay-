import type { LucideIcon } from "lucide-react";
import {
  AlertCircle,
  BadgeCheck,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Cpu,
  ExternalLink,
  IndianRupee,
  Link2,
  LoaderCircle,
  Lock,
  Play,
  RefreshCcw,
  ShieldCheck,
  Webhook,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getCaseAuditTimeline,
  type AuditTimelineEvent,
  type CaseAuditTimeline as CaseAuditTimelineData,
} from "../api/auditTimeline";


type CaseTimelineProps = {
  caseId: string;
  refreshKey?: number;
};

type LoadState = "loading" | "ready" | "error";


const eventIcons: Record<string, LucideIcon> = {
  webhook_received: Webhook,
  webhook_processed: CheckCircle2,
  case_created: AlertCircle,
  production_decision: ShieldCheck,
  action_scheduled: Clock3,
  action_executed: Play,
  provider_action_created: Link2,
  provider_payment_confirmed: BadgeCheck,
  ml_shadow_decision: Cpu,
  ai_shadow_decision: BrainCircuit,
  payment_recovered: IndianRupee,
  case_closed: Lock,
};


const eventTypeLabels: Record<string, string> = {
  webhook_received: "Webhook Received",
  webhook_processed: "Webhook Processed",
  case_created: "Case Created",
  production_decision: "Production Decision",
  action_scheduled: "Action Scheduled",
  action_executed: "Action Executed",
  provider_action_created: "Payment Link Created",
  provider_payment_confirmed: (
    "Provider Payment Confirmed"
  ),
  ml_shadow_decision: "ML Shadow Decision",
  ai_shadow_decision: "AI Shadow Decision",
  payment_recovered: "Revenue Recovered",
  case_closed: "Case Closed",
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


function eventTypeLabel(eventType: string): string {
  return (
    eventTypeLabels[eventType] ??
    readable(eventType)
  );
}


function cssToken(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "-");
}


function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}


function formatCurrency(value: unknown): string {
  const amount = Number(value);

  if (!Number.isFinite(amount)) return "—";

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(amount);
}


function formatDetailValue(
  key: string,
  value: unknown,
): string {
  if (value === null || value === undefined) {
    return "—";
  }

  if (key.includes("rupees")) {
    return formatCurrency(value);
  }

  if (key.includes("probability")) {
    const probability = Number(value);

    return Number.isFinite(probability)
      ? `${(probability * 100).toFixed(1)}%`
      : String(value);
  }

  if (
    key.endsWith("_at") &&
    typeof value === "string"
  ) {
    return formatDate(value);
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => readable(String(item)))
      .join(", ");
  }

  if (
    typeof value === "object" &&
    value !== null
  ) {
    return JSON.stringify(value);
  }

  const text = String(value);

  if (
    key.includes("action") ||
    key.includes("status") ||
    key === "failure_category" ||
    key === "policy_result" ||
    key === "model_source" ||
    key === "execution_mode" ||
    key === "final_state"
  ) {
    return readable(text);
  }

  return text;
}


function isSafeProviderUrl(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }

  try {
    const url = new URL(value);

    return url.protocol === "https:";
  } catch {
    return false;
  }
}


function DetailValue({
  detailKey,
  value,
}: {
  detailKey: string;
  value: unknown;
}) {
  if (
    detailKey === "provider_action_url" &&
    isSafeProviderUrl(value)
  ) {
    return (
      <a
        className="case-timeline-provider-link"
        href={value}
        target="_blank"
        rel="noreferrer noopener"
      >
        Open Razorpay Test Link
        <ExternalLink size={12} />
      </a>
    );
  }

  return (
    <>
      {formatDetailValue(detailKey, value)}
    </>
  );
}


function TimelineEvent({
  event,
  isLast,
}: {
  event: AuditTimelineEvent;
  isLast: boolean;
}) {
  const Icon =
    eventIcons[event.event_type] ?? Clock3;

  const detailEntries = Object.entries(
    event.details,
  ).filter(([, value]) => value !== null);

  const statusClass = (
    `case-timeline-status ` +
    `case-timeline-status--${cssToken(event.status)}`
  );

  return (
    <li
      className={
        `case-timeline-item ` +
        `case-timeline-item--${event.event_type}`
      }
    >
      <div className="case-timeline-marker">
        <Icon size={15} />
      </div>

      {!isLast && (
        <div className="case-timeline-line" />
      )}

      <article className="case-timeline-content">
        <div className="case-timeline-event-heading">
          <div>
            <strong>{event.title}</strong>

            <span>
              {formatDate(event.occurred_at)}
            </span>
          </div>

          <span className="case-timeline-source">
            {readable(event.source)}
          </span>
        </div>

        <p>{event.description}</p>

        <div className="case-timeline-status-row">
          <span className={statusClass}>
            {readable(event.status)}
          </span>

          <small>
            {eventTypeLabel(event.event_type)}
          </small>
        </div>

        {detailEntries.length > 0 && (
          <details className="case-timeline-details">
            <summary>View event details</summary>

            <div>
              {detailEntries.map(([key, value]) => (
                <dl key={key}>
                  <dt>{readable(key)}</dt>

                  <dd>
                    <DetailValue
                      detailKey={key}
                      value={value}
                    />
                  </dd>
                </dl>
              ))}
            </div>
          </details>
        )}
      </article>
    </li>
  );
}


export function CaseTimeline({
  caseId,
  refreshKey = 0,
}: CaseTimelineProps) {
  const [timeline, setTimeline] =
    useState<CaseAuditTimelineData | null>(null);

  const [loadState, setLoadState] =
    useState<LoadState>("loading");

  const [errorMessage, setErrorMessage] =
    useState("");


  const loadTimeline = useCallback(
    async (signal?: AbortSignal) => {
      setLoadState("loading");
      setErrorMessage("");

      try {
        const result = await getCaseAuditTimeline(
          caseId,
          signal,
        );

        setTimeline(result);
        setLoadState("ready");
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
            : "Unable to load audit timeline",
        );

        setLoadState("error");
      }
    },
    [caseId],
  );


  useEffect(() => {
    const controller = new AbortController();

    void loadTimeline(controller.signal);

    return () => controller.abort();
  }, [loadTimeline, refreshKey]);


  return (
    <section className="case-timeline-section">
      <div className="case-timeline-header">
        <div>
          <span>Audit trail</span>
          <h3>Recovery journey</h3>
        </div>

        <div>
          {timeline && (
            <span className="case-timeline-count">
              {timeline.total_events} events
            </span>
          )}

          <button
            type="button"
            aria-label="Refresh audit timeline"
            disabled={loadState === "loading"}
            onClick={() => void loadTimeline()}
          >
            <RefreshCcw
              size={14}
              className={
                loadState === "loading"
                  ? "spin"
                  : ""
              }
            />
          </button>
        </div>
      </div>

      {loadState === "loading" && (
        <div className="case-timeline-loading">
          <LoaderCircle className="spin" size={20} />
          Loading audit trail...
        </div>
      )}

      {loadState === "error" && (
        <div className="case-timeline-error">
          <AlertCircle size={17} />

          <div>
            <strong>Audit trail unavailable</strong>
            <p>{errorMessage}</p>
          </div>
        </div>
      )}

      {loadState === "ready" &&
        timeline &&
        timeline.events.length === 0 && (
          <div className="case-timeline-empty">
            No audit events recorded.
          </div>
        )}

      {loadState === "ready" &&
        timeline &&
        timeline.events.length > 0 && (
          <ol className="case-timeline-list">
            {timeline.events.map((event, index) => (
              <TimelineEvent
                event={event}
                isLast={
                  index ===
                  timeline.events.length - 1
                }
                key={event.id}
              />
            ))}
          </ol>
        )}
    </section>
  );
}