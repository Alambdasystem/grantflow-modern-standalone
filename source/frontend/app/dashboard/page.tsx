"use client";
import { useQuery } from "@tanstack/react-query";
import { NextActions } from "@/components/NextActions";
import RuntimeNotice from '@/components/RuntimeNotice';
import { motion } from "framer-motion";
import {
  DashboardStats,
  formatAwardedAmount,
  formatSuccessRate,
  parseDashboardStats,
} from "@/lib/dashboard";
import { fetchGrantFlowQuery } from "@/lib/query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AIPanel } from "@/components/ai/AIPanel";
import {
  TrendingUp, FileText, Zap, DollarSign, Clock, CheckCircle2, Target,
} from "lucide-react";

export default function DashboardPage() {
  const {
    data: stats,
    isLoading,
    isError,
  } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: () =>
      fetchGrantFlowQuery("/api/analytics/dashboard", parseDashboardStats),
    refetchInterval: 30_000,
    retry: 1,
  });

  const statsState = isLoading ? "loading" : isError ? "error" : stats ? "ready" : "empty";

  const cards = [
    { label: "Active Grants", value: stats?.active_grants, icon: FileText, color: "text-cyan-200" },
    { label: "Applications", value: stats?.total_applications, icon: TrendingUp, color: "text-amber-200" },
    { label: "Approved", value: stats?.approved_applications, icon: CheckCircle2, color: "text-emerald-200" },
    { label: "Pending Renewals", value: stats?.pending_renewals, icon: Clock, color: "text-orange-200" },
    { label: "Automation Jobs", value: stats?.automation_jobs_running, icon: Zap, color: "text-sky-200" },
    {
      label: "Total Awarded",
      value: stats ? formatAwardedAmount(stats.total_awarded) : undefined,
      icon: DollarSign,
      color: "text-teal-200",
    },
  ];

  const winRateLabel = formatSuccessRate(stats?.success_rate);

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <NextActions />
      <RuntimeNotice />
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5 sm:p-6 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_10%_15%,rgba(103,232,249,0.18),transparent_32%),radial-gradient(circle_at_80%_20%,rgba(251,191,36,0.18),transparent_36%)]" />
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="border-cyan-300/50 bg-cyan-500/10 text-cyan-100">GrantFlow Live</Badge>
              <Badge variant="outline" className="border-emerald-300/40 bg-emerald-500/10 text-emerald-100">
                {statsState === "loading" ? "Syncing" : statsState === "error" ? "Summary unavailable" : `${winRateLabel} success rate`}
              </Badge>
            </div>
            <h1 className="text-3xl md:text-4xl font-semibold tracking-tight gradient-text">Mission Control Dashboard</h1>
            <p className="text-zinc-200/90 text-sm md:text-base max-w-3xl">
              Monitor grant throughput, renewal exposure, and automation health with a single tactical view.
            </p>
          </div>
          <div className="rounded-2xl border border-cyan-300/30 bg-[#0b2330]/70 px-4 py-3 text-right">
            <p className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/80">Current Win Rate</p>
            <div className="text-3xl font-semibold text-cyan-50 mt-1">{statsState === "loading" ? "..." : statsState === "error" ? "Error" : winRateLabel}</div>
          </div>
        </div>
      </motion.section>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {cards.map((card, i) => {
          const Icon = card.icon;
          return (
            <motion.div key={card.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
              <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
                <CardHeader className="pb-0">
                  <CardTitle className="text-sm text-zinc-300 flex items-center justify-between">
                    {card.label}
                    <Icon className={`w-4 h-4 ${card.color}`} />
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {statsState === "loading" ? (
                    <div className="h-7 w-24 rounded bg-cyan-200/15 animate-pulse" />
                  ) : statsState === "error" ? (
                    <div className="text-sm font-medium text-rose-200 mt-2">Error</div>
                  ) : statsState === "empty" ? (
                    <div className="text-sm font-medium text-zinc-300 mt-2">No data</div>
                  ) : (
                    <div className="text-3xl font-semibold text-white mt-1">{card.value}</div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-zinc-100 flex items-center gap-2">
              <Target className="w-4 h-4 text-cyan-200" />
              Pipeline Focus
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-zinc-300">
            {statsState === "loading" ? (
              <div className="space-y-2">
                <div className="h-4 w-40 rounded bg-cyan-200/15 animate-pulse" />
                <div className="h-4 w-44 rounded bg-cyan-200/15 animate-pulse" />
                <div className="h-4 w-36 rounded bg-cyan-200/15 animate-pulse" />
              </div>
            ) : statsState === "error" ? (
              <p className="text-rose-200">Dashboard summary is unavailable. Retry after the API is reachable.</p>
            ) : statsState === "empty" ? (
              <p className="text-zinc-300">No portfolio summary data is available yet.</p>
            ) : (
              <>
                <p>Total grants tracked: <span className="text-white font-medium">{stats!.total_grants}</span></p>
                <p>Submitted applications: <span className="text-white font-medium">{stats!.submitted_applications}</span></p>
                <p>Pending renewals: <span className="text-white font-medium">{stats!.pending_renewals}</span></p>
              </>
            )}
          </CardContent>
        </Card>
        <div>
          <AIPanel />
        </div>
      </div>
    </div>
  );
}
