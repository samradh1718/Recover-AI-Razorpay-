import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getHealth } from "./api/health";
import {
  getRecoveryCases,
  type RecoveryCaseResponse,
  type RecoveryCaseState,
} from "./api/cases";
import { DecisionPanel } from "./components/DecisionPanel";
import {
  DecisionHistoryPage,
  PaymentEventsPage,
  RecoveryCasesPage,
  ReportsPage,
  SettingsPage,
  type ActivePage,
} from "./components/WorkspacePages";
import {
  Activity,
  BarChart3,
  Bell,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  IndianRupee,
  LayoutDashboard,
  ListChecks,
  MoreHorizontal,
  RefreshCcw,
  Search,
  Settings,
  Webhook,
} from "lucide-react";

import "./App.css";
import "./cases-dashboard.css";

type Metric = {
  title: string;
  value: string;
  description: string;
  icon: LucideIcon;
};

type CaseLoadState = "loading" | "ready" | "error";

const TERMINAL_STATES: RecoveryCaseState[] = [
  "RECOVERED",
  "EXHAUSTED",
  "STOPPED",
  "EXPIRED",
];

const failureLabels: Record<string, string> = {
  temporary_gateway_or_bank: "Gateway or bank issue",
  insufficient_funds: "Insufficient funds",
  invalid_or_expired_method: "Invalid or expired method",
  mandate_or_authorization: "Authorization failed",
  unknown: "Unknown failure",
};

const stateLabels: Record<RecoveryCaseState, string> = {
  DETECTED: "Detected",
  DIAGNOSED: "Diagnosed",
  EVALUATING: "Evaluating",
  READY: "Ready",
  SCHEDULED: "Scheduled",
  EXECUTING: "Executing",
  WAITING_FOR_RETRY: "Waiting for retry",
  WAITING_FOR_CUSTOMER: "Waiting for customer",
  HUMAN_REVIEW: "Needs review",
  RECOVERED: "Recovered",
  EXHAUSTED: "Exhausted",
  STOPPED: "Stopped",
  EXPIRED: "Expired",
};

function amountAsNumber(value: string): number {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : 0;
}

function formatMoney(
  value: number,
  currency = "INR",
): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRelativeTime(value: string): string {
  const createdAt = new Date(value).getTime();
  const difference = Date.now() - createdAt;

  if (!Number.isFinite(createdAt) || difference < 0) {
    return "Just now";
  }

  const minutes = Math.floor(difference / 60_000);

  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;

  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function getStateClass(state: RecoveryCaseState): string {
  if (state === "RECOVERED") return "recovered";
  if (state === "HUMAN_REVIEW") return "review";
  if (TERMINAL_STATES.includes(state)) return "closed";

  if (
    [
      "SCHEDULED",
      "EXECUTING",
      "WAITING_FOR_RETRY",
      "WAITING_FOR_CUSTOMER",
    ].includes(state)
  ) {
    return "scheduled";
  }

  return "detected";
}

function buildWeeklyRecovery(cases: RecoveryCaseResponse[]) {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - (6 - index));

    return {
      date,
      day: date.toLocaleDateString("en-IN", {
        weekday: "short",
      }),
      amount: 0,
    };
  });

  for (const recoveryCase of cases) {
    if (!recoveryCase.recovered_at) continue;

    const recoveredDate = new Date(recoveryCase.recovered_at);
    recoveredDate.setHours(0, 0, 0, 0);

    const matchingDay = days.find(
      (day) => day.date.getTime() === recoveredDate.getTime(),
    );

    if (matchingDay) {
      matchingDay.amount += amountAsNumber(
        recoveryCase.recovered_amount_rupees,
      );
    }
  }

  const largestAmount = Math.max(
    ...days.map((day) => day.amount),
    0,
  );

  return days.map((day) => ({
    day: day.day,
    amount: formatMoney(day.amount),
    height:
      largestAmount > 0
        ? Math.max(8, (day.amount / largestAmount) * 100)
        : 0,
  }));
}

function MetricCard({
  title,
  value,
  description,
  icon: Icon,
}: Metric) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <span>{title}</span>

        <div className="metric-icon">
          <Icon size={17} strokeWidth={1.8} />
        </div>
      </div>

      <div className="metric-value">{value}</div>

      <div className="metric-footer">
        <p>{description}</p>
      </div>
    </article>
  );
}
type HealthState =
  | "checking"
  | "online"
  | "degraded"
  | "offline";

const healthLabels: Record<HealthState, string> = {
  checking: "Checking service",
  online: "Backend online",
  degraded: "Service degraded",
  offline: "Backend offline",
};

export default function App() {
  const [activePage, setActivePage] =
    useState<ActivePage>("overview");
  const [healthState, setHealthState] =
    useState<HealthState>("checking");
  const [recoveryCases, setRecoveryCases] = useState<
    RecoveryCaseResponse[]
  >([]);
  const [caseLoadState, setCaseLoadState] =
    useState<CaseLoadState>("loading");
  const [casesError, setCasesError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCaseId, setSelectedCaseId] = useState<
    string | null
  >(null);

  const pageLabels: Record<ActivePage, string> = {
    overview: "Overview",
    cases: "Recovery cases",
    events: "Payment events",
    decisions: "Decision history",
    reports: "Reports",
    settings: "Settings",
  };

  const loadRecoveryCases = useCallback(
    async (signal?: AbortSignal) => {
      setCaseLoadState("loading");
      setCasesError("");

      try {
        const cases = await getRecoveryCases(signal);
        setRecoveryCases(cases);
        setCaseLoadState("ready");
      } catch (error: unknown) {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        setCasesError(
          error instanceof Error
            ? error.message
            : "Unable to load recovery cases",
        );
        setCaseLoadState("error");
      }
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((health) => {
        if (
          health.status === "ok" &&
          health.dependencies.database === "ok" &&
          health.dependencies.redis === "ok"
        ) {
          setHealthState("online");
        } else {
          setHealthState("degraded");
        }
      })
      .catch((error: unknown) => {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        setHealthState("offline");
      });

    return () => {
      controller.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    void loadRecoveryCases(controller.signal);

    return () => {
      controller.abort();
    };
  }, [loadRecoveryCases]);

  const currency = recoveryCases[0]?.currency ?? "INR";

  const totalRecoverable = recoveryCases.reduce(
    (total, recoveryCase) =>
      total +
      amountAsNumber(recoveryCase.recoverable_amount_rupees),
    0,
  );

  const totalRecovered = recoveryCases.reduce(
    (total, recoveryCase) =>
      total +
      amountAsNumber(recoveryCase.recovered_amount_rupees),
    0,
  );

  const activeCases = recoveryCases.filter(
    (recoveryCase) =>
      !TERMINAL_STATES.includes(recoveryCase.current_state),
  ).length;

  const recoveryRate =
    totalRecoverable > 0
      ? (totalRecovered / totalRecoverable) * 100
      : 0;

  const metrics: Metric[] = [
    {
      title: "Recoverable revenue",
      value:
        caseLoadState === "loading"
          ? "—"
          : formatMoney(totalRecoverable, currency),
      description: `${recoveryCases.length} cases in current view`,
      icon: IndianRupee,
    },
    {
      title: "Recovered revenue",
      value:
        caseLoadState === "loading"
          ? "—"
          : formatMoney(totalRecovered, currency),
      description: "Recorded by completed recoveries",
      icon: CheckCircle2,
    },
    {
      title: "Active cases",
      value:
        caseLoadState === "loading"
          ? "—"
          : String(activeCases),
      description: "Cases awaiting completion",
      icon: RefreshCcw,
    },
    {
      title: "Recovery rate",
      value:
        caseLoadState === "loading"
          ? "—"
          : `${recoveryRate.toFixed(1)}%`,
      description: "Recovered amount against recoverable value",
      icon: Activity,
    },
  ];

  const distributionCounts = {
    detected: recoveryCases.filter((recoveryCase) =>
      ["DETECTED", "DIAGNOSED", "EVALUATING", "READY"].includes(
        recoveryCase.current_state,
      ),
    ).length,
    scheduled: recoveryCases.filter((recoveryCase) =>
      [
        "SCHEDULED",
        "EXECUTING",
        "WAITING_FOR_RETRY",
        "WAITING_FOR_CUSTOMER",
      ].includes(recoveryCase.current_state),
    ).length,
    review: recoveryCases.filter(
      (recoveryCase) =>
        recoveryCase.current_state === "HUMAN_REVIEW",
    ).length,
    recovered: recoveryCases.filter(
      (recoveryCase) =>
        recoveryCase.current_state === "RECOVERED",
    ).length,
    closed: recoveryCases.filter((recoveryCase) =>
      ["EXHAUSTED", "STOPPED", "EXPIRED"].includes(
        recoveryCase.current_state,
      ),
    ).length,
  };

  const caseDistribution = [
    {
      label: "Detected",
      count: distributionCounts.detected,
      className: "detected",
    },
    {
      label: "Scheduled",
      count: distributionCounts.scheduled,
      className: "scheduled",
    },
    {
      label: "Needs review",
      count: distributionCounts.review,
      className: "review",
    },
    {
      label: "Recovered",
      count: distributionCounts.recovered,
      className: "recovered",
    },
    {
      label: "Closed",
      count: distributionCounts.closed,
      className: "closed",
    },
  ].map((item) => ({
    ...item,
    percentage:
      recoveryCases.length > 0
        ? (item.count / recoveryCases.length) * 100
        : 0,
  }));

  const weeklyRecovery = buildWeeklyRecovery(recoveryCases);
  const hasWeeklyRecovery = weeklyRecovery.some(
    (day) => day.height > 0,
  );

  const normalizedSearch = searchQuery.trim().toLowerCase();
  const filteredCases = recoveryCases.filter((recoveryCase) => {
    if (!normalizedSearch) return true;

    return [
      recoveryCase.provider_payment_id,
      recoveryCase.provider_subscription_id,
      recoveryCase.provider_customer_id,
      recoveryCase.failure_category,
      stateLabels[recoveryCase.current_state],
    ].some((value) =>
      value?.toLowerCase().includes(normalizedSearch),
    );
  });

  const selectedCase = selectedCaseId
    ? recoveryCases.find(
        (recoveryCase) => recoveryCase.id === selectedCaseId,
      ) ?? null
    : null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">R</div>

          <span className="brand-name">
            Recover<span>AI</span>
          </span>
        </div>

        <button className="workspace-switcher" type="button">
          <div className="workspace-avatar">RA</div>

          <div className="workspace-information">
            <strong>RecoverAI Sandbox</strong>
            <span>Test account</span>
          </div>

          <ChevronDown size={15} />
        </button>

        <nav className="navigation">
          <p className="navigation-label">Main</p>

          <button
            className={`navigation-item ${activePage === "overview" ? "navigation-item--active" : ""}`}
            type="button"
            onClick={() => setActivePage("overview")}
          >
            <LayoutDashboard size={18} />
            Overview
          </button>

          <button
            className={`navigation-item ${activePage === "cases" ? "navigation-item--active" : ""}`}
            type="button"
            onClick={() => setActivePage("cases")}
          >
            <RefreshCcw size={18} />
            Recovery cases
            <span className="navigation-count">
              {activeCases}
            </span>
          </button>

          <button
            className={`navigation-item ${activePage === "events" ? "navigation-item--active" : ""}`}
            type="button"
            onClick={() => setActivePage("events")}
          >
            <Webhook size={18} />
            Payment events
          </button>

          <button
            className={`navigation-item ${activePage === "decisions" ? "navigation-item--active" : ""}`}
            type="button"
            onClick={() => setActivePage("decisions")}
          >
            <ListChecks size={18} />
            Decision history
          </button>

          <button
            className={`navigation-item ${activePage === "reports" ? "navigation-item--active" : ""}`}
            type="button"
            onClick={() => setActivePage("reports")}
          >
            <BarChart3 size={18} />
            Reports
          </button>

          <p className="navigation-label navigation-label--second">
            Workspace
          </p>

          <button
            className={`navigation-item ${activePage === "settings" ? "navigation-item--active" : ""}`}
            type="button"
            onClick={() => setActivePage("settings")}
          >
            <Settings size={18} />
            Settings
          </button>
        </nav>

        <div className="sidebar-footer">
          <button className="profile" type="button">
            <div className="profile-avatar">SD</div>

            <div className="profile-information">
              <strong>Samradh Dubey</strong>
              <span>Administrator</span>
            </div>

            <ChevronDown size={16} />
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Recoveries</span>
            <span>/</span>
            <strong>{pageLabels[activePage]}</strong>
          </div>

          <div className="topbar-actions">
            <div
              className={`api-status api-status--${healthState}`}
              role="status"
              aria-live="polite"
            >
              <span />
              {healthLabels[healthState]}
            </div>

            <label className="search-box">
              <Search size={17} />
              <input
                type="search"
                placeholder={`Search ${pageLabels[activePage].toLowerCase()}`}
                aria-label="Search payments"
                value={searchQuery}
                onChange={(event) =>
                  setSearchQuery(event.target.value)
                }
              />
            </label>

            <div className="test-mode">
              <span />
              Test mode
            </div>

            <button
              className="icon-button"
              type="button"
              aria-label="Open recovery cases"
              onClick={() => setActivePage("cases")}
            >
              <Bell size={18} />
              {distributionCounts.review > 0 && (
                <span className="notification-dot" />
              )}
            </button>
          </div>
        </header>

        <div className="page">
          {activePage === "overview" && (
            <>
          <section className="page-heading">
            <div>
              <h1>Overview</h1>
              <p>
                Monitor failed payments and recovery activity.
              </p>
            </div>

            <div className="page-actions">
              <button className="secondary-button" type="button">
                <CalendarDays size={16} />
                Last 7 days
              </button>

              <button
                className="primary-button"
                type="button"
                onClick={() => void loadRecoveryCases()}
              >
                <RefreshCcw size={16} />
                Refresh data
              </button>
            </div>
          </section>

          <section className="metrics-grid">
            {metrics.map((metric) => (
              <MetricCard key={metric.title} {...metric} />
            ))}
          </section>

          <section className="overview-grid">
            <article className="panel recovery-chart-panel">
              <div className="panel-header">
                <div>
                  <h2>Recovered revenue</h2>
                  <p>Recovery value processed during this period</p>
                </div>

                <button
                  className="panel-menu"
                  type="button"
                  aria-label="Recovery chart options"
                >
                  <MoreHorizontal size={19} />
                </button>
              </div>

              <div className="chart-summary">
                <strong>
                  {caseLoadState === "loading"
                    ? "—"
                    : formatMoney(totalRecovered, currency)}
                </strong>
                <span>Last 7 days</span>
              </div>

              {hasWeeklyRecovery ? (
                <div className="chart">
                  {weeklyRecovery.map((item) => (
                    <div className="chart-column" key={item.day}>
                      <div className="bar-area">
                        <div
                          className="chart-bar"
                          style={{ height: `${item.height}%` }}
                          title={`${item.day}: ${item.amount}`}
                        />
                      </div>

                      <span>{item.day}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="chart-empty">
                  <BarChart3 size={24} />
                  <strong>No recovered payments yet</strong>
                  <span>
                    Recovered amounts will appear here.
                  </span>
                </div>
              )}
            </article>

            <article className="panel distribution-panel">
              <div className="panel-header">
                <div>
                  <h2>Case distribution</h2>
                  <p>
                    {recoveryCases.length} total recovery cases
                  </p>
                </div>

                <button
                  className="panel-menu"
                  type="button"
                  aria-label="Case distribution options"
                >
                  <MoreHorizontal size={19} />
                </button>
              </div>

              <div className="distribution-list">
                {caseDistribution.map((item) => (
                  <div
                    className="distribution-item"
                    key={item.label}
                  >
                    <div className="distribution-heading">
                      <div>
                        <span
                          className={`distribution-dot distribution-dot--${item.className}`}
                        />
                        <span>{item.label}</span>
                      </div>

                      <strong>{item.count}</strong>
                    </div>

                    <div className="distribution-track">
                      <div
                        className={`distribution-value distribution-value--${item.className}`}
                        style={{
                          width: `${item.percentage}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <button
                className="view-report-button"
                type="button"
                onClick={() => setActivePage("reports")}
              >
                View case report
              </button>
            </article>
          </section>

          <section className="panel cases-panel">
            <div className="table-header">
              <div>
                <h2>Recovery cases</h2>
                <p>Latest payment failures added to recovery</p>
              </div>

              <div className="table-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setActivePage("cases")}
                >
                  View all cases
                </button>
              </div>
            </div>

            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Payment ID</th>
                    <th>Customer</th>
                    <th>Amount</th>
                    <th>Failure reason</th>
                    <th>State</th>
                    <th>Created</th>
                    <th>Decision</th>
                  </tr>
                </thead>

                <tbody>
                  {caseLoadState === "loading" && (
                    <tr>
                      <td className="table-message" colSpan={7}>
                        Loading recovery cases...
                      </td>
                    </tr>
                  )}

                  {caseLoadState === "error" && (
                    <tr>
                      <td
                        className="table-message table-message--error"
                        colSpan={7}
                      >
                        {casesError}
                      </td>
                    </tr>
                  )}

                  {caseLoadState === "ready" &&
                    filteredCases.length === 0 && (
                      <tr>
                        <td className="table-message" colSpan={7}>
                          {searchQuery
                            ? "No recovery case matches your search."
                            : "No recovery cases have been created yet."}
                        </td>
                      </tr>
                    )}

                  {caseLoadState === "ready" &&
                    filteredCases.map((recoveryCase) => {
                      const providerReference =
                        recoveryCase.provider_payment_id ??
                        recoveryCase.provider_subscription_id ??
                        "Not available";

                      return (
                        <tr
                          className="case-row"
                          key={recoveryCase.id}
                          onClick={() =>
                            setSelectedCaseId(recoveryCase.id)
                          }
                        >
                          <td>
                            <span className="payment-id">
                              {providerReference}
                            </span>
                          </td>

                          <td>
                            {recoveryCase.provider_customer_id ??
                              "Not provided"}
                          </td>

                          <td className="amount">
                            {formatMoney(
                              amountAsNumber(
                                recoveryCase.recoverable_amount_rupees,
                              ),
                              recoveryCase.currency,
                            )}
                          </td>

                          <td>
                            {recoveryCase.failure_category
                              ? failureLabels[
                                  recoveryCase.failure_category
                                ] ?? "Unknown failure"
                              : "Not classified"}
                          </td>

                          <td>
                            <span
                              className={`case-state case-state--${getStateClass(
                                recoveryCase.current_state,
                              )}`}
                            >
                              {
                                stateLabels[
                                  recoveryCase.current_state
                                ]
                              }
                            </span>
                          </td>

                          <td className="created">
                            {formatRelativeTime(
                              recoveryCase.created_at,
                            )}
                          </td>

                          <td>
                            <button
                              className="case-review-button"
                              type="button"
                              aria-label={`Review decision for ${providerReference}`}
                              onClick={(event) => {
                                event.stopPropagation();
                                setSelectedCaseId(recoveryCase.id);
                              }}
                            >
                              Review
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>

            <div className="table-footer">
              <span>
                Showing {filteredCases.length} of{" "}
                {recoveryCases.length} cases
              </span>

              <div>
                <button type="button" disabled>
                  Previous
                </button>
                <button type="button" disabled>
                  Next
                </button>
              </div>
            </div>
          </section>
            </>
          )}

          {activePage === "cases" && (
            <RecoveryCasesPage
              recoveryCases={recoveryCases}
              searchQuery={searchQuery}
              onOpenCase={setSelectedCaseId}
              onRefreshCases={() => void loadRecoveryCases()}
              caseLoadState={caseLoadState}
              casesError={casesError}
            />
          )}

          {activePage === "events" && (
            <PaymentEventsPage searchQuery={searchQuery} />
          )}

          {activePage === "decisions" && (
            <DecisionHistoryPage
              recoveryCases={recoveryCases}
              searchQuery={searchQuery}
              onOpenCase={setSelectedCaseId}
            />
          )}

          {activePage === "reports" && (
            <ReportsPage recoveryCases={recoveryCases} />
          )}

          {activePage === "settings" && (
            <SettingsPage healthState={healthState} />
          )}
        </div>
      </main>

      {selectedCase && (
        <DecisionPanel
          recoveryCase={selectedCase}
          onClose={() => setSelectedCaseId(null)}
          onCaseUpdated={loadRecoveryCases}
        />
      )}
    </div>
  );
}
