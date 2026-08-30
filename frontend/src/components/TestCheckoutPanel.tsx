import {
  CheckCircle2,
  Clock3,
  CreditCard,
  ExternalLink,
  LoaderCircle,
  RefreshCcw,
  ShieldCheck,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  createRazorpayTestCheckoutOrder,
  getRazorpayTestCheckoutOrders,
  reconcileRazorpayTestCheckoutOrder,
  type RazorpayTestCheckoutOrder,
  type RazorpayTestOrderRecord,
} from "../api/testCheckout";
import {
  openRazorpayTestCheckout,
  type RazorpayCheckoutResult,
} from "../api/razorpayCheckout";


type TestCheckoutPanelProps = {
  onProviderActivity?: () => void | Promise<void>;
};


type CheckoutPhase =
  | "idle"
  | "creating_order"
  | "checkout_open"
  | "waiting_for_webhook"
  | "provider_confirmed"
  | "payment_failed"
  | "dismissed"
  | "error";


const MAX_TEST_AMOUNT_RUPEES = 10_000;


function formatMoney(
  value: string | number,
): string {
  const amount = Number(value);

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}


function formatDateTime(value: string): string {
  const timestamp = new Date(value);

  if (Number.isNaN(timestamp.getTime())) {
    return "Unknown time";
  }

  return timestamp.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}


function displayStatus(
  order: RazorpayTestOrderRecord,
): string {
  if (order.outcome_status !== "pending") {
    return order.outcome_status.replaceAll(
      "_",
      " ",
    );
  }

  return order.provider_order_status.replaceAll(
    "_",
    " ",
  );
}


function statusClass(
  order: RazorpayTestOrderRecord,
): string {
  const status = displayStatus(
    order,
  ).toLowerCase();

  if (
    status.includes("paid") ||
    status.includes("captured") ||
    status.includes("authorized") ||
    status.includes("completed")
  ) {
    return "success";
  }

  if (
    status.includes("failed") ||
    status.includes("cancelled") ||
    status.includes("expired")
  ) {
    return "failure";
  }

  return "pending";
}


function phaseMessage(
  phase: CheckoutPhase,
  result: RazorpayCheckoutResult | null,
  confirmedOrder: RazorpayTestOrderRecord | null,
): string | null {
  if (phase === "creating_order") {
    return (
      "Creating a provider-generated " +
      "Razorpay Test Mode order..."
    );
  }

  if (phase === "checkout_open") {
    return (
      "Razorpay Checkout is open. Complete " +
      "or fail the test payment there."
    );
  }

  if (phase === "waiting_for_webhook") {
    return (
      "Checkout submitted. RecoverAI is checking " +
      "Razorpay's server API every 3 seconds for " +
      "provider confirmation."
    );
  }

  if (
    phase === "provider_confirmed" &&
    confirmedOrder !== null
  ) {
    return (
      "Razorpay confirmed payment " +
      `${confirmedOrder.provider_payment_id ?? ""} ` +
      `for ${formatMoney(
        confirmedOrder.amount_rupees,
      )}.`
    );
  }

  if (
    phase === "payment_failed" &&
    result?.status === "payment_failed"
  ) {
    return result.message;
  }

  if (phase === "dismissed") {
    return (
      "Checkout was closed. The provider order " +
      "remains available for another attempt."
    );
  }

  return null;
}


export function TestCheckoutPanel({
  onProviderActivity,
}: TestCheckoutPanelProps) {
  const [amountRupees, setAmountRupees] =
    useState("499");

  const [
    customerReference,
    setCustomerReference,
  ] = useState(
    "demo_realtime_customer_001",
  );

  const [phase, setPhase] =
    useState<CheckoutPhase>("idle");

  const [errorMessage, setErrorMessage] =
    useState("");

  const [checkoutResult, setCheckoutResult] =
    useState<RazorpayCheckoutResult | null>(
      null,
    );

  const [activeOrder, setActiveOrder] =
    useState<RazorpayTestCheckoutOrder | null>(
      null,
    );

  const [confirmedOrder, setConfirmedOrder] =
    useState<RazorpayTestOrderRecord | null>(
      null,
    );

  const [orders, setOrders] = useState<
    RazorpayTestOrderRecord[]
  >([]);

  const [ordersLoading, setOrdersLoading] =
    useState(true);

  const [ordersError, setOrdersError] =
    useState("");

  const reconciliationInFlightRef =
    useRef(false);

  const onProviderActivityRef = useRef(
    onProviderActivity,
  );

  const numericAmount = Number(
    amountRupees,
  );

  const amountIsValid = (
    Number.isFinite(numericAmount) &&
    numericAmount > 0 &&
    numericAmount <=
      MAX_TEST_AMOUNT_RUPEES
  );

  const checkoutBusy = (
    phase === "creating_order" ||
    phase === "checkout_open"
  );

  const recentOrders = useMemo(
    () => orders.slice(0, 6),
    [orders],
  );

  useEffect(() => {
    onProviderActivityRef.current = (
      onProviderActivity
    );
  }, [onProviderActivity]);

  const loadOrders = useCallback(
    async (
      signal?: AbortSignal,
    ) => {
      setOrdersError("");

      try {
        const records = (
          await getRazorpayTestCheckoutOrders(
            signal,
          )
        );

        setOrders(records);
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        setOrdersError(
          error instanceof Error
            ? error.message
            : (
                "Unable to load " +
                "provider orders"
              ),
        );
      } finally {
        if (!signal?.aborted) {
          setOrdersLoading(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    const controller =
      new AbortController();

    void loadOrders(
      controller.signal,
    );

    return () => {
      controller.abort();
    };
  }, [loadOrders]);

  const synchroniseProviderOutcome =
    useCallback(
      async (
        providerOrderId: string,
      ) => {
        if (
          reconciliationInFlightRef.current
        ) {
          return;
        }

        reconciliationInFlightRef.current =
          true;

        try {
          const reconciledOrder = (
            await reconcileRazorpayTestCheckoutOrder(
              providerOrderId,
            )
          );

          setOrders(
            (currentOrders) => [
              reconciledOrder,
              ...currentOrders.filter(
                (order) =>
                  order.id !==
                  reconciledOrder.id,
              ),
            ],
          );

          const outcome = (
            reconciledOrder
              .outcome_status
              .toLowerCase()
          );

          if (outcome === "paid") {
            setConfirmedOrder(
              reconciledOrder,
            );

            setErrorMessage("");

            setPhase(
              "provider_confirmed",
            );
          } else if (
            outcome === "failed"
          ) {
            setConfirmedOrder(
              reconciledOrder,
            );

            setErrorMessage(
              "Razorpay confirmed that " +
              "the latest Test Mode " +
              "payment attempt failed.",
            );

            setPhase(
              "payment_failed",
            );
          }

          await (
            onProviderActivityRef
              .current?.()
          );
        } catch (error) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : (
                  "Unable to check " +
                  "Razorpay provider status"
                ),
          );
        } finally {
          reconciliationInFlightRef.current =
            false;
        }
      },
      [],
    );

  useEffect(() => {
    if (
      phase !==
        "waiting_for_webhook" ||
      activeOrder === null
    ) {
      return undefined;
    }

    void synchroniseProviderOutcome(
      activeOrder.provider_order_id,
    );

    const intervalId =
      window.setInterval(
        () => {
          void synchroniseProviderOutcome(
            activeOrder
              .provider_order_id,
          );
        },
        3_000,
      );

    return () => {
      window.clearInterval(
        intervalId,
      );
    };
  }, [
    activeOrder,
    phase,
    synchroniseProviderOutcome,
  ]);

  const handleCheckout = async () => {
    if (
      !amountIsValid ||
      checkoutBusy
    ) {
      return;
    }

    setErrorMessage("");
    setCheckoutResult(null);
    setActiveOrder(null);
    setConfirmedOrder(null);
    setPhase("creating_order");

    try {
      const order = (
        await createRazorpayTestCheckoutOrder({
          amountRupees:
            numericAmount,
          customerReference,
        })
      );

      setActiveOrder(order);
      setPhase("checkout_open");

      await loadOrders();

      const result = (
        await openRazorpayTestCheckout(
          order,
        )
      );

      setCheckoutResult(result);

      if (
  result.status ===
    "payment_submitted" ||
  result.status ===
    "payment_failed"
) {
  // Browser success/failure is provisional.
  // RecoverAI confirms the final result through the
  // authenticated Razorpay server reconciliation API.
  setPhase(
    "waiting_for_webhook",
  );
} else {
  setPhase("dismissed");
}

      await loadOrders();

      await (
        onProviderActivityRef
          .current?.()
      );
    } catch (error) {
      setPhase("error");

      setErrorMessage(
        error instanceof Error
          ? error.message
          : (
              "Unable to start " +
              "Razorpay Test Checkout"
            ),
      );
    }
  };

  const currentMessage = phaseMessage(
    phase,
    checkoutResult,
    confirmedOrder,
  );

  return (
    <section className="test-checkout-panel">
      <div className="test-checkout-heading">
        <div>
          <span className="test-checkout-eyebrow">
            Provider-generated live evidence
          </span>

          <h2>Razorpay Test Checkout</h2>

          <p>
            Create an actual Razorpay Test Mode
            order and generate provider-originated
            payment events without moving real money.
          </p>
        </div>

        <div className="test-checkout-safety-badge">
          <ShieldCheck size={17} />
          Test Mode · ₹0 real money
        </div>
      </div>

      <div className="test-checkout-grid">
        <article className="test-checkout-card test-checkout-card--form">
          <div className="test-checkout-card-title">
            <CreditCard size={19} />

            <div>
              <strong>
                Create provider order
              </strong>

              <span>
                Maximum demo amount ₹10,000
              </span>
            </div>
          </div>

          <label className="test-checkout-field">
            <span>
              Test amount (INR)
            </span>

            <div className="test-checkout-amount-input">
              <span>₹</span>

              <input
                type="number"
                min="1"
                max={
                  MAX_TEST_AMOUNT_RUPEES
                }
                step="0.01"
                value={amountRupees}
                disabled={checkoutBusy}
                onChange={(event) => {
                  setAmountRupees(
                    event.target.value,
                  );
                }}
              />
            </div>
          </label>

          <label className="test-checkout-field">
            <span>
              Opaque customer reference
            </span>

            <input
              type="text"
              maxLength={100}
              value={customerReference}
              disabled={checkoutBusy}
              onChange={(event) => {
                setCustomerReference(
                  event.target.value,
                );
              }}
            />

            <small>
              Use a demo identifier—not an
              email address or phone number.
            </small>
          </label>

          {!amountIsValid &&
            amountRupees !== "" && (
              <div className="test-checkout-inline-error">
                <TriangleAlert
                  size={15}
                />

                Amount must be between
                ₹1 and ₹10,000.
              </div>
            )}

          <button
            className="test-checkout-primary-button"
            type="button"
            disabled={
              !amountIsValid ||
              checkoutBusy
            }
            onClick={() =>
              void handleCheckout()
            }
          >
            {checkoutBusy ? (
              <LoaderCircle
                className="test-checkout-spinner"
                size={17}
              />
            ) : (
              <ExternalLink size={17} />
            )}

            {phase === "creating_order"
              ? (
                  "Creating provider " +
                  "order..."
                )
              : phase === "checkout_open"
                ? "Checkout open"
                : (
                    "Create and open " +
                    "Test Checkout"
                  )}
          </button>

          {(currentMessage ||
            errorMessage) && (
            <div
              className={
                `test-checkout-result ` +
                `test-checkout-result--${
                  phase === "error" ||
                  phase ===
                    "payment_failed"
                    ? "failure"
                    : phase ===
                        "provider_confirmed"
                      ? "success"
                      : phase ===
                          "waiting_for_webhook"
                        ? "waiting"
                        : "neutral"
                }`
              }
              role="status"
            >
              {phase === "error" ||
              phase ===
                "payment_failed" ? (
                <XCircle size={17} />
              ) : phase ===
                "waiting_for_webhook" ? (
                <Clock3 size={17} />
              ) : (
                <CheckCircle2
                  size={17}
                />
              )}

              <div>
                <strong>
                  {phase ===
                  "provider_confirmed"
                    ? (
                        "Provider " +
                        "confirmed paid"
                      )
                    : phase ===
                        "waiting_for_webhook"
                      ? (
                          "Browser " +
                          "response received"
                        )
                      : phase ===
                          "payment_failed"
                        ? (
                            "Test payment " +
                            "failed"
                          )
                        : phase === "error"
                          ? (
                              "Checkout could " +
                              "not start"
                            )
                          : "Checkout update"}
                </strong>

                <span>
                  {errorMessage ||
                    currentMessage}
                </span>
              </div>
            </div>
          )}

          {activeOrder && (
            <dl className="test-checkout-active-order">
              <div>
                <dt>Provider order</dt>

                <dd>
                  {
                    activeOrder
                      .provider_order_id
                  }
                </dd>
              </div>

              <div>
                <dt>
                  Provider generated
                </dt>

                <dd>Yes</dd>
              </div>

              <div>
                <dt>Real money</dt>
                <dd>No</dd>
              </div>
            </dl>
          )}
        </article>

        <article className="test-checkout-card test-checkout-card--orders">
          <div className="test-checkout-orders-header">
            <div className="test-checkout-card-title">
              <Clock3 size={19} />

              <div>
                <strong>
                  Recent provider orders
                </strong>

                <span>
                  Persisted RecoverAI
                  telemetry
                </span>
              </div>
            </div>

            <button
              className="test-checkout-refresh-button"
              type="button"
              aria-label={
                "Refresh Test Mode orders"
              }
              onClick={() =>
                void loadOrders()
              }
            >
              <RefreshCcw size={16} />
            </button>
          </div>

          {ordersLoading && (
            <div className="test-checkout-empty-state">
              <LoaderCircle
                className="test-checkout-spinner"
                size={20}
              />

              Loading provider orders...
            </div>
          )}

          {!ordersLoading &&
            ordersError && (
              <div className="test-checkout-empty-state test-checkout-empty-state--error">
                <TriangleAlert
                  size={19}
                />

                {ordersError}
              </div>
            )}

          {!ordersLoading &&
            !ordersError &&
            recentOrders.length === 0 && (
              <div className="test-checkout-empty-state">
                <CreditCard size={21} />

                No provider-generated
                orders yet.
              </div>
            )}

          {!ordersLoading &&
            !ordersError &&
            recentOrders.length > 0 && (
              <div className="test-checkout-order-list">
                {recentOrders.map(
                  (order) => (
                    <div
                      className="test-checkout-order-row"
                      key={order.id}
                    >
                      <div className="test-checkout-order-primary">
                        <strong>
                          {
                            order
                              .provider_order_id
                          }
                        </strong>

                        <span>
                          {formatDateTime(
                            order.created_at,
                          )}
                        </span>
                      </div>

                      <div className="test-checkout-order-amount">
                        <strong>
                          {formatMoney(
                            order
                              .amount_rupees,
                          )}
                        </strong>

                        <span>
                          {
                            order
                              .customer_reference ??
                            "No reference"
                          }
                        </span>
                      </div>

                      <span
                        className={
                          `test-checkout-status ` +
                          `test-checkout-status--${statusClass(
                            order,
                          )}`
                        }
                      >
                        {displayStatus(
                          order,
                        )}
                      </span>
                    </div>
                  ),
                )}
              </div>
            )}

          <div className="test-checkout-proof-note">
            <ShieldCheck size={17} />

            <p>
              A Checkout callback proves only
              that the browser received a
              response. RecoverAI confirms the
              final outcome from a signed
              Razorpay webhook or server-side
              reconciliation.
            </p>
          </div>
        </article>
      </div>
    </section>
  );
}