"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Link2, CheckCircle2, XCircle, Clock, RefreshCw, LogIn,
  KeyRound, Eye, EyeOff, Trash2, ExternalLink, AlertCircle,
  Globe, ShieldCheck, Plus, ChevronDown, ChevronUp, Download,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

interface PortalCredential {
  id: number;
  portal_key: string;
  portal_name: string;
  portal_url: string | null;
  credential_type: string;
  has_credentials: boolean;
  username: string | null;
  is_connected: boolean;
  last_login_at: string | null;
  last_login_status: string | null;
  last_job_id: number | null;
  notes: string | null;
}

interface ProviderEntry {
  key: string;
  name: string;
  url: string;
  register_url?: string;
  credential_type: string;
  description: string;
  requirements: string[];
  credential: PortalCredential | null;
}

function StatusBadge({ cred }: { cred: PortalCredential | null }) {
  if (!cred) return <Badge variant="outline" className="border-zinc-600/40 bg-zinc-700/20 text-zinc-400">Not configured</Badge>;
  if (cred.is_connected) return <Badge variant="outline" className="border-emerald-400/40 bg-emerald-500/10 text-emerald-200">Connected</Badge>;
  if (cred.last_login_status === "pending") return <Badge variant="outline" className="border-amber-400/40 bg-amber-500/10 text-amber-200">Connecting…</Badge>;
  if (cred.last_login_status === "failed") return <Badge variant="outline" className="border-rose-400/40 bg-rose-500/10 text-rose-200">Failed</Badge>;
  if (cred.has_credentials) return <Badge variant="outline" className="border-cyan-400/40 bg-cyan-500/10 text-cyan-200">Credentials saved</Badge>;
  return <Badge variant="outline" className="border-zinc-600/40 bg-zinc-700/20 text-zinc-400">Not configured</Badge>;
}

function ProviderCard({ entry, onRefresh }: { entry: ProviderEntry; onRefresh: () => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [username, setUsername] = useState(entry.credential?.username || "");
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [twoFaCode, setTwoFaCode] = useState("");
  const isApiKey = entry.credential_type === "api_key";
  const activeJobId = entry.credential?.last_job_id ?? null;

  // Poll the active job when it's running or awaiting 2FA
  const { data: activeJob } = useQuery({
    queryKey: ["provider-job", activeJobId],
    queryFn: () => api.get(`/api/automation/jobs/${activeJobId}`).then((r) => r.data),
    enabled: !!activeJobId,
    refetchInterval: (q) => {
      const s = (q.state.data as { status?: string } | undefined)?.status;
      return s === "running" || s === "queued" || s === "awaiting_approval" ? 2000 : false;
    },
  });

  const [syncJobId, setSyncJobId] = useState<number | null>(null);

  const syncWorkspace = useMutation({
    mutationFn: () => api.post("/api/workspace/grants-gov/sync"),
    onSuccess: (res) => {
      toast.success("Workspace sync started");
      setSyncJobId(res.data.job_id);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Sync failed";
      toast.error(msg);
    },
  });

  const { data: syncJob } = useQuery({
    queryKey: ["workspace-sync-job", syncJobId],
    queryFn: () => api.get(`/api/workspace/grants-gov/sync/${syncJobId}`).then((r) => r.data),
    enabled: !!syncJobId,
    refetchInterval: (q) => {
      const s = (q.state.data as { status?: string } | undefined)?.status;
      return s === "running" || s === "queued" ? 2000 : false;
    },
  });

  const save = useMutation({
    mutationFn: () => api.put(`/api/providers/${entry.key}`, {
      portal_key: entry.key,
      username: isApiKey ? undefined : username,
      password: isApiKey ? undefined : (password || undefined),
      api_key: isApiKey ? (apiKey || undefined) : undefined,
    }),
    onSuccess: () => {
      toast.success("Credentials saved");
      setPassword("");
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["providers"] });
    },
    onError: () => toast.error("Failed to save credentials"),
  });

  const connect = useMutation({
    mutationFn: () => api.post(`/api/providers/${entry.key}/connect`),
    onSuccess: (res) => {
      toast.success(`Login job #${res.data.job_id} started`);
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["provider-job", res.data.job_id] });
      onRefresh();
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Connection failed";
      toast.error(msg);
    },
  });

  const submit2fa = useMutation({
    mutationFn: (code: string) => api.post(`/api/providers/jobs/${activeJobId}/2fa`, { code }),
    onSuccess: () => {
      toast.success("2FA code sent — waiting for login to complete");
      setTwoFaCode("");
      qc.invalidateQueries({ queryKey: ["provider-job", activeJobId] });
    },
    onError: () => toast.error("Failed to submit 2FA code"),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/api/providers/${entry.key}`),
    onSuccess: () => {
      toast.success("Credentials removed");
      qc.invalidateQueries({ queryKey: ["providers"] });
    },
    onError: () => toast.error("Failed to remove credentials"),
  });

  const cred = entry.credential;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl border border-cyan-900/40 overflow-hidden"
    >
      {/* Header row */}
      <div className="p-5 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-400/20 flex items-center justify-center shrink-0 mt-0.5">
            <Globe className="w-5 h-5 text-cyan-300" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-zinc-100 font-medium">{entry.name}</span>
              <StatusBadge cred={cred} />
            </div>
            <p className="text-zinc-400 text-xs mt-0.5 leading-relaxed">{entry.description}</p>
            {cred?.last_login_at && (
              <p className="text-zinc-500 text-xs mt-0.5">
                Last {cred.last_login_status === "success" ? "connected" : "attempted"}:{" "}
                {new Date(cred.last_login_at).toLocaleString()}
              </p>
            )}

            {/* Live job status banner */}
            {activeJob && ["running", "queued", "awaiting_approval"].includes(activeJob.status) && (
              <div className={`mt-2 rounded-xl border px-3 py-2.5 space-y-2 ${activeJob.status === "awaiting_approval" ? "border-amber-400/30 bg-amber-500/10" : "border-cyan-400/20 bg-cyan-500/8"}`}>
                <div className="flex items-center gap-2">
                  <RefreshCw className="w-3.5 h-3.5 text-cyan-300 animate-spin shrink-0" />
                  <p className="text-xs text-zinc-200">{activeJob.current_step || "Running…"}</p>
                  <span className="ml-auto text-xs text-zinc-400">{activeJob.progress_pct}%</span>
                </div>
                <div className="w-full bg-zinc-800 rounded-full h-1">
                  <div className="h-1 rounded-full bg-cyan-400 transition-all duration-700" style={{ width: `${activeJob.progress_pct}%` }} />
                </div>

                {/* Device auth info (new browser — only show while no 2FA yet) */}
                {activeJob.status === "awaiting_approval" && activeJob.result?.requires_device_auth && !activeJob.result?.requires_2fa && (
                  <div className="pt-1 space-y-1.5">
                    <p className="text-xs text-amber-200 font-medium flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      New device — browser window opened on your desktop
                    </p>
                    <p className="text-[11px] text-zinc-400 leading-relaxed">
                      Login.gov doesn&apos;t recognize this device yet. A visible Chrome window opened — complete the security check there. GrantFlow will continue automatically once done.
                    </p>
                    <p className="text-[11px] text-zinc-500">One-time step — future logins will be fully automated.</p>
                  </div>
                )}

                {/* 2FA prompt — shown when 2FA is required (even if device auth was also needed) */}
                {activeJob.status === "awaiting_approval" && activeJob.result?.requires_2fa && (
                  <div className="pt-1 space-y-2">
                    <p className="text-xs text-amber-200 font-medium">
                      {activeJob.result?.requires_device_auth
                        ? "Browser opened & Login.gov is asking for 2FA"
                        : "Login.gov is asking for a 2-factor authentication code"}
                    </p>
                    <p className="text-[11px] text-zinc-400">
                      Open your Login.gov authenticator app and enter the 6-digit code below.
                      {activeJob.result?.requires_device_auth && " The Chrome window on your desktop is waiting."}
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        inputMode="numeric"
                        maxLength={8}
                        placeholder="Enter 6-digit code"
                        value={twoFaCode}
                        onChange={(e) => setTwoFaCode(e.target.value.replace(/\D/g, ""))}
                        className="flex-1 px-3 py-1.5 rounded-lg bg-[#0d2635]/80 border border-amber-400/30 text-zinc-100 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-amber-400/60 tracking-widest font-mono"
                      />
                      <Button
                        onClick={() => submit2fa.mutate(twoFaCode)}
                        disabled={twoFaCode.length < 6 || submit2fa.isPending}
                        size="sm"
                        className="h-9 rounded-lg bg-amber-500 hover:bg-amber-400 text-[#241500] font-semibold text-xs px-4"
                      >
                        {submit2fa.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : "Submit"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Completed/failed login job result */}
            {activeJob && activeJob.status === "completed" && (
              <p className="text-xs text-emerald-300 mt-1 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Login successful
              </p>
            )}
            {activeJob && activeJob.status === "failed" && (
              <p className="text-xs text-rose-300 mt-1 truncate">
                Error: {activeJob.error_message || (activeJob.result as { error?: string } | null)?.error || "Login failed"}
              </p>
            )}

            {/* Workspace sync result banner */}
            {syncJob && syncJob.status === "running" && (
              <div className="mt-1 flex items-center gap-1.5 text-xs text-emerald-200">
                <RefreshCw className="w-3 h-3 animate-spin shrink-0" />
                {syncJob.current_step || "Syncing workspace…"} ({syncJob.progress_pct}%)
              </div>
            )}
            {syncJob && syncJob.status === "completed" && (
              <div className="mt-1 text-xs text-emerald-300 flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3 shrink-0" />
                Workspace synced — {(syncJob.result as { created?: number; updated?: number; total_found?: number } | null)?.total_found ?? 0} applications found
                {((syncJob.result as { created?: number } | null)?.created ?? 0) > 0 && (
                  <span className="text-zinc-400">· {(syncJob.result as { created?: number } | null)?.created} new</span>
                )}
              </div>
            )}
            {syncJob && syncJob.status === "failed" && (
              <p className="mt-1 text-xs text-rose-300 truncate">Sync error: {syncJob.error_message}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Sync Workspace — grants.gov only, when connected */}
          {entry.key === "grants_gov" && cred?.is_connected && (
            <Button
              onClick={() => syncWorkspace.mutate()}
              disabled={syncWorkspace.isPending || syncJob?.status === "running"}
              size="sm"
              variant="outline"
              className="h-8 rounded-xl border-emerald-700/50 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 text-xs"
            >
              {syncWorkspace.isPending || syncJob?.status === "running"
                ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                : <Download className="w-3.5 h-3.5" />}
              {syncWorkspace.isPending || syncJob?.status === "running" ? "Syncing…" : "Sync Workspace"}
            </Button>
          )}
          {cred?.has_credentials && (
            <Button
              onClick={() => connect.mutate()}
              disabled={connect.isPending}
              size="sm"
              className="h-8 rounded-xl bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-[#02131b] font-semibold text-xs"
            >
              {connect.isPending
                ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                : <LogIn className="w-3.5 h-3.5" />}
              {connect.isPending ? "Connecting…" : "Connect"}
            </Button>
          )}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="h-8 w-8 rounded-xl border border-cyan-900/40 bg-[#0d2635]/60 flex items-center justify-center text-zinc-400 hover:text-cyan-200 transition"
          >
            {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Expanded credential form */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-cyan-900/30"
          >
            <div className="p-5 space-y-4">
              {/* Requirements */}
              {entry.requirements.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-400 font-medium mb-1.5 uppercase tracking-wide">Prerequisites</p>
                  <ul className="space-y-1">
                    {entry.requirements.map((r) => (
                      <li key={r} className="flex items-center gap-2 text-xs text-zinc-300">
                        <ShieldCheck className="w-3.5 h-3.5 text-amber-300 shrink-0" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Credential form */}
              <div className="space-y-3">
                <p className="text-xs text-zinc-400 font-medium uppercase tracking-wide">
                  {isApiKey ? "API Key" : "Login Credentials"}
                </p>

                {isApiKey ? (
                  <div className="relative">
                    <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400" />
                    <input
                      type={showPw ? "text" : "password"}
                      placeholder="Paste API key…"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      className="w-full pl-9 pr-10 py-2 rounded-xl bg-[#0d2635]/80 border border-cyan-900/40 text-zinc-100 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500/60"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPw((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                    >
                      {showPw ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                ) : (
                  <>
                    <input
                      type="text"
                      placeholder="Username or email"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      autoComplete="off"
                      className="w-full px-3 py-2 rounded-xl bg-[#0d2635]/80 border border-cyan-900/40 text-zinc-100 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500/60"
                    />
                    <div className="relative">
                      <input
                        type={showPw ? "text" : "password"}
                        placeholder={cred?.has_credentials ? "New password (leave blank to keep current)" : "Password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="new-password"
                        className="w-full px-3 pr-10 py-2 rounded-xl bg-[#0d2635]/80 border border-cyan-900/40 text-zinc-100 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500/60"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPw((v) => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                      >
                        {showPw ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button
                  onClick={() => save.mutate()}
                  disabled={save.isPending || (!username && !password && !apiKey)}
                  className="h-8 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#02131b] font-semibold text-xs"
                >
                  {save.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  {save.isPending ? "Saving…" : "Save Credentials"}
                </Button>

                {cred?.has_credentials && (
                  <Button
                    onClick={() => connect.mutate()}
                    disabled={connect.isPending}
                    className="h-8 rounded-xl bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-[#02131b] font-semibold text-xs"
                  >
                    {connect.isPending
                      ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      : <LogIn className="w-3.5 h-3.5" />}
                    Connect with OpenClaw
                  </Button>
                )}

                {entry.register_url && (
                  <a
                    href={entry.register_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xl border border-cyan-700/40 bg-[#0d2635]/60 text-cyan-200 text-xs hover:bg-cyan-500/10 transition"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    Register / Sign Up
                  </a>
                )}

                {cred && (
                  <Button
                    onClick={() => remove.mutate()}
                    disabled={remove.isPending}
                    variant="outline"
                    className="h-8 rounded-xl border-rose-500/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20 text-xs ml-auto"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Remove
                  </Button>
                )}
              </div>

              {/* Last job link */}
              {cred?.last_job_id && (
                <div className="flex items-center gap-2 text-xs text-zinc-500 pt-1">
                  <Clock className="w-3.5 h-3.5" />
                  Last login job:{" "}
                  <Link
                    href="/automation"
                    className="text-cyan-400 hover:text-cyan-200 underline"
                  >
                    Job #{cred.last_job_id} in Automation Center
                  </Link>
                </div>
              )}

              {/* OpenClaw info */}
              <div className="rounded-xl border border-cyan-900/30 bg-cyan-500/5 px-4 py-3 mt-2">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-3.5 h-3.5 text-cyan-300 shrink-0 mt-0.5" />
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    <span className="text-cyan-200 font-medium">OpenClaw</span> is a Playwright-based browser agent that logs in to grant portals on your behalf using a trusted Chrome profile. It stores session cookies so future requests can reuse the session. Your credentials are base64-stored in the local GrantFlow database — not transmitted externally.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function ProvidersPage() {
  const qc = useQueryClient();
  const me = useQuery<{role:string}>({queryKey:["me"],queryFn:()=>api.get("/api/auth/me").then(r=>r.data)});

  const { data: providers = [], isLoading, isError, refetch } = useQuery<ProviderEntry[]>({
    enabled: me.data?.role === "admin",
    queryKey: ["providers"],
    queryFn: () => api.get("/api/providers").then((r) => r.data),
    retry: 1,
  });

  const connected = providers.filter((p) => p.credential?.is_connected).length;
  const configured = providers.filter((p) => p.credential?.has_credentials).length;

  if (me.isLoading) return <p className="p-6">Checking account permissions...</p>;
  if (me.data?.role !== "admin") return <p role="alert" className="p-6">Provider management requires administrator access. Your current role does not permit viewing or changing provider credentials.</p>;
  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl border border-cyan-900/40 p-5 sm:p-6 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_8%_20%,rgba(99,102,241,0.22),transparent_30%),radial-gradient(circle_at_85%_15%,rgba(16,185,129,0.14),transparent_36%)]" />
        <div className="relative flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div className="space-y-1">
            <Badge variant="outline" className="border-cyan-300/50 bg-cyan-500/10 text-cyan-100">
              {connected} Connected · {configured} Configured
            </Badge>
            <h1 className="text-3xl font-semibold text-zinc-50">Portal Providers</h1>
            <p className="text-zinc-300 text-sm">
              Add your grant portal logins. OpenClaw (Playwright) authenticates on your behalf so GrantFlow can access and autofill application portals.
            </p>
          </div>
          <Button
            onClick={() => refetch()}
            variant="outline"
            className="h-9 border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </Button>
        </div>
      </motion.div>

      {/* Status summary */}
      {providers.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Total portals", value: providers.length, icon: <Globe className="w-4 h-4 text-cyan-300" /> },
            { label: "Credentials saved", value: configured, icon: <KeyRound className="w-4 h-4 text-amber-300" /> },
            { label: "Connected", value: connected, icon: <CheckCircle2 className="w-4 h-4 text-emerald-300" /> },
          ].map((stat) => (
            <div key={stat.label} className="rounded-xl border border-cyan-900/40 bg-[#0d2635]/80 p-3 flex items-center gap-3">
              {stat.icon}
              <div>
                <div className="text-xs text-zinc-400">{stat.label}</div>
                <div className="text-lg font-semibold text-zinc-100">{stat.value}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* What is OpenClaw */}
      <div className="rounded-2xl border border-amber-400/20 bg-amber-500/5 p-4 flex items-start gap-3">
        <Link2 className="w-5 h-5 text-amber-300 shrink-0 mt-0.5" />
        <div className="text-sm space-y-1">
          <p className="text-amber-100 font-medium">How portal connections work</p>
          <p className="text-zinc-400 text-xs leading-relaxed">
            GrantFlow uses <strong className="text-zinc-200">OpenClaw</strong> — a Playwright-based browser automation agent built on Anthesis — to log in to grant portals for you.
            After login, it stores session cookies so the Automation Center can reuse them for autofill and submission jobs.
            You must have registered and been approved on each portal before OpenClaw can connect.
          </p>
          <p className="text-zinc-500 text-xs">
            Grants.gov requires SAM.gov registration first (get your UEI) →{" "}
            <a
              href="https://apply07.grants.gov/apply/register.faces?INITIAL_LOAD=true"
              target="_blank"
              rel="noopener noreferrer"
              className="text-cyan-300 hover:text-cyan-100 underline"
            >
              Register on Grants.gov
            </a>
          </p>
        </div>
      </div>

      {/* Provider cards */}
      {isLoading ? (
        <div className="text-zinc-400 text-sm py-8 text-center">Loading providers…</div>
      ) : isError ? (
        <div className="glass p-8 rounded-xl border border-rose-500/20 text-center space-y-3">
          <XCircle className="mx-auto w-8 h-8 text-rose-300" />
          <p className="text-zinc-200 text-sm">Could not load providers.</p>
          <Button onClick={() => refetch()} variant="outline" className="border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100">
            <RefreshCw className="w-4 h-4" /> Retry
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {providers.map((entry) => (
            <ProviderCard
              key={entry.key}
              entry={entry}
              onRefresh={() => qc.invalidateQueries({ queryKey: ["providers"] })}
            />
          ))}
        </div>
      )}

      {/* Link to automation */}
      <div className="text-center pt-2">
        <Link
          href="/automation"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-cyan-300 transition"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          View login jobs and status in Automation Center
        </Link>
      </div>
    </div>
  );
}
