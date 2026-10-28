import type { QueryClient } from '@tanstack/react-query';

export function refreshApplicationViews(client: QueryClient, id?: number) {
  const keys: unknown[][] = [['applications'], ['dashboard-stats'], ['grant-pipeline'], ['renewals']];
  if (id !== undefined) keys.push(['application', id], ['workflow', id], ['application-readiness', id], ['reviews', id]);
  return Promise.all(keys.map(queryKey => client.invalidateQueries({queryKey})));
}
