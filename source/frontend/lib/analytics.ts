import { expectArray, parseNumericValue } from "@/lib/query";

export interface PipelineDatum {
  status: string;
  count: number;
}

export function parseGrantPipeline(payload: unknown): PipelineDatum[] {
  const rows = expectArray(payload, "Analytics pipeline API returned an invalid response.");

  return rows
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    .map((item) => ({
      status: String(item.status || "unknown"),
      count: parseNumericValue(item.count),
    }));
}