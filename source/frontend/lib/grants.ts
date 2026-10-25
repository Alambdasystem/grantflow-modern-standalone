import { expectArray, parseNumericValue } from "@/lib/query";

export interface GrantListItem {
  id: number;
  title: string;
  funding_agency?: string;
  amount?: number;
  deadline_str?: string;
  category?: string;
  status: string;
  ai_match_score?: number;
  source_url?: string;
  ai_summary?: string;
  eligibility?: string;
}

export function parseGrantList(payload: unknown): GrantListItem[] {
  const grants = expectArray(payload, "Grant discovery API returned an invalid response.");

  return grants
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    .map((item) => ({
      id: parseNumericValue(item.id),
      title: String(item.title || "Untitled Grant"),
      funding_agency: item.funding_agency ? String(item.funding_agency) : undefined,
      amount: item.amount === null || item.amount === undefined ? undefined : parseNumericValue(item.amount),
      deadline_str: item.deadline_str ? String(item.deadline_str) : undefined,
      category: item.category ? String(item.category) : undefined,
      status: String(item.status || "unknown"),
      ai_match_score:
        item.ai_match_score === null || item.ai_match_score === undefined
          ? undefined
          : parseNumericValue(item.ai_match_score),
      source_url: item.source_url ? String(item.source_url) : undefined,
      ai_summary: item.ai_summary ? String(item.ai_summary) : undefined,
      eligibility: item.eligibility ? String(item.eligibility) : undefined,
    }))
    .filter((grant) => grant.id > 0);
}

export interface GrantOption {
  id: number;
  title: string;
}

export function parseGrantOptions(payload: unknown): GrantOption[] {
  return parseGrantList(payload).map((grant) => ({ id: grant.id, title: grant.title }));
}