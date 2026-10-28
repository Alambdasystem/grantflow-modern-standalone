export function requestedAmountError(value: string): string | undefined {
  if (!value.trim()) return undefined;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return 'Enter a valid requested amount.';
  if (amount < 0) return 'Requested amount must be zero or greater.';
  return undefined;
}

export function applicationError(error: unknown): {message: string; fields: Record<string, string>} {
  const detail = (error as {response?: {data?: {detail?: unknown}}})?.response?.data?.detail;
  const fields: Record<string, string> = {};
  if (Array.isArray(detail)) {
    for (const issue of detail) {
      if (!issue || !Array.isArray(issue.loc) || typeof issue.msg !== 'string') continue;
      const key = issue.loc.find((part: unknown) => ['grant_id', 'title', 'amount_requested'].includes(String(part)));
      if (key) fields[String(key)] = issue.msg;
    }
    return {message: Object.keys(fields).length ? 'Check the highlighted application fields.' : 'Check your application fields and try again.', fields};
  }
  return {message: typeof detail === 'string' ? detail : 'Could not save the application. Your entries are retained; please retry.', fields};
}
