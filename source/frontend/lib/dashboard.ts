import { expectRecord, parseNumericValue } from "@/lib/query";

export interface DashboardStats {
  total_grants: number;
  active_grants: number;
  total_applications: number;
  submitted_applications: number;
  approved_applications: number;
  pending_renewals: number;
  automation_jobs_running: number;
  total_awarded: number;
  success_rate: number | null;
}

export function parseDashboardStats(payload: unknown): DashboardStats {
  const record = expectRecord(
    payload,
    "Dashboard summary API returned an invalid response."
  );

  const successRateRaw = record.success_rate;
  const successRate =
    successRateRaw === null || successRateRaw === undefined
      ? null
      : parseNumericValue(successRateRaw, 0);

  return {
    total_grants: parseNumericValue(record.total_grants),
    active_grants: parseNumericValue(record.active_grants),
    total_applications: parseNumericValue(record.total_applications),
    submitted_applications: parseNumericValue(record.submitted_applications),
    approved_applications: parseNumericValue(record.approved_applications),
    pending_renewals: parseNumericValue(record.pending_renewals),
    automation_jobs_running: parseNumericValue(record.automation_jobs_running),
    total_awarded: parseNumericValue(record.total_awarded),
    success_rate: successRate,
  };
}

export function formatSuccessRate(successRate: number | null | undefined): string {
  return typeof successRate === "number" ? `${successRate}%` : "N/A";
}

export function formatAwardedAmount(totalAwarded: number | null | undefined, digits = 0): string {
  const safeAmount = totalAwarded ?? 0;
  return `$${(safeAmount / 1000).toFixed(digits)}k`;
}