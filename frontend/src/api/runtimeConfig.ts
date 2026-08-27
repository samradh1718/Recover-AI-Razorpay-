function requiredEnvironmentValue(
  name: string,
  value: string | undefined,
): string {
  const normalizedValue = value?.trim();

  if (!normalizedValue) {
    throw new Error(
      `${name} must be configured in the frontend environment`,
    );
  }

  return normalizedValue;
}


function normalizeApiBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}


export const API_BASE_URL = normalizeApiBaseUrl(
  requiredEnvironmentValue(
    "VITE_API_BASE_URL",
    import.meta.env.VITE_API_BASE_URL,
  ),
);


export const TENANT_ID = requiredEnvironmentValue(
  "VITE_TENANT_ID",
  import.meta.env.VITE_TENANT_ID,
);