import { API_BASE_URL } from "./runtimeConfig";
export type PaymentEventResponse = {
  id: string;
  tenant_id: string;
  provider_event_id: string;
  event_type: string;
  provider_payment_id: string | null;
  provider_subscription_id: string | null;
  processing_status: string;
  processing_error: string | null;
  received_at: string;
  processed_at: string | null;
};



export async function getPaymentEvents(
  signal?: AbortSignal,
): Promise<PaymentEventResponse[]> {
  const response = await fetch(
    `${API_BASE_URL}/payment-events?offset=0&limit=100`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    },
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(
        "Payment Events read endpoint is not available yet.",
      );
    }

    throw new Error(
      `Payment events request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<PaymentEventResponse[]>;
}
