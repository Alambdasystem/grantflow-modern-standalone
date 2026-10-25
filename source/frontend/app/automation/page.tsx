"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { expectArray, fetchGrantFlowQuery } from "@/lib/query";
import { RefreshCw, CheckCircle2, XCircle, Clock, Zap, AlertCircle } from "lucide-react";

interface AutomationJob {
  id: number;
  job_type: string;
  portal_key?: string;
  status: string;
  progress_pct: number;
  current_step?: string;
  error_message?: string;
  created_at: string;
}

const JOB_POLL_MS = 5000;
const JOB_POLL_WINDOW_MS = 60000;

function normalizeAutomationJobs(payload: unknown): AutomationJob[] {
  const jobs = expectArray(
    payload,
    "Automation jobs API returned an invalid response."
  );

  return jobs
    .filter((item): item is AutomationJob => Boolean(item && typeof item === "object" && "id" in item && "status" in item))
    .map((job) => ({
      ...job,
      progress_pct: Number.isFinite(Number(job.progress_pct))
        ? Math.max(0, Math.min(100, Number(job.progress_pct)))
        : 0,
    }));
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  queued: <Clock className="w-4 h-4 text-yellow-400" />,
  running: <Zap className="w-4 h-4 text-blue-400 animate-pulse" />,
  completed: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
  failed: <XCircle className="w-4 h-4 text-red-400" />,
};

export default function AutomationPage() {
  const [actionError, setActionError] = useState("");
  const [busyJob, setBusyJob] = useState<number | null>(null);
  async function control(id: number, action: "retry" | "cancel") {
    setBusyJob(id); setActionError("");
    try {
      if (action === "retry") await api.post(`/api/automation/jobs/${id}/run`);
      else await api.delete(`/api/automation/jobs/${id}`);
      pollingStartedAtRef.current = null;
      await refetch();
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      setActionError(err.response?.data?.detail || "Job action failed. Please retry.");
    } finally { setBusyJob(null); }
  }
  const pollingStartedAtRef = useRef<number | null>(null);
  const {
    data: jobs = [],
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    dataUpdatedAt,
  } = useQuery<AutomationJob[]>({
    queryKey: ["automation-jobs"],
    queryFn: async () => {
      return fetchGrantFlowQuery(
        "/api/automation/jobs",
        normalizeAutomationJobs
      );
    },
    retry: 1,
    refetchInterval: (query) => {
      const hasActiveJobs = (query.state.data ?? []).some((job) => job.status === "queued" || job.status === "running");
      if (!hasActiveJobs) {
        pollingStartedAtRef.current = null;
        return false;
      }
      if (!pollingStartedAtRef.current) {
        pollingStartedAtRef.current = Date.now();
      }
      if (Date.now() - pollingStartedAtRef.current >= JOB_POLL_WINDOW_MS) {
        return false;
      }
      return JOB_POLL_MS;
    },
  });

  const queue=useQuery<{counts:Record<string,number>;concurrency:number;pending_limit:number;worker_enabled:boolean;last_poll_at:string|null;mode:string}>({
    queryKey:["queue-status"],queryFn:()=>api.get('/api/automation/queue').then(r=>r.data),refetchInterval:10000});
  const lastUpdatedLabel = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Automation Center</h1>
          <p className="text-zinc-400 text-sm">Browser automation and Playwright job control</p>
          {lastUpdatedLabel && (
            <p className="text-zinc-500 text-xs mt-1">Last updated {lastUpdatedLabel}</p>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-sm transition"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
          {isFetching ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {queue.isError ? <p role="alert">Queue status unavailable.</p> : queue.data && <section className="glass rounded-xl p-4 mb-4 space-y-2" aria-label="Queue status">
        <h2 className="font-semibold">Persistent queue</h2>
        <p>Queued: {queue.data.counts.queued||0} ? Running: {queue.data.counts.running||0} ? Paused: {queue.data.counts.paused||0} ? Failed: {queue.data.counts.failed||0}</p>
        <p className="text-sm text-zinc-400">Your pending limit: {queue.data.pending_limit}. Shared concurrency: {queue.data.concurrency}. {queue.data.mode}.</p>
        <p className="text-sm">{queue.data.worker_enabled ? `Last worker poll: ${queue.data.last_poll_at ? new Date(queue.data.last_poll_at).toLocaleString() : 'Awaiting first poll'}` : 'Worker disabled; queued jobs will wait.'}</p>
      </section>}
      {actionError && <p role="alert" className="text-red-300">{actionError}</p>}
      <div className="space-y-3">
        {isLoading ? (
          <div className="text-zinc-500 text-sm">Loading jobs...</div>
        ) : isError ? (
          <div className="glass p-8 rounded-xl text-center space-y-3 border border-rose-500/20">
            <AlertCircle className="mx-auto w-8 h-8 text-rose-300" />
            <p className="text-zinc-100 text-sm">Unable to load automation jobs.</p>
            <p className="text-zinc-400 text-xs max-w-md mx-auto">
              {error instanceof Error
                ? error.message
                : "The automation jobs request timed out or returned an unexpected response."}
            </p>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm transition disabled:opacity-60"
            >
              <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Retry
            </button>
          </div>
        ) : !jobs.length ? (
          <div className="glass p-8 rounded-xl text-center text-zinc-500 text-sm">
            No automation jobs yet. Jobs will appear here when grant applications trigger automation.
          </div>
        ) : (
          jobs.map((job) => (
            <motion.div
              key={job.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass p-4 rounded-xl"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  {STATUS_ICONS[job.status] || <Clock className="w-4 h-4 text-zinc-500" />}
                  <div>
                    <span className="text-zinc-100 text-sm font-medium">
                      {job.job_type} · {job.portal_key || "local"}
                    </span>
                    <span className="ml-2 text-zinc-500 text-xs">#{job.id}</span>
                  </div>
                </div>
                <span className="text-xs text-zinc-500">
                  {new Date(job.created_at).toLocaleString()}
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-zinc-800 rounded-full h-1.5 mt-2">
                <div
                  className="h-1.5 rounded-full transition-all duration-500"
                  style={{
                    width: `${job.progress_pct}%`,
                    background: job.status === "failed" ? "#ef4444" : "#6366f1",
                  }}
                />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-xs text-zinc-500">{job.current_step || job.status}</span>
                <span className="text-xs text-zinc-500">{job.progress_pct}%</span>
              </div>
              {job.error_message && (
                <p className="text-xs text-red-400 mt-1">{job.error_message}</p>
              )}
              <div className="flex gap-3 mt-3">
                {["failed", "paused"].includes(job.status) && ["scrape", "renew"].includes(job.job_type) && <button disabled={busyJob === job.id} className="text-sm underline" onClick={() => control(job.id, "retry")}>Retry job</button>}
                {["queued", "running"].includes(job.status) && <button disabled={busyJob === job.id} className="text-sm underline" onClick={() => control(job.id, "cancel")}>Cancel job</button>}
              </div>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
