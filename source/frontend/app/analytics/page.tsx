"use client";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { DashboardStats, formatAwardedAmount, formatSuccessRate, parseDashboardStats } from "@/lib/dashboard";
import { fetchGrantFlowQuery } from "@/lib/query";
import { parseGrantPipeline, PipelineDatum } from "@/lib/analytics";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const COLORS = ["#6366f1", "#8b5cf6", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4"];

export default function AnalyticsPage() {
  const {
    data: pipeline = [],
    isLoading: pipelineLoading,
    isError: pipelineError,
  } = useQuery<PipelineDatum[]>({
    queryKey: ["grant-pipeline"],
    queryFn: () => fetchGrantFlowQuery("/api/analytics/grant-pipeline", parseGrantPipeline),
    retry: 1,
  });
  const { data: stats, isLoading, isError } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: () => fetchGrantFlowQuery("/api/analytics/dashboard", parseDashboardStats),
    retry: 1,
  });

  const hasPipelineData = pipeline.some((row) => row.count > 0);

  const summaryRows = [
    { label: "Total Awarded", value: stats ? formatAwardedAmount(stats.total_awarded, 1) : "No data" },
    { label: "Success Rate", value: stats ? formatSuccessRate(stats.success_rate) : "No data" },
    { label: "Active Grants", value: stats?.active_grants ?? "No data" },
    { label: "Pending Renewals", value: stats?.pending_renewals ?? "No data" },
  ];

  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-3xl font-bold gradient-text">Analytics</h1>
        <p className="text-zinc-400 text-sm">Grant performance and pipeline metrics</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Pipeline bar chart */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass p-6 rounded-xl"
        >
          <h2 className="text-zinc-100 font-semibold mb-4">Application Pipeline</h2>
          {pipelineLoading ? (
            <div className="space-y-3">
              <div className="h-4 w-40 rounded bg-cyan-200/15 animate-pulse" />
              <div className="h-[180px] w-full rounded bg-cyan-200/10 animate-pulse" />
            </div>
          ) : pipelineError ? (
            <p className="text-sm text-rose-200">Pipeline chart data is unavailable right now.</p>
          ) : !hasPipelineData ? (
            <div className="h-[220px] rounded-xl border border-cyan-900/40 bg-[#0d2434]/70 flex items-center justify-center px-6 text-center">
              <p className="text-sm text-zinc-300">No application pipeline data is available yet. Create or move applications to populate this chart.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={pipeline} margin={{ left: -20 }}>
                <XAxis dataKey="status" stroke="#52525b" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                <YAxis stroke="#52525b" tick={{ fill: "#a1a1aa", fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
                  labelStyle={{ color: "#fafafa" }}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        {/* Stats summary */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass p-6 rounded-xl"
        >
          <h2 className="text-zinc-100 font-semibold mb-4">Funding Overview</h2>
          {isLoading ? (
            <div className="space-y-3">
              <div className="h-4 w-40 rounded bg-cyan-200/15 animate-pulse" />
              <div className="h-4 w-36 rounded bg-cyan-200/15 animate-pulse" />
              <div className="h-4 w-32 rounded bg-cyan-200/15 animate-pulse" />
              <div className="h-4 w-36 rounded bg-cyan-200/15 animate-pulse" />
            </div>
          ) : isError ? (
            <p className="text-sm text-rose-200">Funding overview is unavailable while the dashboard summary API is failing.</p>
          ) : (
            <div className="space-y-4">
              {summaryRows.map((item) => (
              <div key={item.label} className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm">{item.label}</span>
                <span className="text-zinc-100 font-semibold">{item.value}</span>
              </div>
              ))}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
