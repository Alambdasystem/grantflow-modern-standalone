import { api } from "@/lib/api";

export const GRANTFLOW_QUERY_TIMEOUT_MS = 10_000;

export type QueryValidator<T> = (payload: unknown) => T;

export async function fetchGrantFlowQuery<T>(
  path: string,
  validate: QueryValidator<T>,
  options: { timeoutMs?: number } = {}
): Promise<T> {
  const response = await api.get(path, {
    timeout: options.timeoutMs ?? GRANTFLOW_QUERY_TIMEOUT_MS,
  });
  return validate(response.data);
}

export async function postGrantFlowQuery<T>(
  path: string,
  body: unknown,
  validate: QueryValidator<T>,
  options: { timeoutMs?: number } = {}
): Promise<T> {
  const response = await api.post(path, body, {
    timeout: options.timeoutMs ?? GRANTFLOW_QUERY_TIMEOUT_MS,
  });
  return validate(response.data);
}

export function expectArray(payload: unknown, message: string): unknown[] {
  if (!Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload;
}

export function expectRecord(
  payload: unknown,
  message: string
): Record<string, unknown> {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload as Record<string, unknown>;
}

export function parseNumericValue(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}