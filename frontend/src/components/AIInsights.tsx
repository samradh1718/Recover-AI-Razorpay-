import type { LucideIcon } from "lucide-react";
import {
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Cpu,
  RefreshCcw,
  Scale,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getAIShadowDecisions,
  getAIShadowSummary,
  type AIShadowDecision,
  type AIShadowSummary,
} from "../api/aiShadow";
import {
  getMLShadowDecisions,
  getMLShadowSummary,
  type MLShadowDecision,
  type MLShadowSummary,
} from "../api/mlShadow";

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


function formatLatency(value: number | null): string {
  if (value === null) return "—";

  if (value < 1000) {
    return `${value} ms`;
  }

  return `${(value / 1000).toFixed(2)} sec`;
}


function formatProbability(
  value: string | null,
): string {
  if (value === null) return "—";

  const probability = Number(value);

  if (!Number.isFinite(probability)) return "—";

  return `${(probability * 100).toFixed(1)}%`;
}


function formatCurrency(value: string | null): string {
  if (value === null) return "—";

  const amount = Number(value);

  if (!Number.isFinite(amount)) return "—";

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(amount);
}


function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}


function getAlignment(
  mlDecision: MLShadowDecision,
  aiDecision?: AIShadowDecision,
): {
  label: string;
  tone: "yes" | "no" | "partial";
} {
  if (
    mlDecision.agrees_with_production === true &&
    aiDecision?.agrees_with_production === true
  ) {
    return {
      label: "All aligned",
      tone: "yes",
    };
  }

  if (
    mlDecision.agrees_with_production === false ||
    aiDecision?.agrees_with_production === false
  ) {
    return {
      label: "Review divergence",
      tone: "no",
    };
  }

  if (
    mlDecision.agrees_with_production === true &&
    !aiDecision
  ) {
    return {
      label: "ML aligned",
      tone: "partial",
    };
  }

  return {
    label: "Pending",
    tone: "partial",
  };
}


export function AIInsights() {
  const [aiSummary, setAISummary] =
    useState<AIShadowSummary | null>(null);

  const [aiDecisions, setAIDecisions] = useState<
    AIShadowDecision[]
  >([]);

  const [mlSummary, setMLSummary] =
    useState<MLShadowSummary | null>(null);

  const [mlDecisions, setMLDecisions] = useState<
    MLShadowDecision[]
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
        const [
          aiSummaryResult,
          aiDecisionResults,
          mlSummaryResult,
          mlDecisionResults,
        ] = await Promise.all([
          getAIShadowSummary(signal),
          getAIShadowDecisions(signal),
          getMLShadowSummary(signal),
          getMLShadowDecisions(signal),
        ]);

        setAISummary(aiSummaryResult);
        setAIDecisions(aiDecisionResults);
        setMLSummary(mlSummaryResult);
        setMLDecisions(mlDecisionResults);
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
            : "Unable to load decision intelligence",
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


  const comparisonRows = useMemo(() => {
    const aiByProductionDecision = new Map(
      aiDecisions.map((decision) => [
        decision.production_decision_id,
        decision,
      ]),
    );

    return mlDecisions.map((mlDecision) => ({
      mlDecision,
      aiDecision: aiByProductionDecision.get(
        mlDecision.production_decision_id,
      ),
    }));
  }, [aiDecisions, mlDecisions]);


  const latestMLDecision = mlDecisions[0] ?? null;


  const metrics: InsightMetric[] = [
    {
      label: "ML evaluations",
      value:
        loadState === "loading"
          ? "—"
          : String(mlSummary?.total_evaluations ?? 0),
      description: "CatBoost shadow decisions generated",
      icon: Cpu,
      tone: "blue",
    },
    {
      label: "ML agreement",
      value:
        loadState === "loading"
          ? "—"
          : `${(
              mlSummary?.agreement_rate_percent ?? 0
            ).toFixed(1)}%`,
      description: "Agreement with bounded rules engine",
      icon: CheckCircle2,
      tone: "green",
    },
    {
      label: "Average probability",
      value:
        loadState === "loading"
          ? "—"
          : formatProbability(
              mlSummary
                ?.average_calibrated_probability ?? null,
            ),
      description: "Calibrated recovery probability",
      icon: Scale,
      tone: "purple",
    },
    {
      label: "ML latency",
      value:
        loadState === "loading"
          ? "—"
          : formatLatency(
              mlSummary?.average_latency_ms ?? null,
            ),
      description: "Average CatBoost ranking time",
      icon: Clock3,
      tone: "orange",
    },
  ];


  return (
    <div className="ai-insights">
      <section className="ai-heading">
        <div>
          <div className="ai-heading-label">
            <BrainCircuit size={16} />
            Decision intelligence
          </div>

          <h1>Recovery Decision Lab</h1>

          <p>
            Compare bounded production rules, CatBoost action
            ranking and Ollama recommendations.
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
          <strong>
            Production policy remains in control
          </strong>

          <p>
            CatBoost and Ollama evaluate the same case in
            shadow mode. They cannot execute financial or
            customer-facing actions.
          </p>
        </div>
      </div>

      {loadState === "error" && (
        <div className="ai-error">
          <XCircle size={19} />

          <div>
            <strong>
              Unable to load decision intelligence
            </strong>
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

      <section className="ai-model-grid">
        <article className="ai-model-card ai-model-card--rules">
          <div className="ai-model-card-heading">
            <div>
              <ShieldCheck size={19} />
              <strong>Rules engine</strong>
            </div>

            <span>Production</span>
          </div>

          <p>
            Applies eligibility, policy limits, stopping rules
            and execution boundaries.
          </p>

          <div className="ai-model-footer">
            <strong>Execution authority</strong>
            <span>Deterministic and auditable</span>
          </div>
        </article>

        <article className="ai-model-card ai-model-card--ml">
          <div className="ai-model-card-heading">
            <div>
              <Cpu size={19} />
              <strong>CatBoost</strong>
            </div>

            <span>Shadow</span>
          </div>

          <p>
            Scores allowed actions and ranks them using
            calibrated expected net value.
          </p>

          <div className="ai-model-footer">
            <strong>
              {mlSummary?.completed_count ?? 0} evaluations
            </strong>

            <span>
              {formatLatency(
                mlSummary?.average_latency_ms ?? null,
              )}{" "}
              average
            </span>
          </div>
        </article>

        <article className="ai-model-card ai-model-card--ollama">
          <div className="ai-model-card-heading">
            <div>
              <BrainCircuit size={19} />
              <strong>Ollama · Llama 3</strong>
            </div>

            <span>Shadow</span>
          </div>

          <p>
            Produces a separate recommendation, explanation
            and auditable reason codes.
          </p>

          <div className="ai-model-footer">
            <strong>
              {aiSummary?.completed_count ?? 0} evaluations
            </strong>

            <span>
              {(aiSummary?.agreement_rate_percent ?? 0)
                .toFixed(1)}
              % rules agreement
            </span>
          </div>
        </article>
      </section>

      <section className="ai-decision-panel">
        <div className="ai-panel-header">
          <div>
            <h2>Decision comparison</h2>

            <p>
              Three decision layers evaluated against the same
              recovery case
            </p>
          </div>

          <span>
            {comparisonRows.length} comparison
            {comparisonRows.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="ai-table-wrapper">
          <table className="ai-table ai-comparison-table">
            <thead>
              <tr>
                <th>Payment</th>
                <th>Failure</th>
                <th>Rules action</th>
                <th>CatBoost</th>
                <th>Ollama</th>
                <th>Result</th>
              </tr>
            </thead>

            <tbody>
              {loadState === "loading" && (
                <tr>
                  <td
                    colSpan={6}
                    className="ai-table-message"
                  >
                    Loading decision comparisons...
                  </td>
                </tr>
              )}

              {loadState === "ready" &&
                comparisonRows.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="ai-table-message"
                    >
                      No ML shadow evaluations are available.
                    </td>
                  </tr>
                )}

              {loadState === "ready" &&
                comparisonRows.map(
                  ({ mlDecision, aiDecision }) => {
                    const alignment = getAlignment(
                      mlDecision,
                      aiDecision,
                    );

                    return (
                      <tr key={mlDecision.id}>
                        <td>
                          <strong className="ai-payment-id">
                            {mlDecision
                              .provider_payment_id ??
                              "Not available"}
                          </strong>

                          <span className="ai-row-date">
                            {formatDate(
                              mlDecision.created_at,
                            )}
                          </span>
                        </td>

                        <td>
                          {formatAction(
                            mlDecision.failure_category,
                          )}
                        </td>

                        <td>
                          <strong>
                            {formatAction(
                              mlDecision
                                .production_action,
                            )}
                          </strong>

                          <span className="ai-table-model-detail">
                            Bounded policy
                          </span>
                        </td>

                        <td>
                          <strong>
                            {formatAction(
                              mlDecision
                                .ml_selected_action,
                            )}
                          </strong>

                          <span className="ai-table-model-detail">
                            {formatProbability(
                              mlDecision
                                .calibrated_probability,
                            )}
                            {" · "}
                            {formatCurrency(
                              mlDecision
                                .expected_net_value_rupees,
                            )}{" "}
                            net
                          </span>
                        </td>

                        <td>
                          <strong>
                            {formatAction(
                              aiDecision
                                ?.ai_recommended_action ??
                                null,
                            )}
                          </strong>

                          <span className="ai-table-model-detail">
                            {aiDecision
                              ? `${formatProbability(
                                  aiDecision
                                    .recovery_probability,
                                )} · ${formatLatency(
                                  aiDecision.latency_ms,
                                )}`
                              : "No matching evaluation"}
                          </span>
                        </td>

                        <td>
                          <span
                            className={`ai-alignment ai-alignment--${alignment.tone}`}
                          >
                            {alignment.tone === "yes" ? (
                              <CheckCircle2 size={14} />
                            ) : alignment.tone === "no" ? (
                              <XCircle size={14} />
                            ) : (
                              <Clock3 size={14} />
                            )}

                            {alignment.label}
                          </span>
                        </td>
                      </tr>
                    );
                  },
                )}
            </tbody>
          </table>
        </div>
      </section>

      {latestMLDecision &&
        latestMLDecision.alternatives.length > 0 && (
          <section className="ml-ranking-panel">
            <div className="ai-panel-header">
              <div>
                <h2>Latest CatBoost action ranking</h2>

                <p>
                  {latestMLDecision.provider_payment_id} ·{" "}
                  {formatAction(
                    latestMLDecision.failure_category,
                  )}
                </p>
              </div>

              <span>
                {
                  latestMLDecision.alternatives.length
                }{" "}
                allowed actions
              </span>
            </div>

            <div className="ml-ranking-list">
              {latestMLDecision.alternatives.map(
                (alternative) => {
                  const probability = Math.max(
                    0,
                    Math.min(
                      100,
                      Number(
                        alternative
                          .calibrated_probability,
                      ) * 100,
                    ),
                  );

                  return (
                    <article
                      className={`ml-ranking-row ${
                        alternative.rank === 1
                          ? "ml-ranking-row--selected"
                          : ""
                      }`}
                      key={alternative.action}
                    >
                      <div className="ml-rank-number">
                        {alternative.rank}
                      </div>

                      <div className="ml-rank-action">
                        <strong>
                          {formatAction(
                            alternative.action,
                          )}
                        </strong>

                        <span>
                          {alternative.rank === 1
                            ? "Selected by expected net value"
                            : "Policy-allowed alternative"}
                        </span>
                      </div>

                      <div className="ml-rank-probability">
                        <div>
                          <span>
                            Recovery probability
                          </span>

                          <strong>
                            {formatProbability(
                              alternative
                                .calibrated_probability,
                            )}
                          </strong>
                        </div>

                        <div className="ml-probability-track">
                          <span
                            style={{
                              width: `${probability}%`,
                            }}
                          />
                        </div>
                      </div>

                      <div className="ml-rank-value">
                        <span>Expected net value</span>

                        <strong>
                          {formatCurrency(
                            alternative
                              .expected_net_value_rupees,
                          )}
                        </strong>

                        <small>
                          Cost{" "}
                          {formatCurrency(
                            alternative
                              .estimated_action_cost_rupees,
                          )}
                        </small>
                      </div>
                    </article>
                  );
                },
              )}
            </div>
          </section>
        )}
    </div>
  );
}