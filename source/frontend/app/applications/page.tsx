"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useState, useRef } from "react";
import { fetchGrantFlowQuery } from "@/lib/query";
import { parseApplicationList, ApplicationListItem } from "@/lib/applications";
import {applicationError, requestedAmountError} from '@/lib/form-feedback';
import {refreshApplicationViews} from '@/lib/application-cache';
import { parseGrantOptions, GrantOption } from "@/lib/grants";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Plus, ChevronRight, FileText, Clock, CheckCircle, AlertCircle, XCircle } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

const STATUS_COLS = [
  { key: "draft",        label: "Draft",         icon: FileText,      color: "text-gray-400" },
  { key: "submitted",    label: "Submitted",      icon: Clock,         color: "text-blue-400" },
  { key: "in_review",    label: "Under Review",   icon: AlertCircle,   color: "text-yellow-400" },
  { key: "approved",     label: "Approved",       icon: CheckCircle,   color: "text-green-400" },
  { key: "rejected",     label: "Rejected",       icon: XCircle,       color: "text-red-400" },
  { key: "renewal_due",  label: "Renewal Due",    icon: AlertCircle,   color: "text-orange-400" },
];

export default function ApplicationsPage() {
  const qc = useQueryClient();
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ grant_id: "", title: "", amount_requested: "" });
  const [fieldErrors,setFieldErrors]=useState<Record<string,string>>({});
  const [formError,setFormError]=useState('');
  const amountInput=useRef<HTMLInputElement>(null);

  const {
    data: apps = [],
    isLoading,
    isError,
    error,
    isFetching,
    refetch,
  } = useQuery<ApplicationListItem[]>({
    queryKey: ["applications"],
    queryFn: () => fetchGrantFlowQuery("/api/applications/", parseApplicationList),
    retry: 1,
    refetchInterval: 5000,
    refetchOnWindowFocus: 'always',
  });

  const {
    data: grants = [],
    isLoading: grantsLoading,
    isError: grantsError,
  } = useQuery<GrantOption[]>({
    queryKey: ["application-grants"],
    queryFn: () => fetchGrantFlowQuery("/api/grants/?limit=200&offset=0&status=active", parseGrantOptions),
    enabled: showNew,
    retry: 1,
  });

  const createApp = useMutation({
    mutationFn: (payload: object) => api.post("/api/applications/", payload),
    onSuccess: () => {
      toast.success("Application created");
      refreshApplicationViews(qc);
      setFieldErrors({});setFormError('');
      setShowNew(false);
      setForm({ grant_id: "", title: "", amount_requested: "" });
    },
    onError: (error:unknown) => {const feedback=applicationError(error);setFieldErrors(feedback.fields);setFormError(feedback.message);toast.error(feedback.message);},
  });

  const patchStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.patch(`/api/applications/${id}`, { status }),
    onSuccess: (res,{id}) => {qc.setQueryData(['application',id],res.data);return refreshApplicationViews(qc,id);},
    onError: (error:unknown) => toast.error(applicationError(error).message),
  });

  const byStatus = (key: string) => apps.filter(a => a.status === key);

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-5 sm:p-6 border border-cyan-900/40 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_8%_20%,rgba(103,232,249,0.16),transparent_30%),radial-gradient(circle_at_85%_15%,rgba(245,158,11,0.14),transparent_34%)]" />
        <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="outline" className="border-cyan-300/50 bg-cyan-500/10 text-cyan-100">Pipeline Board</Badge>
              <Badge variant="outline" className="border-amber-300/50 bg-amber-500/10 text-amber-100">{apps.length} Total Applications</Badge>
            </div>
            <h1 className="text-3xl font-semibold text-white">Applications</h1>
            <p className="text-zinc-200 text-sm mt-1">Manage your grant applications from draft through renewal.</p>
          </div>
          <Button
            onClick={() => setShowNew(v => !v)}
            className="h-10 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#03141c] font-semibold"
          >
            <Plus size={16} /> New Application
          </Button>
        </div>
      </motion.div>

      {showNew && (
        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-white">Create Application</CardTitle>
          </CardHeader>
          <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <select
              aria-label="Grant" aria-invalid={!!fieldErrors.grant_id} aria-describedby={fieldErrors.grant_id?'grant-error':undefined}
              value={form.grant_id}
              onChange={e => setForm(f => ({ ...f, grant_id: e.target.value }))}
              disabled={grantsLoading || grantsError}
              className="h-10 bg-[#0d2635]/80 border border-cyan-900/40 rounded-lg px-3 py-2 text-white text-sm"
            >
              <option value="">
                {grantsLoading ? "Loading grants..." : grantsError ? "Grant list unavailable" : "Select Grant"}
              </option>
              {grants.map((grant) => (
                <option key={grant.id} value={grant.id}>{grant.id} - {grant.title}</option>
              ))}
            </select>
            <Input
              aria-label="Application title" aria-invalid={!!fieldErrors.title} aria-describedby={fieldErrors.title?'title-error':undefined}
              placeholder="Application Title"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-white"
            />
            <Input
              aria-label="Requested amount" min="0" step="0.01" aria-invalid={!!fieldErrors.amount_requested} aria-describedby={fieldErrors.amount_requested?'amount-error':undefined}
              ref={amountInput}
              placeholder="Requested Amount ($)"
              type="number"
              value={form.amount_requested}
              onChange={e => setForm(f => ({ ...f, amount_requested: e.target.value }))}
              className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-white"
            />
          </div>
          {fieldErrors.grant_id&&<p id="grant-error" role="alert" className="text-rose-200 text-sm">Grant: {fieldErrors.grant_id}</p>}
          {fieldErrors.title&&<p id="title-error" role="alert" className="text-rose-200 text-sm">Application title: {fieldErrors.title}</p>}
          {fieldErrors.amount_requested&&<p id="amount-error" role="alert" className="text-rose-200 text-sm">Requested amount: {fieldErrors.amount_requested}</p>}
          {formError&&<p role="alert" className="text-rose-200 text-sm mt-2">{formError}</p>}
          <div className="flex gap-3 mt-4">
            <Button
              onClick={() => {const amountError=amountInput.current?.validity.badInput?'Enter a valid requested amount.':requestedAmountError(form.amount_requested);if(amountError){setFieldErrors({amount_requested:amountError});setFormError('Check the highlighted application fields.');amountInput.current?.focus();return;}setFieldErrors({});setFormError('');createApp.mutate({
                grant_id: Number(form.grant_id),
                title: form.title || undefined,
                amount_requested: form.amount_requested ? Number(form.amount_requested) : undefined,
              });}}
              disabled={!form.grant_id || createApp.isPending}
              className="h-10 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#03141c] font-semibold disabled:opacity-50"
            >
              {createApp.isPending ? "Creating…" : "Create"}
            </Button>
            <Button variant="outline" onClick={() => setShowNew(false)} className="h-10 border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10">
              Cancel
            </Button>
          </div>
          {grantsError && (
            <p className="text-rose-200 text-xs mt-3">Grant options could not be loaded for application creation.</p>
          )}
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <div className="text-zinc-200 text-center py-12">Loading applications…</div>
      ) : isError ? (
        <Card className="border border-rose-500/30 bg-[#201015]/90">
          <CardContent className="py-8 space-y-3">
            <p className="text-zinc-100 text-sm font-medium">Applications could not be loaded.</p>
            <p className="text-zinc-400 text-xs">
              {error instanceof Error ? error.message : "The applications request timed out or failed."}
            </p>
            <Button
              onClick={() => refetch()}
              disabled={isFetching}
              variant="outline"
              className="h-9 border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10"
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : apps.length === 0 ? (
        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardContent className="py-12 text-center text-zinc-300 text-sm">
            No applications yet. Create a new application to start the pipeline.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {STATUS_COLS.map(col => {
            const colApps = byStatus(col.key);
            const Icon = col.icon;
            return (
              <Card key={col.key} className="border border-cyan-900/40 bg-[#0a1f2d]/85">
                <CardContent className="pt-4">
                <div className={`flex items-center gap-2 mb-3 ${col.color}`}>
                  <Icon size={16} />
                  <span className="font-semibold text-sm">{col.label}</span>
                  <span className="ml-auto bg-[#13364a] text-zinc-100 text-xs rounded-full px-2 py-0.5">{colApps.length}</span>
                </div>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {colApps.length === 0 && (
                    <p className="text-zinc-300 text-xs text-center py-4">No applications</p>
                  )}
                  {colApps.map(app => (
                    <Link key={app.id} href={`/applications/${app.id}`} className="block bg-[#0e2838]/75 rounded-lg p-3 border border-cyan-900/30 hover:border-cyan-400/45 transition-colors">
                      <p className="text-white text-sm font-medium line-clamp-1">{app.title || "Untitled Application"}</p>
                      <p className="text-zinc-300 text-xs mt-1">Grant #{app.grant_id}</p>
                      {app.amount_requested && (
                        <p className="text-cyan-200 text-xs mt-1">${app.amount_requested.toLocaleString()}</p>
                      )}
                      {col.key === "draft" && (
                        <button
                          onClick={(e) => { e.preventDefault(); e.stopPropagation(); patchStatus.mutate({ id: app.id, status: "submitted" }); }}
                          className="flex items-center gap-1 mt-2 text-xs text-cyan-200 hover:text-cyan-100 transition-colors"
                        >
                          Submit <ChevronRight size={12} />
                        </button>
                      )}
                    </Link>
                  ))}
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
