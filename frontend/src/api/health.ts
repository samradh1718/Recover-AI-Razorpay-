import { API_BASE_URL } from "./runtimeConfig";
export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  environment: string;
  razorpay_mode: string;
  dependencies: {
    database: "ok" | "unavailable";
    redis: "ok" | "unavailable";
  };
  timestamp: string;
};


export async function getHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetch(
    `${API_BASE_URL}/health`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      `Health request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<HealthResponse>;
}