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
  withCredentials: true,
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
    const csrf = document.cookie.match(/(?:^|; )(__Host-gfm_csrf|gfm_csrf)=([^;]*)/);
    if (csrf) config.headers['X-CSRF-Token'] = decodeURIComponent(csrf[2]);
  }
  return config;
});

// Handle 401 → redirect to /login (Next applies the configured basePath)
let refreshing: Promise<unknown> | null = null;
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      const config=err.config;
      if (localStorage.getItem('gfm_session_hint') && !config?._gfmRetried && !String(config?.url).startsWith('/api/auth/')) {
        const csrf=document.cookie.match(/(?:^|; )(__Host-gfm_csrf|gfm_csrf)=([^;]*)/);
        config._gfmRetried=true;
        try {
          if (!refreshing) refreshing=axios.post('/gfm-app/api/auth/refresh',{}, {withCredentials:true,headers:{'X-CSRF-Token':csrf?decodeURIComponent(csrf[2]):''}}).finally(()=>{refreshing=null;});
          await refreshing;
          return api.request(config);
        } catch { /* Clear the UI hint; server remains authoritative. */ }
      }
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
