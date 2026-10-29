"use client";

import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {refreshApplicationViews} from "@/lib/application-cache";
import {applicationError} from "@/lib/form-feedback";
import {HondaOnboardingPanel} from "@/components/HondaOnboardingPanel";
import {ApplicationSourceWorkbench} from "@/components/ApplicationSourceWorkbench";
import {HondaOnboardingData,isHondaOnboarding,hondaSources} from "@/lib/honda-onboarding";
import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { ApplicationReadiness } from "@/components/ApplicationReadiness";
import { DraftReview } from "@/components/DraftReview";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  Wand2,
  Send,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Building2,
  DollarSign,
  Calendar,
  FileText,
  Save,
  Copy,
  Download,
  ChevronRight,
  Clock,
  AlertCircle,
  ExternalLink,
  Info,
  Search,
  ClipboardList,
  Link2,
  Database,
  Package,
  Paperclip,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

interface ApplicationDetail {
  id: number;
  grant_id: number;
  organization_id: number | null;
  applicant_id: number | null;
  status: string;
  title?: string | null;
  proposal_text?: string | null;
  budget_narrative?: string | null;
  amount_requested?: number | null;
  form_data?: {
    honda_2027_onboarding?: HondaOnboardingData;
    grant_planning?: {
      strategic_fit?: {
        north_star?: string;
        score?: number;
      };
      partners?: Array<{ name: string; status?: string }>;
      compliance_items?: Array<{ title: string; status?: string }>;
      summary?: { budget_total?: number };
    };
    workspace_sync?: {
      opportunity_number?: string;
      cfda?: string;
      workspace_status?: string;
      last_modified?: string;
      workspace_url?: string;
      synced_at?: string;
      last_checked?: string;
    };
  };
  notes?: string | null;
  ai_generated?: boolean | null;
  submission_date?: string | null;
  created_at?: string;
  updated_at?: string | null;
}

interface PackageForm {
  name: string;
  form_number?: string;
  description?: string;
  is_mandatory: boolean;
  page_limit?: number | null;
}

interface GrantRequirements {
  grant_id: number;
  status: "none" | "running" | "done" | "error";
  fetched_at?: string | null;
  error?: string | null;
  requirements?: {
    success?: boolean;
    title?: string;
    synopsis?: string;
    agency?: string;
    opp_number?: string;
    deadline?: string;
    award_ceiling?: number | null;
    award_floor?: number | null;
    eligibility?: string;
    eligible_applicants?: string[];
    required_forms?: PackageForm[];
    required_attachments?: PackageForm[];
    package_instructions?: string;
    application_url?: string | null;
    source?: string;
    cfda_numbers?: string[];
    error?: string | null;
  };
}

interface GrantDetail {
  id: number;
  title: string;
  description?: string | null;
  funding_agency?: string | null;
  amount?: number | null;
  deadline?: string | null;
  eligibility?: string | null;
  ai_summary?: string | null;
  source_url?: string | null;
  portal_key?: string | null;
  requirements?: string[] | null;
  requirements_fetched_at?: string | null;
  meta?: {
    requirements_status?: string;
    requirements_error?: string;
    enrichment?: {
      cfda_number?: string | null;
      synopsis?: string | null;
      award_amounts_mentioned?: string[];
      required_documents?: string[];
      application_url?: string | null;
      pdf_url?: string | null;
      source?: string;
      error?: string | null;
    };
  } | null;
}

interface WorkflowStage {
  id: number;
  stage: string;
  status: string;
  order_index: number;
  notes?: string | null;
}

const STATUS_FLOW: { from: string; to: string; label: string; tone: string }[] = [
  { from: "draft", to: "submitted", label: "Submit", tone: "bg-cyan-500 hover:bg-cyan-400 text-[#03141c]" },
  { from: "submitted", to: "in_review", label: "Mark Under Review", tone: "bg-amber-400 hover:bg-amber-300 text-[#241500]" },
  { from: "in_review", to: "approved", label: "Approve", tone: "bg-emerald-500 hover:bg-emerald-400 text-[#04221a]" },
  { from: "in_review", to: "rejected", label: "Reject", tone: "bg-rose-500 hover:bg-rose-400 text-white" },
];

const STATUS_BADGE: Record<string, string> = {
  draft: "border-zinc-400/40 bg-zinc-500/10 text-zinc-100",
  submitted: "border-cyan-400/40 bg-cyan-500/10 text-cyan-100",
  in_review: "border-amber-400/40 bg-amber-500/10 text-amber-100",
  approved: "border-emerald-400/40 bg-emerald-500/10 text-emerald-100",
  rejected: "border-rose-400/40 bg-rose-500/10 text-rose-100",
  renewal_due: "border-orange-400/40 bg-orange-500/10 text-orange-100",
};

const STAGE_HINTS: Record<string, string> = {
  "Organization Setup": "Make sure your org profile is complete — name, mission, categories, and eligibility tags.",
  "Document Upload": "Upload supporting documents: audit, financial statement, annual report, and prior grant proposals.",
  "Grant Matching": "Review your grant match score and confirm this grant aligns with your mission and capacity.",
  "Application Draft": "Use AI Fill to generate a proposal draft, then review and edit before saving.",
  "Review & Collaboration": "Share the draft with team members or board for internal review and sign-off.",
  "Submission": "Go to the grant portal link and submit manually. Come back here and mark Submitted once done.",
  "Reporting & Compliance": "Track spending, collect outcome data, and submit required progress reports.",
};

// Static links per stage. Submission gets the grant source_url injected at render time.
const STAGE_LINKS: Record<string, { label: string; href: string; external?: boolean }> = {
  "Organization Setup":       { label: "Edit Org Profile", href: "/settings" },
  "Document Upload":          { label: "Upload Documents", href: "/documents" },
  "Grant Matching":           { label: "Browse Grants", href: "/grants" },
  "Application Draft":        { label: "AI Gap Analysis", href: "/gap-solutions" },
  "Review & Collaboration":   { label: "Gap Solutions", href: "/gap-solutions" },
  "Reporting & Compliance":   { label: "Gap Solutions", href: "/gap-solutions" },
};

function StageIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />;
  if (status === "blocked") return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />;
  if (status === "active") return (
    <span className="relative flex w-4 h-4 shrink-0">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
      <span className="relative inline-flex rounded-full w-4 h-4 bg-cyan-500" />
    </span>
  );
  return <div className="w-4 h-4 rounded-full border-2 border-zinc-500/50 shrink-0" />;
}

export default function ApplicationDetailPage() {
  const params = useParams<{ id: string }>();
  const qc = useQueryClient();
  const appId = Number(params?.id);

  const [proposal, setProposal] = useState("");
  const [proposalDirty, setProposalDirty] = useState(false);
  const [sourceDraftId,setSourceDraftId]=useState<number|null>(null);
  const [copyDone, setCopyDone] = useState(false);
  const [showOnboardingEditor,setShowOnboardingEditor]=useState(false);

  const application = useQuery<ApplicationDetail>({
    queryKey: ["application", appId],
    queryFn: () => api.get(`/api/applications/${appId}`).then((r) => r.data),
    enabled: Number.isFinite(appId),
    refetchInterval: 5000,
    refetchOnWindowFocus: 'always',
  });

  const grant = useQuery<GrantDetail>({
    queryKey: ["grant", application.data?.grant_id],
    queryFn: () => api.get(`/api/grants/${application.data?.grant_id}`).then((r) => r.data),
    enabled: !!application.data?.grant_id,
  });

  const workflow = useQuery<WorkflowStage[]>({
    queryKey: ["workflow", appId],
    queryFn: () => api.get(`/api/applications/${appId}/workflow`).then((r) => r.data),
    enabled: Number.isFinite(appId),
    refetchInterval: 5000,
    refetchOnWindowFocus: 'always',
  });

  useEffect(() => {
    if (application.data?.proposal_text != null && !proposalDirty) {
      setProposal(application.data.proposal_text || "");
    }
  }, [application.data?.proposal_text, proposalDirty]);

  const aiFill = useMutation({
    mutationFn: () =>
      api.post("/api/ai/generate", {
        application_id: appId,
        grant_id: application.data?.grant_id,
        task: "proposal",
        stream: false,
      }),
    onSuccess: (res) => {
      toast.success("AI candidate saved separately. Review it, then Save to update the application.");
      setSourceDraftId(res.data?.draft_id||null);
      setProposal(res.data?.result || "");
      setProposalDirty(true);
    },
    onError: () => toast.error("AI generation failed"),
  });

  const saveProposal = useMutation({
    mutationFn: () => api.patch(`/api/applications/${appId}`, { proposal_text: proposal, source_draft_id: sourceDraftId }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["application-readiness", Number(appId)] });
      toast.success("Proposal saved");
      refreshApplicationViews(qc,appId);
      // Update the cache before clearing dirty state; otherwise the sync effect
      // restores the old proposal while refetch is pending, corrupting exports.
      qc.setQueryData(["application", appId], res.data);
      setProposal(res.data.proposal_text || "");
      setProposalDirty(false);
      qc.invalidateQueries({ queryKey: ["application", appId] });
    },
    onError: (error:unknown) => toast.error(applicationError(error).message),
  });

  const setStatus = useMutation({
    mutationFn: (status: string) => api.patch(`/api/applications/${appId}`, { status }),
    onSuccess: (res, status) => {
      qc.setQueryData(["application",appId],res.data);
      refreshApplicationViews(qc,appId);
      toast.success(`Status set to ${status.replace("_", " ")}`);
      qc.invalidateQueries({ queryKey: ["application", appId] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (error: unknown) => toast.error((error as {response?:{data?:{detail?:string}}}).response?.data?.detail || "Status change failed"),
  });

  const advancePipeline = useMutation({
    mutationFn: () => api.post(`/api/applications/${appId}/workflow/advance`),
    onSuccess: () => {
      refreshApplicationViews(qc,appId);
      toast.success("Pipeline advanced to next stage");
      qc.invalidateQueries({ queryKey: ["workflow", appId] });
    },
    onError: (error: unknown) => toast.error((error as {response?:{data?:{detail?:string}}}).response?.data?.detail || "Could not advance pipeline"),
  });

  const updateStage = useMutation({
    mutationFn: ({ stageId, status }: { stageId: number; status: string }) =>
      api.patch(`/api/applications/${appId}/workflow/${stageId}`, { status }),
    onSuccess: () => {
      refreshApplicationViews(qc,appId);
      qc.invalidateQueries({ queryKey: ["workflow", appId] });
    },
    onError: (error: unknown) => toast.error((error as {response?:{data?:{detail?:string}}}).response?.data?.detail || "Stage update failed"),
  });

  const enrichGrant = useMutation({
    mutationFn: () => api.post(`/api/grants/${application.data?.grant_id}/enrich`),
    onSuccess: () => {
      toast.success("Grant details fetched from source");
      qc.invalidateQueries({ queryKey: ["grant", application.data?.grant_id] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Could not fetch grant details";
      toast.error(msg);
    },
  });

  const [reqPolling, setReqPolling] = useState(false);

  const fetchRequirements = useMutation({
    mutationFn: () => api.post(`/api/grants/${application.data?.grant_id}/requirements`),
    onSuccess: () => {
      toast.success("Scanning grants.gov for package requirements…");
      setReqPolling(true);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Could not start requirements fetch";
      toast.error(msg);
    },
  });

  const grantReqs = useQuery<GrantRequirements>({
    queryKey: ["grant-requirements", application.data?.grant_id],
    queryFn: () => api.get(`/api/grants/${application.data?.grant_id}/requirements`).then((r) => r.data),
    enabled: !!application.data?.grant_id,
    refetchInterval: reqPolling ? 3000 : false,
  });
  useEffect(() => {
    if (grantReqs.data && grantReqs.data.status !== "running") setReqPolling(false);
  }, [grantReqs.data]);

  const [sf424JobId, setSf424JobId] = useState<number | null>(null);
  const fillSF424 = useMutation({
    mutationFn: () => api.post(`/api/workspace/grants-gov/fill-sf424/${appId}`),
    onSuccess: (res) => {
      toast.success("SF-424 fill started — browser window opening on your desktop");
      setSf424JobId(res.data.job_id);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "SF-424 fill failed";
      toast.error(msg);
    },
  });

  const { data: sf424Job } = useQuery({
    queryKey: ["sf424-job", sf424JobId],
    queryFn: () => api.get(`/api/workspace/grants-gov/sync/${sf424JobId}`).then((r) => r.data),
    enabled: !!sf424JobId,
    refetchInterval: (q) => {
      const s = (q.state.data as { status?: string } | undefined)?.status;
      return s === "running" || s === "queued" ? 2000 : false;
    },
  });

  const [statusJobId, setStatusJobId] = useState<number | null>(null);
  const checkStatus = useMutation({
    mutationFn: () => api.post(`/api/workspace/grants-gov/check-status/${appId}`),
    onSuccess: (res) => {
      toast.success("Status check started");
      setStatusJobId(res.data.job_id);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Status check failed";
      toast.error(msg);
    },
  });

  const { data: statusJob } = useQuery({
    queryKey: ["status-check-job", statusJobId],
    queryFn: () => api.get(`/api/workspace/grants-gov/sync/${statusJobId}`).then((r) => r.data),
    enabled: !!statusJobId,
    refetchInterval: (q) => {
      const s = (q.state.data as { status?: string } | undefined)?.status;
      return s === "running" || s === "queued" ? 2000 : false;
    },
  });
  useEffect(() => {
    if (statusJob?.status === "completed") {
      qc.invalidateQueries({ queryKey: ["application", appId] });
    }
  }, [statusJob?.status, appId, qc]);

  function handleCopy() {
    if (!proposal) return;
    navigator.clipboard.writeText(proposal).then(() => {
      setCopyDone(true);
      toast.success("Proposal copied to clipboard");
      setTimeout(() => setCopyDone(false), 2000);
    });
  }

  function handleDownload() {
    if (!proposal) return;
    const title = (application.data?.title || "proposal").replace(/[^a-z0-9]/gi, "_").toLowerCase();
    const blob = new Blob([proposal], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Proposal downloaded");
  }

  if (!Number.isFinite(appId)) return <div className="p-6 text-zinc-200">Invalid application id.</div>;
  if (application.isLoading) return (
    <div className="p-6 flex items-center gap-2 text-zinc-200">
      <RefreshCw className="w-4 h-4 animate-spin" /> Loading application…
    </div>
  );
  if (application.isError || !application.data) return (
    <div className="p-6 text-rose-300">Could not load application.</div>
  );

  const app = application.data;
  const planning = app.form_data?.grant_planning;
  const hondaOnboarding=isHondaOnboarding(app);
  const transitions = STATUS_FLOW.filter((t) => t.from === app.status);
  const stages = workflow.data ?? [];
  const activeStage = stages.find((s) => s.status === "active");
  const allDone = stages.length > 0 && stages.every((s) => s.status === "completed");
  const noneStarted = stages.length > 0 && stages.every((s) => s.status === "pending");

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {!hondaOnboarding&&<><ApplicationReadiness appId={Number(appId)} /><DraftReview appId={Number(appId)} /></>}
      <div className="flex items-center justify-between gap-3">
        <Link href="/applications" className="inline-flex items-center gap-2 text-sm text-zinc-300 hover:text-cyan-200">
          <ArrowLeft className="w-4 h-4" /> Back to pipeline
        </Link>
        <Badge variant="outline" className={STATUS_BADGE[app.status] ?? STATUS_BADGE.draft}>
          {app.status.replace("_", " ").toUpperCase()}
        </Badge>
      </div>

      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5 sm:p-6 border border-cyan-900/40 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_10%_15%,rgba(103,232,249,0.18),transparent_32%),radial-gradient(circle_at_85%_15%,rgba(245,158,11,0.18),transparent_36%)]" />
        <div className="relative space-y-3">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-cyan-200/80">Application #{app.id}</p>
              <h1 className="text-2xl sm:text-3xl font-semibold text-white">
                {app.title || grant.data?.title || "Untitled application"}
              </h1>
              <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-zinc-200">
                <span className="inline-flex items-center gap-1.5">
                  <Building2 className="w-4 h-4 text-cyan-200" />
                  {grant.data?.funding_agency || "Unknown agency"}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <DollarSign className="w-4 h-4 text-amber-200" />
                  {app.amount_requested ? `$${app.amount_requested.toLocaleString()}` : "Amount TBD"}
                </span>
                {grant.data?.deadline && (
                  <span className="inline-flex items-center gap-1.5">
                    <Calendar className="w-4 h-4 text-emerald-200" />
                    Due {new Date(grant.data.deadline).toLocaleDateString()}
                  </span>
                )}
                {app.ai_generated && (
                  <Badge variant="outline" className="border-amber-400/40 bg-amber-500/10 text-amber-100">
                    AI Drafted
                  </Badge>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {transitions.map((t) => (
                <Button
                  key={t.to}
                  onClick={() => setStatus.mutate(t.to)}
                  disabled={setStatus.isPending}
                  className={`h-9 rounded-xl font-semibold ${t.tone}`}
                >
                  <Send className="w-3.5 h-3.5" />
                  {t.label}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </motion.section>

      {hondaOnboarding&&<><HondaOnboardingPanel appId={appId} request={app.amount_requested} data={app.form_data!.honda_2027_onboarding!}/><ApplicationReadiness appId={appId} onboarding/><DraftReview appId={appId}/></>}
      <ApplicationSourceWorkbench appId={appId}/>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Proposal editor */}
        {hondaOnboarding&&!showOnboardingEditor&&!proposal&&!proposalDirty&&<div className="lg:col-span-2 glass rounded-xl border border-cyan-900/40 p-5"><h2 className="text-xl text-white">Proposal intentionally blank</h2><p className="text-sm text-zinc-300 my-3">This record captures source onboarding only. No proposal has been generated.</p><Button variant="outline" onClick={()=>setShowOnboardingEditor(true)}>Open blank proposal editor</Button></div>}
        {(!hondaOnboarding||showOnboardingEditor||!!proposal||proposalDirty)&&<Card className="lg:col-span-2 border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div>
              <CardTitle className="text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-cyan-200" /> Proposal
              </CardTitle>
              <p className="text-xs text-zinc-300 mt-1">
                AI drafts from your org profile + grant requirements. Edit, save, then export.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => {if(!proposalDirty||window.confirm("Replace your unsaved editor text with a new AI candidate? Saved application text will remain unchanged."))aiFill.mutate();}}
                disabled={aiFill.isPending}
                className="h-9 rounded-xl bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-[#02131b] font-semibold"
              >
                {aiFill.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                {aiFill.isPending ? "Drafting…" : "AI Fill"}
              </Button>
              <Button
                onClick={() => saveProposal.mutate()}
                disabled={saveProposal.isPending || !proposalDirty}
                variant="outline"
                className="h-9 rounded-xl border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10 disabled:opacity-40"
              >
                <Save className="w-3.5 h-3.5" />
                {saveProposal.isPending ? "Saving…" : "Save"}
              </Button>
              <Button
                onClick={handleCopy}
                disabled={!proposal}
                variant="outline"
                className="h-9 rounded-xl border-zinc-600/50 bg-zinc-800/60 text-zinc-200 hover:bg-zinc-700/60 disabled:opacity-40"
              >
                <Copy className="w-3.5 h-3.5" />
                {copyDone ? "Copied!" : "Copy"}
              </Button>
              <Button
                onClick={handleDownload}
                disabled={!proposal}
                variant="outline"
                className="h-9 rounded-xl border-zinc-600/50 bg-zinc-800/60 text-zinc-200 hover:bg-zinc-700/60 disabled:opacity-40"
              >
                <Download className="w-3.5 h-3.5" />
                Export
              </Button>
            </div>
          </CardHeader>

          {/* AI drafting overlay */}
          {aiFill.isPending && (
            <div className="mx-6 mb-4 rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-4 flex items-start gap-3">
              <RefreshCw className="w-4 h-4 text-cyan-300 animate-spin mt-0.5 shrink-0" />
              <div className="text-sm">
                <p className="text-cyan-100 font-medium">AI is drafting your proposal…</p>
                <p className="text-cyan-200/70 text-xs mt-0.5">
                  Reading your org profile, grant requirements, and uploaded documents. This takes 15–30 seconds.
                </p>
              </div>
            </div>
          )}

          <CardContent>
            <Textarea
              value={proposal}
              disabled={saveProposal.isPending || aiFill.isPending}
              onChange={(e) => { setProposal(e.target.value); setProposalDirty(true); }}
              placeholder="Click 'AI Fill' to generate a draft, or write your own…"
              className="min-h-[420px] bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 leading-relaxed"
            />
          </CardContent>
        </Card>}

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Grant snapshot */}
          <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
            <CardHeader className="flex flex-row items-start justify-between pb-2 gap-2">
              <CardTitle className="text-white text-base">Grant Snapshot</CardTitle>
              {application.data?.grant_id && (
                <Button
                  onClick={() => enrichGrant.mutate()}
                  disabled={enrichGrant.isPending || !grant.data?.source_url}
                  size="sm"
                  variant="outline"
                  title="Fetch full requirements, CFDA number, and eligibility from the source page"
                  className="h-7 px-2 text-xs rounded-lg border-cyan-700/50 bg-[#0d2635]/80 text-zinc-200 hover:bg-cyan-500/10 shrink-0"
                >
                  {enrichGrant.isPending
                    ? <RefreshCw className="w-3 h-3 animate-spin" />
                    : <Search className="w-3 h-3" />}
                  {enrichGrant.isPending ? "Fetching…" : "Fetch Details"}
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-zinc-200 pt-0">
              {grant.isLoading ? (
                <p className="text-zinc-300">Loading grant…</p>
              ) : grant.data ? (
                <>
                  <p className="font-medium text-white leading-snug">{grant.data.title}</p>
                  {grant.data.ai_summary && (
                    <p className="text-zinc-300 text-xs leading-relaxed">{grant.data.ai_summary}</p>
                  )}
                  {grant.data.eligibility && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-cyan-200/80 mt-2">Eligibility</p>
                      <p className="text-xs text-zinc-300">{grant.data.eligibility}</p>
                    </div>
                  )}

                  {/* Enrichment panel — shows after Fetch Details */}
                  {grant.data.meta?.enrichment && (
                    <div className="mt-3 space-y-2 border-t border-cyan-900/30 pt-3">
                      {grant.data.meta.enrichment.cfda_number && (
                        <div>
                          <p className="text-xs uppercase tracking-wider text-amber-200/80">CFR / CFDA</p>
                          <p className="text-xs text-zinc-300">{grant.data.meta.enrichment.cfda_number}</p>
                        </div>
                      )}
                      {(grant.data.meta.enrichment.award_amounts_mentioned?.length ?? 0) > 0 && (
                        <div>
                          <p className="text-xs uppercase tracking-wider text-emerald-200/80">Award amounts found</p>
                          <p className="text-xs text-zinc-300">{grant.data.meta.enrichment.award_amounts_mentioned?.join(", ")}</p>
                        </div>
                      )}
                      {(grant.data.requirements?.length ?? 0) > 0 && (
                        <div>
                          <p className="text-xs uppercase tracking-wider text-cyan-200/80 mb-1 flex items-center gap-1">
                            <ClipboardList className="w-3 h-3" /> Required documents
                          </p>
                          <ul className="space-y-0.5">
                            {grant.data.requirements!.map((req) => (
                              <li key={req} className="text-xs text-zinc-300 flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60 shrink-0" />
                                {req}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {grant.data.meta.enrichment.pdf_url && (
                        <a
                          href={grant.data.meta.enrichment.pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-rose-300 hover:text-rose-100"
                        >
                          <FileText className="w-3 h-3" /> View NOFO PDF
                        </a>
                      )}
                      {grant.data.meta.enrichment.error && (
                        <p className="text-xs text-rose-400 bg-rose-500/10 rounded px-2 py-1">
                          {grant.data.meta.enrichment.error}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Portal connect shortcut */}
                  {grant.data.portal_key && (
                    <div className="mt-3 rounded-lg border border-cyan-900/30 bg-cyan-500/5 px-3 py-2 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <Link2 className="w-3.5 h-3.5 text-cyan-300 shrink-0" />
                        <p className="text-xs text-zinc-300 truncate capitalize">
                          {grant.data.portal_key.replace("_", " ")} portal
                        </p>
                      </div>
                      <Link
                        href="/providers"
                        className="text-xs text-cyan-400 hover:text-cyan-200 shrink-0 flex items-center gap-0.5"
                      >
                        Connect <ChevronRight className="w-3 h-3" />
                      </Link>
                    </div>
                  )}

                  {grant.data.source_url && (
                    <a
                      href={grant.data.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-cyan-300 hover:text-cyan-100 mt-1"
                    >
                      View grant source <ChevronRight className="w-3 h-3" />
                    </a>
                  )}
                </>
              ) : (
                <p className="text-zinc-300">No grant linked.</p>
              )}
            </CardContent>
          </Card>

          {/* ── Submission Package Requirements ───────────────────────────── */}
          {application.data?.grant_id && (
            hondaOnboarding?<Card className="border border-cyan-900/40 bg-[#0a1f2d]/85"><CardHeader><CardTitle className="text-white text-base">Honda application guidance</CardTitle></CardHeader><CardContent className="space-y-3 text-sm"><p>Official guidance available — complete portal questions and required uploads pending confirmation.</p><p>Submission platform: CyberGrants.</p><a className="text-cyan-200 underline" href={hondaSources.portal} target="_blank" rel="noopener noreferrer">Verified eligibility quiz / portal entry</a></CardContent></Card>:(<Card className="border border-violet-900/40 bg-[#0a1f2d]/85">
              <CardHeader className="flex flex-row items-start justify-between pb-2 gap-2">
                <CardTitle className="text-white text-base flex items-center gap-1.5">
                  <Package className="w-4 h-4 text-violet-300" /> Package Requirements
                </CardTitle>
                <Button
                  onClick={() => fetchRequirements.mutate()}
                  disabled={fetchRequirements.isPending || grantReqs.data?.status === "running"}
                  size="sm"
                  variant="outline"
                  title="Use OpenClaw to navigate to grants.gov and fetch the real submission package requirements"
                  className="h-7 px-2 text-xs rounded-lg border-violet-700/50 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20 shrink-0"
                >
                  {(fetchRequirements.isPending || grantReqs.data?.status === "running")
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Search className="w-3 h-3" />}
                  {grantReqs.data?.status === "running" ? "Scanning…" : grantReqs.data?.status === "done" ? "Re-scan" : "Scan grants.gov"}
                </Button>
              </CardHeader>
              <CardContent className="pt-0 text-xs text-zinc-300 space-y-3">
                {grantReqs.data?.status === "none" && !fetchRequirements.isPending && (
                  <p className="text-zinc-500 text-[11px]">
                    Click "Scan grants.gov" to discover what forms, attachments, and documents this specific grant actually requires.
                  </p>
                )}

                {grantReqs.data?.status === "running" && (
                  <div className="flex items-start gap-2 rounded-lg border border-violet-700/30 bg-violet-500/10 px-3 py-2">
                    <Loader2 className="w-3.5 h-3.5 text-violet-300 animate-spin mt-0.5 shrink-0" />
                    <div>
                      <p className="text-violet-200 font-medium">OpenClaw scanning grants.gov…</p>
                      <p className="text-violet-300/60 text-[10px] mt-0.5">Navigating to the opportunity page and reading the package checklist. This takes 20–40 seconds.</p>
                    </div>
                  </div>
                )}

                {grantReqs.data?.status === "error" && (
                  <div className="rounded-lg border border-rose-700/30 bg-rose-500/10 px-3 py-2 text-rose-300 text-[11px]">
                    {grantReqs.data.error || "Scan failed — check OpenClaw connection"}
                  </div>
                )}

                {grantReqs.data?.status === "done" && grantReqs.data.requirements && (() => {
                  const req = grantReqs.data.requirements!;
                  const forms = req.required_forms ?? [];
                  const attachments = req.required_attachments ?? [];
                  const hasContent = forms.length > 0 || attachments.length > 0;
                  return (
                    <div className="space-y-3">
                      {req.source && (
                        <div className="flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-violet-400/60 shrink-0" />
                          <span className="text-[10px] text-zinc-500 capitalize">Source: {req.source.replace("+", " + ")}</span>
                          {req.opp_number && <span className="text-[10px] text-zinc-600 ml-auto font-mono">{req.opp_number}</span>}
                        </div>
                      )}

                      {!hasContent && (
                        <p className="text-zinc-500 text-[11px]">
                          No specific package forms found — this grant may use a portal-based application or only list narrative instructions below.
                        </p>
                      )}

                      {forms.length > 0 && (
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-violet-200/80 mb-1.5 flex items-center gap-1">
                            <ClipboardList className="w-3 h-3" /> Required Forms
                          </p>
                          <ul className="space-y-1">
                            {forms.map((f, i) => (
                              <li key={i} className="flex items-start gap-1.5">
                                {f.is_mandatory
                                  ? <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-rose-400/70 shrink-0" />
                                  : <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-zinc-500/60 shrink-0" />}
                                <div className="min-w-0">
                                  <span className={f.is_mandatory ? "text-zinc-100" : "text-zinc-400"}>{f.name}</span>
                                  {f.form_number && <span className="ml-1.5 font-mono text-[10px] text-zinc-500">({f.form_number})</span>}
                                  {!f.is_mandatory && <span className="ml-1 text-[10px] text-zinc-600">optional</span>}
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {attachments.length > 0 && (
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-amber-200/80 mb-1.5 flex items-center gap-1">
                            <Paperclip className="w-3 h-3" /> Attachments & Narratives
                          </p>
                          <ul className="space-y-1">
                            {attachments.map((a, i) => (
                              <li key={i} className="flex items-start gap-1.5">
                                {a.is_mandatory
                                  ? <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-amber-400/70 shrink-0" />
                                  : <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-zinc-500/60 shrink-0" />}
                                <div className="min-w-0">
                                  <span className={a.is_mandatory ? "text-zinc-100" : "text-zinc-400"}>{a.name}</span>
                                  {a.page_limit && (
                                    <span className="ml-1.5 text-[10px] text-amber-400/80">{a.page_limit} pg limit</span>
                                  )}
                                  {!a.is_mandatory && <span className="ml-1 text-[10px] text-zinc-600">optional</span>}
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {req.eligible_applicants && req.eligible_applicants.length > 0 && (
                        <div className="border-t border-violet-900/30 pt-2">
                          <p className="text-[10px] uppercase tracking-wider text-cyan-200/80 mb-1">Eligible Applicants</p>
                          <p className="text-[11px] text-zinc-400">{req.eligible_applicants.join(", ")}</p>
                        </div>
                      )}

                      {req.package_instructions && (
                        <details className="border-t border-violet-900/30 pt-2">
                          <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-zinc-500 hover:text-zinc-300 select-none">
                            Package Instructions
                          </summary>
                          <p className="mt-1 text-[11px] text-zinc-400 leading-relaxed whitespace-pre-wrap line-clamp-12">
                            {req.package_instructions}
                          </p>
                        </details>
                      )}

                      {req.application_url && (
                        <a
                          href={req.application_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-violet-300 hover:text-violet-100 mt-1"
                        >
                          Open application page <ExternalLink className="w-3 h-3" />
                        </a>
                      )}

                      {grantReqs.data.fetched_at && (
                        <p className="text-[10px] text-zinc-600 border-t border-violet-900/20 pt-1.5">
                          Scanned {new Date(grantReqs.data.fetched_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                  );
                })()}
              </CardContent>
            </Card>)
          )}

          {/* Workspace sync info — shown when application came from grants.gov Workspace */}
          {app.form_data?.workspace_sync && (
            <Card className="border border-emerald-900/40 bg-[#0a1f2d]/85">
              <CardHeader className="flex flex-row items-start justify-between pb-2 gap-2">
                <CardTitle className="text-white text-base flex items-center gap-1.5">
                  <Database className="w-4 h-4 text-emerald-300" /> Workspace Sync
                </CardTitle>
                <Button
                  onClick={() => checkStatus.mutate()}
                  disabled={checkStatus.isPending || statusJob?.status === "running"}
                  size="sm"
                  variant="outline"
                  title="Check current status in grants.gov Workspace"
                  className="h-7 px-2 text-xs rounded-lg border-emerald-700/50 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 shrink-0"
                >
                  {checkStatus.isPending || statusJob?.status === "running"
                    ? <RefreshCw className="w-3 h-3 animate-spin" />
                    : <Search className="w-3 h-3" />}
                  {checkStatus.isPending || statusJob?.status === "running" ? "Checking…" : "Check Status"}
                </Button>
              </CardHeader>
              <CardContent className="pt-0 space-y-2 text-xs text-zinc-300">
                {app.form_data.workspace_sync.opportunity_number && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">Opportunity #</p>
                    <p className="font-mono text-zinc-200">{app.form_data.workspace_sync.opportunity_number}</p>
                  </div>
                )}
                {app.form_data.workspace_sync.cfda && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">CFDA</p>
                    <p className="text-zinc-200">{app.form_data.workspace_sync.cfda}</p>
                  </div>
                )}
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">Workspace Status</p>
                  <p className="text-emerald-200 font-medium">
                    {app.form_data.workspace_sync.workspace_status || "Unknown"}
                  </p>
                </div>
                {app.form_data.workspace_sync.last_modified && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">Last Modified</p>
                    <p className="text-zinc-300">{app.form_data.workspace_sync.last_modified}</p>
                  </div>
                )}
                {app.form_data.workspace_sync.last_checked && (
                  <p className="text-[10px] text-zinc-600">
                    Status checked: {new Date(app.form_data.workspace_sync.last_checked).toLocaleString()}
                  </p>
                )}
                {app.form_data.workspace_sync.synced_at && !app.form_data.workspace_sync.last_checked && (
                  <p className="text-[10px] text-zinc-600">
                    Synced: {new Date(app.form_data.workspace_sync.synced_at).toLocaleString()}
                  </p>
                )}
                {app.form_data.workspace_sync.workspace_url && (
                  <a
                    href={app.form_data.workspace_sync.workspace_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-emerald-300 hover:text-emerald-100 mt-1"
                  >
                    Open in Workspace <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                <div className="pt-2 border-t border-emerald-900/30">
                  <Button
                    onClick={() => fillSF424.mutate()}
                    disabled={fillSF424.isPending || sf424Job?.status === "running" || sf424Job?.status === "queued"}
                    size="sm"
                    className="w-full h-8 rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-semibold text-xs"
                  >
                    {fillSF424.isPending || sf424Job?.status === "running" || sf424Job?.status === "queued"
                      ? <><RefreshCw className="w-3 h-3 animate-spin" /> Filling SF-424…</>
                      : <><FileText className="w-3 h-3" /> Auto-fill SF-424</>}
                  </Button>
                  <p className="text-[10px] text-zinc-600 mt-1 leading-relaxed">
                    Opens a browser window on your desktop and fills the SF-424 with your org profile.
                  </p>
                  {sf424Job?.status === "completed" && (
                    <p className="text-xs text-emerald-300 mt-1 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      Filled {(sf424Job.result as { filled_fields?: string[] } | null)?.filled_fields?.length ?? 0} fields
                      {((sf424Job.result as { skipped_fields?: string[] } | null)?.skipped_fields?.length ?? 0) > 0 && (
                        <span className="text-zinc-500 ml-1">
                          · {(sf424Job.result as { skipped_fields?: string[] } | null)?.skipped_fields?.length} not found
                        </span>
                      )}
                    </p>
                  )}
                  {sf424Job?.status === "failed" && (
                    <p className="text-xs text-rose-300 mt-1 truncate">{sf424Job.error_message}</p>
                  )}
                </div>
                {statusJob?.status === "completed" && (
                  <p className="text-xs text-emerald-300 flex items-center gap-1 pt-1">
                    <CheckCircle2 className="w-3 h-3" />
                    Status refreshed — {(statusJob.result as { detected_status?: string } | null)?.detected_status ?? "no change"}
                  </p>
                )}
                {statusJob?.status === "failed" && (
                  <p className="text-xs text-rose-300 truncate">{statusJob.error_message}</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Planning context */}
          {planning && (
            <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
              <CardHeader>
                <CardTitle className="text-white text-base">Planning Context</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-zinc-200">
                <p>Strategic fit: <span className="text-cyan-200">{planning.strategic_fit?.score ?? 0}%</span></p>
                {planning.strategic_fit?.north_star && (
                  <p className="text-zinc-300 text-xs leading-relaxed">{planning.strategic_fit.north_star}</p>
                )}
                <p>Partners: <span className="text-zinc-100">{planning.partners?.length ?? 0}</span></p>
                <p>Compliance ready: <span className="text-zinc-100">{planning.compliance_items?.filter((i) => i.status === "ready").length ?? 0}</span></p>
                {planning.summary?.budget_total !== undefined && (
                  <p>Budget total: <span className="text-emerald-200">${planning.summary.budget_total.toLocaleString()}</span></p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Workflow pipeline */}
          <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div>
                <CardTitle className="text-white text-base">Workflow Pipeline</CardTitle>
                <p className="text-[11px] text-zinc-500 mt-0.5">Click a stage to update its status. Links open the resource for that step.</p>
              </div>
              {!allDone && stages.length > 0 && (
                <Button
                  onClick={() => advancePipeline.mutate()}
                  disabled={advancePipeline.isPending}
                  size="sm"
                  className="h-7 px-2.5 text-xs rounded-lg bg-gradient-to-r from-cyan-500 to-emerald-500 text-[#02131b] font-semibold hover:from-cyan-400 hover:to-emerald-400"
                >
                  {advancePipeline.isPending
                    ? <RefreshCw className="w-3 h-3 animate-spin" />
                    : <ChevronRight className="w-3 h-3" />}
                  {noneStarted ? "Start" : "Advance"}
                </Button>
              )}
            </CardHeader>
            <CardContent className="pt-0 space-y-0.5">
              {workflow.isLoading ? (
                <p className="text-zinc-300 text-sm">Loading…</p>
              ) : stages.length === 0 ? (
                <p className="text-zinc-300 text-sm">No stages yet.</p>
              ) : (
                <>
                  {stages.map((stage) => {
                    const isActive = stage.status === "active";
                    const isDone = stage.status === "completed";
                    const hint = STAGE_HINTS[stage.stage];

                    // Submission stage gets the live grant source_url; others use static map
                    const linkDef = stage.stage === "Submission"
                      ? grant.data?.source_url
                        ? { label: "Open Grant Portal", href: grant.data.source_url, external: true }
                        : null
                      : STAGE_LINKS[stage.stage] ?? null;

                    return (
                      <li key={stage.id} className="list-none">
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => {
                              if (isDone) updateStage.mutate({ stageId: stage.id, status: "pending" });
                              else if (isActive) updateStage.mutate({ stageId: stage.id, status: "completed" });
                              else updateStage.mutate({ stageId: stage.id, status: "active" });
                            }}
                            className="flex-1 flex items-center gap-2 text-sm text-left rounded-lg px-2 py-1.5 transition hover:bg-cyan-500/10 group"
                            title={hint}
                          >
                            <StageIcon status={stage.status} />
                            <span className={`flex-1 leading-tight ${isDone ? "text-zinc-500 line-through" : isActive ? "text-cyan-100 font-medium" : "text-zinc-300"}`}>
                              {stage.stage}
                            </span>
                            {isActive && (
                              <span className="text-[10px] text-cyan-300 font-medium uppercase tracking-wide shrink-0">active</span>
                            )}
                            {!isDone && !isActive && (
                              <Clock className="w-3 h-3 text-zinc-600 shrink-0 group-hover:text-zinc-400" />
                            )}
                          </button>

                          {/* Resource link — always visible */}
                          {linkDef && (
                            linkDef.external ? (
                              <a
                                href={stage.stage === "Document Upload" ? `/documents?application_id=${appId}` : linkDef.href}
                                target="_blank"
                                rel="noopener noreferrer"
                                title={linkDef.label}
                                className="p-1.5 rounded-md text-zinc-500 hover:text-cyan-200 hover:bg-cyan-500/10 transition shrink-0"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            ) : (
                              <Link
                                href={stage.stage === "Document Upload" ? `/documents?application_id=${appId}` : linkDef.href}
                                title={linkDef.label}
                                className="p-1.5 rounded-md text-zinc-500 hover:text-cyan-200 hover:bg-cyan-500/10 transition shrink-0"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </Link>
                            )
                          )}
                        </div>

                        {/* Active hint */}
                        {isActive && hint && (
                          <p className="text-xs text-cyan-200/60 pl-8 pr-2 pb-1 leading-relaxed">{hint}</p>
                        )}

                        {/* Submission stage disclaimer */}
                        {stage.stage === "Submission" && isActive && (
                          <div className="ml-8 mr-2 mb-1 rounded-lg border border-amber-400/25 bg-amber-500/8 px-3 py-2 flex gap-2">
                            <Info className="w-3.5 h-3.5 text-amber-300 shrink-0 mt-0.5" />
                            <p className="text-[11px] text-amber-200/80 leading-relaxed">
                              Marking this stage complete only updates your internal tracker — it does not submit to any portal. Use the link above to go to the grant portal and submit manually.
                            </p>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </>
              )}
              {allDone && (
                <p className="text-xs text-emerald-300 mt-3 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> All stages complete
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
