export function expectArray(payload, message) {
  if (!Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload;
}

export function expectRecord(payload, message) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(message);
  }
  return payload;
}

export function parseNumericValue(value, fallback = 0) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
