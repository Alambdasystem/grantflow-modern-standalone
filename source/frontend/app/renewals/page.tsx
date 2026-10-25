"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import Link from "next/link";
import { expectArray, fetchGrantFlowQuery } from "@/lib/query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertCircle,
  RefreshCw,
  Calendar,
  DollarSign,
  Wand2,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";

interface RenewalApplication {
  id: number;
  grant_id: number;
  title?: string | null;
  status: string;
  renewal_due_date?: string | null;
  amount_requested?: number | null;
  amount_awarded?: number | null;
}

const RENEWAL_WINDOW_DAYS = 90;

function normalizeRenewalsResponse(payload: unknown): RenewalApplication[] {
  const renewals = expectArray(payload, "Renewals API returned an invalid response.");

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const cutoff = new Date(today);
  cutoff.setDate(cutoff.getDate() + RENEWAL_WINDOW_DAYS);

  return renewals
    .filter((item): item is RenewalApplication => Boolean(item && typeof item === "object" && "id" in item && "grant_id" in item))
    .filter((item) => {
      const due = item.renewal_due_date ? new Date(item.renewal_due_date) : null;
      if (!due || Number.isNaN(due.getTime())) {
        return false;
      }
      const status = String(item.status || "").toLowerCase();
      return (
        (status === "approved" || status === "renewal_due") &&
        due >= today &&
        due <= cutoff
      );
    })
    .sort((left, right) => {
      const leftDue = left.renewal_due_date ? new Date(left.renewal_due_date).getTime() : Number.MAX_SAFE_INTEGER;
      const rightDue = right.renewal_due_date ? new Date(right.renewal_due_date).getTime() : Number.MAX_SAFE_INTEGER;
      return leftDue - rightDue;
    });
}

function daysUntil(dateStr: string) {
  const diff = new Date(dateStr).getTime() - Date.now();
  return Math.ceil(diff / 86400000);
}

function urgency(days: number) {
  if (days <= 7) return { ring: "border-rose-400/50", chip: "bg-rose-500/15 text-rose-100 border-rose-400/40" };
  if (days <= 30) return { ring: "border-amber-400/50", chip: "bg-amber-500/15 text-amber-100 border-amber-400/40" };
  return { ring: "border-cyan-400/40", chip: "bg-cyan-500/10 text-cyan-100 border-cyan-400/40" };
}

export default function RenewalsPage() {
  const qc = useQueryClient();

  const {
    data: renewals = [],
    isLoading,
    isError,
    error,
    isFetching,
    refetch,
  } = useQuery<RenewalApplication[]>({
    queryKey: ["renewals"],
    queryFn: async () => {
      return fetchGrantFlowQuery(
        "/api/renewals/due",
        normalizeRenewalsResponse
      );
    },
    retry: 1,
  });

  const autoRenew = useMutation({
    mutationFn: (id: number) =>
      api.post(`/api/renewals/${id}/auto-renew`),
    onSuccess: () => {
      toast.success("Auto-renewal job started");
      qc.invalidateQueries({ queryKey: ["renewals"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["automation-jobs"] });
    },
    onError: () => toast.error("Failed to start auto-renewal"),
  });

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5 sm:p-6 border border-cyan-900/40 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_8%_20%,rgba(245,158,11,0.18),transparent_30%),radial-gradient(circle_at_85%_15%,rgba(103,232,249,0.18),transparent_36%)]" />
        <div className="relative space-y-2">
          <Badge
            variant="outline"
            className="border-amber-300/50 bg-amber-500/10 text-amber-100"
          >
            Renewal Watchlist
          </Badge>
          <h1 className="text-3xl font-semibold text-white">Renewals Due</h1>
          <p className="text-zinc-200 text-sm">
            Approved & awarded applications with renewal deadlines in the next
            90 days.
          </p>
        </div>
      </motion.div>

      {isLoading ? (
        <div className="text-zinc-200 text-center py-12">Loading renewals…</div>
      ) : isError ? (
        <Card className="border border-rose-500/30 bg-[#201015]/90">
          <CardContent className="py-12 text-center space-y-3">
            <AlertCircle className="mx-auto text-rose-300 mb-1" size={40} />
            <p className="text-zinc-100">Unable to load renewals.</p>
            <p className="text-zinc-400 text-xs max-w-md mx-auto">
              {error instanceof Error
                ? error.message
                : "The renewals request did not complete successfully."}
            </p>
            <Button
              onClick={() => refetch()}
              disabled={isFetching}
              variant="outline"
              className="border-cyan-400/40 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/20"
            >
              <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : renewals.length === 0 ? (
        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardContent className="py-12 text-center">
            <AlertCircle className="mx-auto text-cyan-300/70 mb-3" size={40} />
            <p className="text-zinc-200">
              No renewals due in the next 90 days.
            </p>
            <p className="text-zinc-400 text-xs mt-1">
              Approve an application and set its renewal date to see it here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {renewals.map((app) => {
            const days = app.renewal_due_date
              ? daysUntil(app.renewal_due_date)
              : null;
            const u = days !== null ? urgency(days) : urgency(91);
            return (
              <Card
                key={app.id}
                className={`bg-[#0a1f2d]/85 border ${u.ring}`}
              >
                <CardContent className="pt-5 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="text-white font-semibold text-sm line-clamp-2">
                        {app.title || `Application #${app.id}`}
                      </h3>
                      <p className="text-zinc-400 text-xs mt-1">
                        Grant #{app.grant_id} · App #{app.id}
                      </p>
                    </div>
                    {days !== null && (
                      <Badge
                        variant="outline"
                        className={`shrink-0 text-xs font-bold ${u.chip}`}
                      >
                        {days}d
                      </Badge>
                    )}
                  </div>

                  <div className="space-y-1.5">
                    {app.renewal_due_date && (
                      <div className="flex items-center gap-2 text-xs text-zinc-200">
                        <Calendar size={13} className="text-cyan-200" />
                        <span>
                          Due{" "}
                          {new Date(app.renewal_due_date).toLocaleDateString()}
                        </span>
                      </div>
                    )}
                    {(app.amount_awarded || app.amount_requested) && (
                      <div className="flex items-center gap-2 text-xs text-zinc-200">
                        <DollarSign size={13} className="text-amber-200" />
                        <span>
                          $
                          {(
                            app.amount_awarded ?? app.amount_requested ?? 0
                          ).toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between gap-2 pt-1">
                    <Badge
                      variant="outline"
                      className="border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 text-[10px]"
                    >
                      {app.status.replace(/_/g, " ")}
                    </Badge>
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/applications/${app.id}`}
                        className="text-xs text-cyan-200 hover:text-cyan-100 inline-flex items-center gap-1"
                      >
                        Open <ArrowRight size={12} />
                      </Link>
                      <Button
                        onClick={() => autoRenew.mutate(app.id)}
                        disabled={autoRenew.isPending}
                        className="h-8 rounded-lg bg-gradient-to-r from-amber-400 to-cyan-400 hover:from-amber-300 hover:to-cyan-300 text-[#241500] text-xs font-semibold"
                      >
                        {autoRenew.isPending ? (
                          <RefreshCw className="w-3 h-3 animate-spin" />
                        ) : (
                          <Wand2 className="w-3 h-3" />
                        )}
                        Auto-Renew
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
