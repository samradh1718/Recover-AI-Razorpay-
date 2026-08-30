import {
  API_BASE_URL,
  TENANT_ID,
} from "./runtimeConfig";


export type RazorpayTestCheckoutOrder = {
  checkout_session_id: string;
  provider_order_id: string;
  provider_order_status: string;
  razorpay_key_id: string;
  amount_rupees: string;
  amount_paise: number;
  currency: "INR";
  receipt: string;
  data_source: "razorpay_test_checkout";
  provider_generated: true;
  real_money: false;
  created_at: string;
};


export type RazorpayTestOrderRecord = {
  id: string;
  tenant_id: string;
  provider: string;
  provider_order_id: string;
  receipt: string;
  amount_rupees: string;
  currency: string;
  provider_order_status: string;
  data_source: "razorpay_test_checkout";
  provider_generated: boolean;
  real_money: boolean;
  customer_reference: string | null;
  provider_payment_id: string | null;
  latest_payment_event_id: string | null;
  outcome_status: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};


type CreateTestCheckoutOrderInput = {
  amountRupees: number;
  customerReference?: string;
  signal?: AbortSignal;
};


type ApiErrorPayload = {
  detail?: unknown;
};


function apiErrorMessage(
  payload: ApiErrorPayload | null,
  fallback: string,
): string {
  const detail = payload?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const firstError = detail[0];

    if (
      typeof firstError === "object" &&
      firstError !== null &&
      "msg" in firstError &&
      typeof firstError.msg === "string"
    ) {
      return firstError.msg;
    }
  }

  return fallback;
}


async function parseErrorPayload(
  response: Response,
): Promise<ApiErrorPayload | null> {
  try {
    const payload: unknown = await response.json();

    if (
      typeof payload === "object" &&
      payload !== null
    ) {
      return payload as ApiErrorPayload;
    }
  } catch {
    return null;
  }

  return null;
}


export async function createRazorpayTestCheckoutOrder({
  amountRupees,
  customerReference,
  signal,
}: CreateTestCheckoutOrderInput): Promise<RazorpayTestCheckoutOrder> {
  const normalizedCustomerReference = (
    customerReference?.trim() ?? ""
  );

  const response = await fetch(
    `${API_BASE_URL}/test-checkout/orders`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        amount_rupees: amountRupees,
        currency: "INR",
        customer_reference:
          normalizedCustomerReference || null,
      }),
      signal,
    },
  );

  if (!response.ok) {
    const payload = await parseErrorPayload(response);

    throw new Error(
      apiErrorMessage(
        payload,
        `Unable to create a Test Mode order (HTTP ${response.status})`,
      ),
    );
  }

  return response.json() as Promise<RazorpayTestCheckoutOrder>;
}


export async function getRazorpayTestCheckoutOrders(
  signal?: AbortSignal,
): Promise<RazorpayTestOrderRecord[]> {
  const query = new URLSearchParams({
    tenant_id: TENANT_ID,
    offset: "0",
    limit: "100",
  });

  const response = await fetch(
    `${API_BASE_URL}/test-checkout/orders?${query.toString()}`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      signal,
    },
  );

  if (!response.ok) {
    const payload = await parseErrorPayload(response);

    throw new Error(
      apiErrorMessage(
        payload,
        `Unable to load Test Mode orders (HTTP ${response.status})`,
      ),
    );
  }

  return response.json() as Promise<RazorpayTestOrderRecord[]>;
}


export async function reconcileRazorpayTestCheckoutOrder(
  providerOrderId: string,
  signal?: AbortSignal,
): Promise<RazorpayTestOrderRecord> {
  const cleanProviderOrderId = providerOrderId.trim();

  if (!cleanProviderOrderId.startsWith("order_")) {
    throw new Error(
      "A valid Razorpay provider order ID is required",
    );
  }

  const query = new URLSearchParams({
    tenant_id: TENANT_ID,
  });

  const response = await fetch(
    (
      `${API_BASE_URL}/test-checkout/orders/` +
      `${encodeURIComponent(cleanProviderOrderId)}/` +
      `reconcile?${query.toString()}`
    ),
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      signal,
    },
  );

  if (!response.ok) {
    const payload = await parseErrorPayload(response);

    throw new Error(
      apiErrorMessage(
        payload,
        `Unable to reconcile the Test Mode order (HTTP ${response.status})`,
      ),
    );
  }

  return response.json() as Promise<RazorpayTestOrderRecord>;
}