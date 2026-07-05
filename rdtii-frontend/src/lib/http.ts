import { getStoredToken } from "../hooks/useAuth";

export function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function truncateMessage(value: string, maxLength = 300): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength).trimEnd()}...`;
}

export async function readErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  const rawPayload = await response.text();
  const payload = rawPayload ? safeJsonParse(rawPayload) : null;

  if (isRecord(payload)) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return formatValidationErrors(detail);
    if (isRecord(detail) && typeof detail.message === "string")
      return detail.message;
  }

  if (typeof payload === "string") return payload;
  return rawPayload ? truncateMessage(rawPayload) : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function formatValidationErrors(detail: unknown[]): string {
  const messages = detail
    .map((item) => {
      if (!isRecord(item)) return "";
      const message = typeof item.msg === "string" ? item.msg : "";
      const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
      if (!message) return "";
      return location ? `${location}: ${message}` : message;
    })
    .filter(Boolean);
  return messages.length ? messages.join("; ") : "Request validation failed.";
}
