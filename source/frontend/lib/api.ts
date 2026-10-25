import axios from "axios";
import {
  GRANTFLOW_LOGIN_PATH,
  GRANTFLOW_TOKEN_KEY,
  clearGrantFlowBrowserState,
  isGrantFlowLoginPath,
  grantFlowLoginPath,
} from "@/lib/auth-session";

export const api = axios.create({
  // Ensure requests go through the Next.js app basePath (/gfm-app)
  // so rewrites can forward /api/* to the FastAPI backend.
  baseURL: "/gfm-app",
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: false,
});

// Keep older feature callers on the same central-token/interceptor path.
export async function apiFetch(path: string, options: RequestInit = {}) {
  const headers = Object.fromEntries(new Headers(options.headers).entries());
  const response = await api.request({
    url: path, method: options.method || 'GET', data: options.body, headers,
    signal: options.signal || undefined,
  });
  return response.data;
}

// Attach JWT token from localStorage if present
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem(GRANTFLOW_TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle 401 → redirect to /login (Next applies the configured basePath)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      clearGrantFlowBrowserState({
        localStorage: window.localStorage,
        sessionStorage: window.sessionStorage,
      });
      if (!isGrantFlowLoginPath(window.location.pathname)) {
        window.location.replace(grantFlowLoginPath(window.location.pathname + window.location.search));
      }
    }
    return Promise.reject(err);
  }
);
