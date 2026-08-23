import {
  Activity,
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  IndianRupee,
  RefreshCcw,
  Server,
  ShieldCheck,
  Webhook,
  Workflow,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import type {
  FailureCategory,
  RecoveryCaseResponse,
  RecoveryCaseState,
} from "../api/cases";
import {
  getRecoveryCaseDecisions,
  type RecoveryActionType,
  type RecoveryDecisionResponse,
} from "../api/decisions";
import {
  getPaymentEvents,
  type PaymentEventResponse,
} from "../api/payment-events";

export type ActivePage =
  | "overview"
  | "cases"
  | "events"
  | "decisions"
  | "reports"
  | "ai-insights"
  | "settings";

type DataState = "loading" | "ready" | "error";

type CommonProps = {
  recoveryCases: RecoveryCaseResponse[];
  searchQuery: string;
  onOpenCase: (caseId: string) => void;
  onRefreshCases: () => void;
  caseLoadState: DataState;
  casesError: string;
};

const terminalStates: RecoveryCaseState[] = [
  "RECOVERED",
  "EXHAUSTED",
  "STOPPED",
  "EXPIRED",
];

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

const failureLabels: Record<FailureCategory, string> = {
  temporary_gateway_or_bank: "Gateway or bank issue",
  insufficient_funds: "Insufficient funds",
  invalid_or_expired_method: "Invalid or expired method",
  mandate_or_authorization: "Authorization failed",
  unknown: "Unknown failure",
};

const actionLabels: Record<RecoveryActionType, string> = {
  retry_payment: "Retry payment",
  send_payment_link: "Send payment link",
  request_payment_method_update: "Request payment method update",
  request_customer_authorization: "Request customer authorization",
  human_review: "Human review",
  stop_recovery: "Stop recovery",
};

function number(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function dateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function stateClass(state: RecoveryCaseState): string {
  if (state === "RECOVERED") return "recovered";
  if (state === "HUMAN_REVIEW") return "review";
  if (terminalStates.includes(state)) return "closed";
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

function matchesCase(
  recoveryCase: RecoveryCaseResponse,
  searchQuery: string,
): boolean {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return true;

  return [
    recoveryCase.provider_payment_id,
    recoveryCase.provider_subscription_id,
    recoveryCase.provider_customer_id,
    recoveryCase.failure_category,
    recoveryCase.current_state,
  ].some((value) => value?.toLowerCase().includes(query));
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function downloadCsv(
  fileName: string,
  headers: string[],
  rows: unknown[][],
) {
  const csv = [
    headers.map(csvCell).join(","),
    ...rows.map((row) => row.map(csvCell).join(",")),
  ].join("\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

function PageHeading({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <section className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="page-actions">{children}</div>}
    </section>
  );
}

function EmptyTable({
  state,
  error,
  empty,
  colSpan,
}: {
  state: DataState;
  error: string;
  empty: string;
  colSpan: number;
}) {
  if (state === "loading") {
    return (
      <tr><td className="table-message" colSpan={colSpan}>Loading data...</td></tr>
    );
  }
  if (state === "error") {
    return (
      <tr><td className="table-message table-message--error" colSpan={colSpan}>{error}</td></tr>
    );
  }
  return (
    <tr><td className="table-message" colSpan={colSpan}>{empty}</td></tr>
  );
}

export function RecoveryCasesPage({
  recoveryCases,
  searchQuery,
  onOpenCase,
  onRefreshCases,
  caseLoadState,
  casesError,
}: CommonProps) {
  const [stateFilter, setStateFilter] = useState("ALL");
  const [failureFilter, setFailureFilter] = useState("ALL");

  const visibleCases = recoveryCases.filter((recoveryCase) =>
    matchesCase(recoveryCase, searchQuery) &&
    (stateFilter === "ALL" || recoveryCase.current_state === stateFilter) &&
    (failureFilter === "ALL" || recoveryCase.failure_category === failureFilter),
  );

  function exportCases() {
    downloadCsv(
      "recoverai-cases.csv",
      ["Payment ID", "Customer", "Amount (INR)", "Failure", "State", "Attempts", "Communications", "Created"],
      visibleCases.map((item) => [
        item.provider_payment_id ?? item.provider_subscription_id,
        item.provider_customer_id,
        item.recoverable_amount_rupees,
        item.failure_category,
        item.current_state,
        item.attempt_count,
        item.communication_count,
        item.created_at,
      ]),
    );
  }

  return (
    <>
      <PageHeading title="Recovery cases" description="Track every at-risk payment from detection to closure.">
        <button className="secondary-button" type="button" onClick={onRefreshCases}>
          <RefreshCcw size={15} /> Refresh
        </button>
        <button className="primary-button" type="button" onClick={exportCases} disabled={visibleCases.length === 0}>
          <Download size={15} /> Export CSV
        </button>
      </PageHeading>

      <section className="panel cases-panel workspace-table-panel">
        <div className="table-header">
          <div><h2>Case queue</h2><p>{visibleCases.length} of {recoveryCases.length} cases</p></div>
          <div className="filter-row">
            <label>
              <span>State</span>
              <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
                <option value="ALL">All states</option>
                {Object.entries(stateLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Failure</span>
              <select value={failureFilter} onChange={(event) => setFailureFilter(event.target.value)}>
                <option value="ALL">All failures</option>
                {Object.entries(failureLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          </div>
        </div>
        <div className="table-wrapper">
          <table>
            <thead><tr><th>Payment ID</th><th>Customer</th><th>Recoverable</th><th>Failure</th><th>State</th><th>Attempts</th><th>Next action</th><th /></tr></thead>
            <tbody>
              {caseLoadState !== "ready" || visibleCases.length === 0 ? (
                <EmptyTable state={caseLoadState} error={casesError} empty="No recovery cases match these filters." colSpan={8} />
              ) : visibleCases.map((item) => {
                const reference = item.provider_payment_id ?? item.provider_subscription_id ?? item.id;
                return (
                  <tr className="case-row" key={item.id} onClick={() => onOpenCase(item.id)}>
                    <td><span className="payment-id">{reference}</span></td>
                    <td>{item.provider_customer_id ?? "Not provided"}</td>
                    <td className="amount">{money(number(item.recoverable_amount_rupees), item.currency)}</td>
                    <td>{item.failure_category ? failureLabels[item.failure_category] : "Not classified"}</td>
                    <td><span className={`case-state case-state--${stateClass(item.current_state)}`}>{stateLabels[item.current_state]}</span></td>
                    <td>{item.attempt_count}</td>
                    <td>{dateTime(item.next_action_at)}</td>
                    <td><button className="case-review-button" type="button" onClick={(event) => { event.stopPropagation(); onOpenCase(item.id); }}>Review</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function PaymentEventsPage({ searchQuery }: { searchQuery: string }) {
  const [events, setEvents] = useState<PaymentEventResponse[]>([]);
  const [state, setState] = useState<DataState>("loading");
  const [error, setError] = useState("");

  const loadEvents = useCallback(async (signal?: AbortSignal) => {
    setState("loading");
    setError("");
    try {
      setEvents(await getPaymentEvents(signal));
      setState("ready");
    } catch (loadError: unknown) {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      setError(loadError instanceof Error ? loadError.message : "Unable to load payment events");
      setState("error");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadEvents(controller.signal);
    return () => controller.abort();
  }, [loadEvents]);

  const query = searchQuery.trim().toLowerCase();
  const visibleEvents = events.filter((event) => !query || [event.provider_event_id, event.provider_payment_id, event.event_type, event.processing_status].some((value) => value?.toLowerCase().includes(query)));

  function exportEvents() {
    downloadCsv("recoverai-payment-events.csv", ["Provider event ID", "Type", "Payment ID", "Status", "Received", "Processed", "Error"], visibleEvents.map((event) => [event.provider_event_id, event.event_type, event.provider_payment_id, event.processing_status, event.received_at, event.processed_at, event.processing_error]));
  }

  return (
    <>
      <PageHeading title="Payment events" description="Inspect signed Razorpay events and asynchronous processing results.">
        <button className="secondary-button" type="button" onClick={() => void loadEvents()}><RefreshCcw size={15} /> Refresh</button>
        <button className="primary-button" type="button" onClick={exportEvents} disabled={visibleEvents.length === 0}><Download size={15} /> Export CSV</button>
      </PageHeading>
      {state === "error" && error.includes("not available") ? (
        <section className="panel endpoint-empty">
          <div className="endpoint-empty-icon"><Webhook size={24} /></div>
          <h2>Payment event history needs one read endpoint</h2>
          <p>The webhook ingestion is working. Add <code>GET /api/v1/payment-events</code> so this page can read the already stored <code>payment_events</code> rows. No placeholder events are displayed.</p>
          <button className="secondary-button" type="button" onClick={() => void loadEvents()}><RefreshCcw size={15} /> Try again</button>
        </section>
      ) : (
        <section className="panel cases-panel workspace-table-panel">
          <div className="table-header"><div><h2>Webhook ledger</h2><p>{visibleEvents.length} events in current view</p></div></div>
          <div className="table-wrapper"><table><thead><tr><th>Event ID</th><th>Event type</th><th>Payment ID</th><th>Status</th><th>Received</th><th>Processed</th><th>Error</th></tr></thead>
            <tbody>{state !== "ready" || visibleEvents.length === 0 ? <EmptyTable state={state} error={error} empty="No payment events found." colSpan={7} /> : visibleEvents.map((event) => <tr key={event.id}><td><span className="payment-id">{event.provider_event_id}</span></td><td>{event.event_type}</td><td><span className="payment-id">{event.provider_payment_id ?? "—"}</span></td><td><span className={`processing-status processing-status--${event.processing_status}`}>{event.processing_status}</span></td><td>{dateTime(event.received_at)}</td><td>{dateTime(event.processed_at)}</td><td className={event.processing_error ? "error-text" : "muted-cell"}>{event.processing_error ?? "—"}</td></tr>)}</tbody>
          </table></div>
        </section>
      )}
    </>
  );
}

type DecisionRow = {
  recoveryCase: RecoveryCaseResponse;
  decision: RecoveryDecisionResponse;
};

function useDecisionRows(recoveryCases: RecoveryCaseResponse[]) {
  const [rows, setRows] = useState<DecisionRow[]>([]);
  const [state, setState] = useState<DataState>("loading");
  const [error, setError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    if (recoveryCases.length === 0) {
      setRows([]);
      setState("ready");
      return;
    }
    setState("loading");
    setError("");
    try {
      const decisions = await Promise.all(recoveryCases.map(async (recoveryCase) => ({ recoveryCase, decisions: await getRecoveryCaseDecisions(recoveryCase.id, signal) })));
      setRows(decisions.flatMap(({ recoveryCase, decisions: caseDecisions }) => caseDecisions.map((decision) => ({ recoveryCase, decision }))).sort((a, b) => new Date(b.decision.created_at).getTime() - new Date(a.decision.created_at).getTime()));
      setState("ready");
    } catch (loadError: unknown) {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      setError(loadError instanceof Error ? loadError.message : "Unable to load decision history");
      setState("error");
    }
  }, [recoveryCases]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return { rows, state, error, load };
}

export function DecisionHistoryPage({ recoveryCases, searchQuery, onOpenCase }: Pick<CommonProps, "recoveryCases" | "searchQuery" | "onOpenCase">) {
  const { rows, state, error, load } = useDecisionRows(recoveryCases);
  const query = searchQuery.trim().toLowerCase();
  const visibleRows = rows.filter(({ recoveryCase, decision }) => !query || [recoveryCase.provider_payment_id, decision.final_action, decision.recommended_action, decision.policy_result, decision.status].some((value) => value?.toLowerCase().includes(query)));

  return (
    <>
      <PageHeading title="Decision history" description="Audit every recommendation, policy outcome and execution status.">
        <button className="secondary-button" type="button" onClick={() => void load()}><RefreshCcw size={15} /> Refresh</button>
      </PageHeading>
      <section className="panel cases-panel workspace-table-panel">
        <div className="table-header"><div><h2>Decision audit trail</h2><p>{visibleRows.length} decisions</p></div></div>
        <div className="table-wrapper"><table><thead><tr><th>Payment ID</th><th>Recommended</th><th>Final action</th><th>Policy</th><th>Status</th><th>Expected net</th><th>Scheduled</th><th /></tr></thead>
          <tbody>{state !== "ready" || visibleRows.length === 0 ? <EmptyTable state={state} error={error} empty="No recovery decisions have been generated yet." colSpan={8} /> : visibleRows.map(({ recoveryCase, decision }) => <tr className="case-row" key={decision.id} onClick={() => onOpenCase(recoveryCase.id)}><td><span className="payment-id">{recoveryCase.provider_payment_id ?? recoveryCase.provider_subscription_id ?? recoveryCase.id}</span></td><td>{actionLabels[decision.recommended_action]}</td><td>{decision.final_action ? actionLabels[decision.final_action] : "Pending"}</td><td><span className={`policy-chip policy-chip--${decision.policy_result}`}>{decision.policy_result}</span></td><td><span className={`processing-status processing-status--${decision.status}`}>{decision.status}</span></td><td className="amount">{money(number(decision.expected_net_value_rupees), recoveryCase.currency)}</td><td>{dateTime(decision.scheduled_for)}</td><td><button className="case-review-button" type="button">Open</button></td></tr>)}</tbody>
        </table></div>
      </section>
    </>
  );
}

export function ReportsPage({ recoveryCases }: { recoveryCases: RecoveryCaseResponse[] }) {
  const totalRecoverable = recoveryCases.reduce((sum, item) => sum + number(item.recoverable_amount_rupees), 0);
  const totalRecovered = recoveryCases.reduce((sum, item) => sum + number(item.recovered_amount_rupees), 0);
  const totalCost = recoveryCases.reduce((sum, item) => sum + number(item.intervention_cost_rupees), 0);
  const netRecovered = totalRecovered - totalCost;
  const currency = recoveryCases[0]?.currency ?? "INR";
  const recoveredCount = recoveryCases.filter((item) => item.current_state === "RECOVERED").length;
  const recoveryRate = totalRecoverable > 0 ? (totalRecovered / totalRecoverable) * 100 : 0;
  const roi = totalCost > 0 ? netRecovered / totalCost : 0;

  const failureSummary = Object.entries(failureLabels).map(([key, label]) => {
    const cases = recoveryCases.filter((item) => item.failure_category === key);
    const amount = cases.reduce((sum, item) => sum + number(item.recoverable_amount_rupees), 0);
    return { key, label, count: cases.length, amount };
  }).filter((item) => item.count > 0).sort((a, b) => b.amount - a.amount);

  return (
    <>
      <PageHeading title="Reports" description="Measured recovery value, intervention cost and case outcomes." />
      <section className="report-metrics">
        <article className="report-card"><IndianRupee size={18} /><span>Recovered revenue</span><strong>{money(totalRecovered, currency)}</strong><small>{recoveredCount} recovered cases</small></article>
        <article className="report-card"><Activity size={18} /><span>Recovery rate</span><strong>{recoveryRate.toFixed(1)}%</strong><small>Recovered ÷ recoverable</small></article>
        <article className="report-card"><Workflow size={18} /><span>Intervention cost</span><strong>{money(totalCost, currency)}</strong><small>Recorded action cost</small></article>
        <article className="report-card"><CheckCircle2 size={18} /><span>Net recovered value</span><strong>{money(netRecovered, currency)}</strong><small>{totalCost > 0 ? `${roi.toFixed(1)}× return on cost` : "No action cost recorded"}</small></article>
      </section>
      <section className="reports-grid">
        <article className="panel report-panel">
          <div className="panel-header"><div><h2>Revenue flow</h2><p>Actual values stored on recovery cases</p></div></div>
          <div className="value-flow">
            <div><span>Recoverable</span><strong>{money(totalRecoverable, currency)}</strong></div>
            <div><span>Recovered</span><strong>{money(totalRecovered, currency)}</strong></div>
            <div><span>Action cost</span><strong>− {money(totalCost, currency)}</strong></div>
            <div className="value-flow-total"><span>Net recovered</span><strong>{money(netRecovered, currency)}</strong></div>
          </div>
        </article>
        <article className="panel report-panel">
          <div className="panel-header"><div><h2>Failure exposure</h2><p>Recoverable value grouped by diagnosis</p></div></div>
          {failureSummary.length === 0 ? <div className="small-empty">No classified failures yet.</div> : <div className="failure-report-list">{failureSummary.map((item) => <div key={item.key}><div><strong>{item.label}</strong><span>{item.count} cases</span></div><strong>{money(item.amount, currency)}</strong></div>)}</div>}
        </article>
      </section>
      <section className="panel evidence-note"><ShieldCheck size={20} /><div><h2>Hackathon evidence</h2><p>These totals are calculated only from persisted backend cases. For the final demo, run a batch and show recoverable amount, recovered amount, action cost, net value, stopped cases and the decision audit trail together.</p></div></section>
    </>
  );
}

export function SettingsPage({ healthState }: { healthState: string }) {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
  return (
    <>
      <PageHeading title="Settings" description="Runtime connection and recovery safety configuration." />
      <section className="settings-grid">
        <article className="panel settings-card"><div className="settings-icon"><Server size={19} /></div><div><span>Backend API</span><strong>{apiBaseUrl}</strong><small className={`connection-text connection-text--${healthState}`}>{healthState}</small></div></article>
        <article className="panel settings-card"><div className="settings-icon"><Database size={19} /></div><div><span>Data source</span><strong>PostgreSQL recovery ledger</strong><small>Dashboard values are not mocked</small></div></article>
        <article className="panel settings-card"><div className="settings-icon"><Webhook size={19} /></div><div><span>Event source</span><strong>Razorpay signed webhooks</strong><small>Test mode during development</small></div></article>
        <article className="panel settings-card"><div className="settings-icon"><BrainCircuit size={19} /></div><div><span>Decision source</span><strong>rules_v1</strong><small>AI shadow mode will be added separately</small></div></article>
      </section>
      <section className="panel guardrail-panel">
        <div className="panel-header"><div><h2>Active safety boundaries</h2><p>Implemented backend policy controls</p></div></div>
        <div className="guardrail-list">
          <div><ShieldCheck size={17} /><div><strong>Bounded action set</strong><span>Only approved recovery actions may be selected.</span></div></div>
          <div><Clock3 size={17} /><div><strong>Recovery deadline</strong><span>Every case has an explicit expiry time.</span></div></div>
          <div><RefreshCcw size={17} /><div><strong>Retry and communication counters</strong><span>Attempts and customer contacts are persisted for stopping rules.</span></div></div>
          <div><AlertCircle size={17} /><div><strong>Human escalation</strong><span>Unknown or unsafe cases can be routed to review.</span></div></div>
        </div>
      </section>
    </>
  );
}
