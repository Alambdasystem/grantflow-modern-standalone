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
