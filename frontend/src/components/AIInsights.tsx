import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  RefreshCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getAIShadowDecisions,
  getAIShadowSummary,
  type AIShadowDecision,
  type AIShadowSummary,
} from "../api/aiShadow";

import "./AIInsights.css";


type LoadState = "loading" | "ready" | "error";

type InsightMetric = {
  label: string;
  value: string;
  description: string;
  icon: LucideIcon;
  tone: "blue" | "green" | "orange" | "purple";
};


function formatAction(value: string | null): string {
  if (!value) return "Not available";

  return value
    .split("_")
    .map(
      (word) =>
        word.charAt(0).toUpperCase() + word.slice(1),
    )
    .join(" ");
}


function formatFailure(value: string | null): string {
  return formatAction(value);
}


function formatLatency(value: number | null): string {
  if (value === null) return "—";

  return `${(value / 1000).toFixed(2)} sec`;
}


function formatProbability(
  value: string | null,
): string {
  if (value === null) return "—";

  return `${(Number(value) * 100).toFixed(0)}%`;
}


function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}


export function AIInsights() {
  const [summary, setSummary] =
    useState<AIShadowSummary | null>(null);

  const [decisions, setDecisions] = useState<
    AIShadowDecision[]
  >([]);

  const [loadState, setLoadState] =
    useState<LoadState>("loading");

  const [errorMessage, setErrorMessage] =
    useState("");


  const loadInsights = useCallback(
    async (signal?: AbortSignal) => {
      setLoadState("loading");
      setErrorMessage("");

      try {
        const [summaryResult, decisionResults] =
          await Promise.all([
            getAIShadowSummary(signal),
            getAIShadowDecisions(signal),
          ]);

        setSummary(summaryResult);
        setDecisions(decisionResults);
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
            : "Unable to load AI insights",
        );

        setLoadState("error");
      }
    },
    [],
  );


  useEffect(() => {
    const controller = new AbortController();

    void loadInsights(controller.signal);

    return () => {
      controller.abort();
    };
  }, [loadInsights]);


  const metrics: InsightMetric[] = [
    {
      label: "AI evaluations",
      value:
        loadState === "loading"
          ? "—"
          : String(summary?.total_evaluations ?? 0),
      description: "Shadow recommendations generated",
      icon: BrainCircuit,
      tone: "blue",
    },
    {
      label: "Agreement rate",
      value:
        loadState === "loading"
          ? "—"
          : `${(
              summary?.agreement_rate_percent ?? 0
            ).toFixed(1)}%`,
      description: "AI agreement with production policy",
      icon: CheckCircle2,
      tone: "green",
    },
    {
      label: "Average latency",
      value:
        loadState === "loading"
          ? "—"
          : formatLatency(
              summary?.average_latency_ms ?? null,
            ),
      description: "Average Ollama response time",
      icon: Clock3,
      tone: "purple",
    },
    {
      label: "Failed evaluations",
      value:
        loadState === "loading"
          ? "—"
          : String(
              (summary?.failed_count ?? 0) +
                (summary?.invalid_count ?? 0),
            ),
      description: "Failed or invalid AI responses",
      icon: AlertTriangle,
      tone: "orange",
    },
  ];


  return (
    <div className="ai-insights">
      <section className="ai-heading">
        <div>
          <div className="ai-heading-label">
            <BrainCircuit size={16} />
            Safe AI evaluation
          </div>

          <h1>AI Insights</h1>

          <p>
            Compare Ollama recommendations with the bounded
            production decision engine.
          </p>
        </div>

        <div className="ai-heading-actions">
          <div className="shadow-mode-badge">
            <ShieldCheck size={16} />
            Shadow mode
          </div>

          <button
            className="ai-refresh-button"
            type="button"
            disabled={loadState === "loading"}
            onClick={() => void loadInsights()}
          >
            <RefreshCcw
              size={16}
              className={
                loadState === "loading"
                  ? "ai-refresh-icon--loading"
                  : ""
              }
            />
            Refresh
          </button>
        </div>
      </section>

      <div className="ai-safety-notice">
        <ShieldCheck size={19} />

        <div>
          <strong>AI cannot execute recovery actions</strong>
          <p>
            Ollama runs independently and only records a
            recommendation for comparison and auditing.
          </p>
        </div>
      </div>

      {loadState === "error" && (
        <div className="ai-error">
          <XCircle size={19} />

          <div>
            <strong>Unable to load AI insights</strong>
            <p>{errorMessage}</p>
          </div>

          <button
            type="button"
            onClick={() => void loadInsights()}
          >
            Try again
          </button>
        </div>
      )}

      <section className="ai-metrics">
        {metrics.map((metric) => {
          const Icon = metric.icon;

          return (
            <article
              className="ai-metric-card"
              key={metric.label}
            >
              <div
                className={`ai-metric-icon ai-metric-icon--${metric.tone}`}
              >
                <Icon size={18} />
              </div>

              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <p>{metric.description}</p>
            </article>
          );
        })}
      </section>

      <section className="ai-decision-panel">
        <div className="ai-panel-header">
          <div>
            <h2>Shadow decision history</h2>
            <p>
              Production and AI recommendations for the same
              recovery cases
            </p>
          </div>

          <span>
            {decisions.length} evaluation
            {decisions.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="ai-table-wrapper">
          <table className="ai-table">
            <thead>
              <tr>
                <th>Payment</th>
                <th>Failure</th>
                <th>Production action</th>
                <th>AI recommendation</th>
                <th>Agreement</th>
                <th>Probability</th>
                <th>Latency</th>
              </tr>
            </thead>

            <tbody>
              {loadState === "loading" && (
                <tr>
                  <td colSpan={7} className="ai-table-message">
                    Loading AI evaluations...
                  </td>
                </tr>
              )}

              {loadState === "ready" &&
                decisions.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="ai-table-message"
                    >
                      No AI shadow evaluations are available.
                    </td>
                  </tr>
                )}

              {loadState === "ready" &&
                decisions.map((decision) => (
                  <tr key={decision.id}>
                    <td>
                      <strong className="ai-payment-id">
                        {decision.provider_payment_id ??
                          "Not available"}
                      </strong>

                      <span className="ai-row-date">
                        {formatDate(decision.created_at)}
                      </span>
                    </td>

                    <td>
                      {formatFailure(
                        decision.failure_category,
                      )}
                    </td>

                    <td>
                      {formatAction(
                        decision.production_action,
                      )}
                    </td>

                    <td>
                      <strong>
                        {formatAction(
                          decision.ai_recommended_action,
                        )}
                      </strong>

                      <span className="ai-model-name">
                        {decision.model_name}
                      </span>
                    </td>

                    <td>
                      {decision.agrees_with_production ===
                      true ? (
                        <span className="ai-agreement ai-agreement--yes">
                          <CheckCircle2 size={14} />
                          Agreed
                        </span>
                      ) : decision.agrees_with_production ===
                        false ? (
                        <span className="ai-agreement ai-agreement--no">
                          <XCircle size={14} />
                          Disagreed
                        </span>
                      ) : (
                        <span className="ai-agreement">
                          Pending
                        </span>
                      )}
                    </td>

                    <td>
                      {formatProbability(
                        decision.recovery_probability,
                      )}
                    </td>

                    <td>
                      {formatLatency(decision.latency_ms)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {loadState === "ready" &&
          decisions.length > 0 && (
            <div className="ai-explanations">
              {decisions.map((decision) => (
                <article
                  className="ai-explanation-card"
                  key={`${decision.id}-explanation`}
                >
                  <div className="ai-explanation-top">
                    <strong>
                      {decision.provider_payment_id}
                    </strong>

                    <span>{decision.prompt_version}</span>
                  </div>

                  <p>
                    {decision.explanation ??
                      "No AI explanation was provided."}
                  </p>

                  <div className="ai-reason-codes">
                    {decision.reason_codes.map((code) => (
                      <span key={code}>
                        {formatAction(code)}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}
      </section>
    </div>
  );
}