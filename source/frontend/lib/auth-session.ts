export const GRANTFLOW_LOGIN_PATH = "/auth/login?next=%2Fgfm-app%2Fdashboard";
export const GRANTFLOW_TOKEN_KEY = "authToken";
const GRANTFLOW_STORAGE_PREFIX = "gfm_";

export function isGrantFlowPublicPath(pathname?: string | null): boolean {
  return /^\/(?:gfm-app\/)?give\/[A-Za-z0-9_-]+\/?$/.test(pathname || "");
}

export type StorageLike = Pick<Storage, "getItem" | "removeItem" | "key" | "length">;
type LocationLike = Pick<Location, "replace"> | { replace: (path: string) => void };
type QueryClientLike = { clear?: () => void };

function isGrantFlowStorageKey(key: string | null | undefined): boolean {
  return Boolean(key && key.startsWith(GRANTFLOW_STORAGE_PREFIX));
}

function removeGrantFlowKeys(storage?: StorageLike | null) {
  if (!storage) {
    return;
  }

  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (isGrantFlowStorageKey(key)) {
      keys.push(String(key));
    }
  }

  if (!keys.includes(GRANTFLOW_TOKEN_KEY)) {
    keys.push(GRANTFLOW_TOKEN_KEY);
  }

  keys.forEach((key) => storage.removeItem(key));
}

export function isGrantFlowLoginPath(pathname?: string | null): boolean {
  return pathname === "/login" || pathname === "/gfm-app/login" || pathname === "/auth/login";
}

export function hasGrantFlowToken(storage?: StorageLike | null): boolean {
  storage?.removeItem("gfm_token");
  return Boolean(storage?.getItem(GRANTFLOW_TOKEN_KEY));
}

export function clearGrantFlowBrowserState(options: {
  localStorage?: StorageLike | null;
  sessionStorage?: StorageLike | null;
  queryClient?: QueryClientLike | null;
} = {}) {
  removeGrantFlowKeys(options.localStorage);
  removeGrantFlowKeys(options.sessionStorage);
  options.queryClient?.clear?.();
}

export function grantFlowLoginPath(destination?: string | null): string {
  if (!destination || destination === '/dashboard' || destination === '/gfm-app/dashboard') return GRANTFLOW_LOGIN_PATH;
  const path = destination.startsWith('/gfm-app/') ? destination : '/gfm-app' + destination;
  if (!path.startsWith('/gfm-app/') || /[\\\r\n]/.test(path) || path.includes('//') || path.includes('..')) return GRANTFLOW_LOGIN_PATH;
  return '/auth/login?next=' + encodeURIComponent(path);
}

export function redirectToGrantFlowLogin(location?: LocationLike | null, destination?: string | null): string {
  const path = grantFlowLoginPath(destination);
  location?.replace(path);
  return path;
}

export function logoutGrantFlowClient(options: {
  localStorage?: StorageLike | null;
  sessionStorage?: StorageLike | null;
  queryClient?: QueryClientLike | null;
  location?: LocationLike | null;
} = {}): string {
  clearGrantFlowBrowserState(options);
  return redirectToGrantFlowLogin(options.location);
}

export function requireGrantFlowAuth(options: {
  pathname?: string | null;
  loggingOut?: boolean;
  localStorage?: StorageLike | null;
  location?: LocationLike | null;
}): boolean {
  if (options.loggingOut || isGrantFlowLoginPath(options.pathname) || isGrantFlowPublicPath(options.pathname)) {
    return false;
  }

  if (hasGrantFlowToken(options.localStorage)) {
    return false;
  }

  redirectToGrantFlowLogin(options.location, options.pathname);
  return true;
}
