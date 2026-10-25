import { expectArray, parseNumericValue } from "@/lib/query";

export interface ApplicationListItem {
  id: number;
  grant_id: number;
  organization_id?: number;
  applicant_id?: number;
  status: string;
  title?: string;
  amount_requested?: number;
  submission_date?: string;
  created_at?: string;
}

export function parseApplicationList(payload: unknown): ApplicationListItem[] {
  const apps = expectArray(payload, "Applications API returned an invalid response.");

  return apps
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    .map((item) => ({
      id: parseNumericValue(item.id),
      grant_id: parseNumericValue(item.grant_id),
      organization_id:
        item.organization_id === null || item.organization_id === undefined
          ? undefined
          : parseNumericValue(item.organization_id),
      applicant_id:
        item.applicant_id === null || item.applicant_id === undefined
          ? undefined
          : parseNumericValue(item.applicant_id),
      status: String(item.status || "unknown"),
      title: item.title ? String(item.title) : undefined,
      amount_requested:
        item.amount_requested === null || item.amount_requested === undefined
          ? undefined
          : parseNumericValue(item.amount_requested),
      submission_date: item.submission_date ? String(item.submission_date) : undefined,
      created_at: item.created_at ? String(item.created_at) : undefined,
    }))
    .filter((app) => app.id > 0 && app.grant_id > 0);
}