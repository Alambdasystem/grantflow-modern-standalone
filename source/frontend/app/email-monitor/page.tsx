"use client";

import type { ComponentType } from "react";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchGrantFlowQuery } from "@/lib/query";
import {
  EmailDecisionControlsResponse,
  EmailDecisionRow,
  EmailDecisionSummary,
  parseEmailDecisionControls,
  parseEmailDecisionRecent,
  parseEmailDecisionSummary,
} from "@/lib/email-decision-dashboard";
import {
  AlertTriangle,
  ArrowRight,
  CircleSlash2,
  Eye,
  Inbox,
  Mail,
  ShieldCheck,
  Sparkles,
  TimerReset,
  Workflow,
} from "lucide-react";

function countValue(value: number | undefined | null): string {
  return typeof value === "number" ? String(value) : "0";
}

function badgeTone(action: string) {
  const normalized = action.toUpperCase();
  if (normalized === "REPLY") return "border-emerald-300/40 bg-emerald-500/10 text-emerald-100";
  if (normalized === "BLOCKED") return "border-rose-300/40 bg-rose-500/10 text-rose-100";
  if (normalized === "HOLD") return "border-amber-300/40 bg-amber-500/10 text-amber-100";
  if (normalized === "REVIEW") return "border-sky-300/40 bg-sky-500/10 text-sky-100";
  return "border-zinc-300/30 bg-zinc-500/10 text-zinc-100";
}

function domainTone(domain: string) {
  switch (domain.toUpperCase()) {
    case "RECRUITING":
      return "border-cyan-300/40 bg-cyan-500/10 text-cyan-100";
    case "PROJECT_COLLABORATION":
      return "border-indigo-300/40 bg-indigo-500/10 text-indigo-100";
    case "MANUAL_OWNER":
      return "border-fuchsia-300/40 bg-fuchsia-500/10 text-fuchsia-100";
    case "SCHEDULING":
      return "border-amber-300/40 bg-amber-500/10 text-amber-100";
    default:
      return "border-zinc-300/30 bg-zinc-500/10 text-zinc-100";
  }
}

function SummaryCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string;
  value: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
}) {
  return (
    <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-zinc-300 flex items-center justify-between gap-3">
          <span>{title}</span>
          <Icon className="w-4 h-4 text-cyan-200" />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-3xl font-semibold text-white">{value}</div>
        <p className="text-xs text-zinc-400">{description}</p>
      </CardContent>
    </Card>
  );
}

function StageCard({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; value: string }>;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <h3 className="text-sm font-semibold text-zinc-100 mb-3">{title}</h3>
      <div className="space-y-1">
        {items.map((item) => (
          <DetailLine key={item.label} label={item.label} value={item.value} />
        ))}
      </div>
    </div>
  );
}

function DetailLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-white/5 last:border-0">
      <span className="text-xs uppercase tracking-[0.16em] text-zinc-500">{label}</span>
      <span className="text-sm text-zinc-100 text-right max-w-[65%] break-words">
        {value || "—"}
      </span>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function textValue(...values: unknown[]): string {
  for (const value of values) {
    if (value === null || value === undefined) {
      continue;
    }
    const text = String(value).trim();
    if (text) {
      return text;
    }
  }
  return "";
}

function booleanText(value: boolean | null | undefined): string {
  if (value === true) {
    return "YES";
  }
  if (value === false) {
    return "NO";
  }
  return "UNKNOWN";
}

function getClassificationRecord(row: EmailDecisionRow): Record<string, unknown> {
  return asRecord(row.classification);
}

function getBusinessStateRecord(row: EmailDecisionRow): Record<string, unknown> {
  return asRecord(row.business_state);
}

function getSelectedHandler(row: EmailDecisionRow): string {
  const classification = getClassificationRecord(row);
  const businessState = getBusinessStateRecord(row);
  return textValue(
    classification["selected_handler"],
    classification["selectedHandler"],
    businessState["selected_handler"],
    businessState["selectedHandler"],
    "none"
  );
}

function getResponseGenerator(row: EmailDecisionRow): string {
  const classification = getClassificationRecord(row);
  const businessState = getBusinessStateRecord(row);
  return textValue(
    classification["response_generator"],
    classification["responseGenerator"],
    businessState["response_generator"],
    businessState["responseGenerator"],
    row.response_preview ? "response preview available" : "",
    "not surfaced"
  );
}

function getDecisionResult(row: EmailDecisionRow): string {
  if (row.final_action === "REPLY" && row.transport.would_call_graph) {
    return "CLASSIFIER_CORRECT_SEND_ALLOWED";
  }
  if (row.transport.blocked) {
    return "CLASSIFIER_CORRECT_TRANSPORT_BLOCK";
  }
  if (row.final_action === "REVIEW") {
    return "NEEDS_REVIEW";
  }
  if (row.final_action === "BLOCKED" || row.final_action === "NO_REPLY") {
    return "CLASSIFIER_CORRECT_POLICY_BLOCK";
  }
  return "UNKNOWN";
}

function getBlockedAt(row: EmailDecisionRow): string {
  if (row.transport.blocked) {
    return "TRANSPORT";
  }
  if (row.final_action === "REVIEW") {
    return "POLICY / REVIEW";
  }
  if (row.send_allowed === false || row.reply_required === false || row.final_action === "NO_REPLY") {
    return "POLICY";
  }
  return "NONE";
}

function getHandlerEligibility(row: EmailDecisionRow): string {
  const selectedHandler = getSelectedHandler(row).toLowerCase();
  return selectedHandler && selectedHandler !== "none" && selectedHandler !== "not surfaced" ? "YES" : "NO";
}

function DecisionPanel({ row }: { row?: EmailDecisionRow | null }) {
  if (!row) {
    return (
      <div className="rounded-2xl border border-dashed border-cyan-900/50 bg-[#071622]/80 p-6 text-sm text-zinc-400">
        Select a decision row to inspect the full chain.
      </div>
    );
  }

  const evidence = row.why.domain_evidence.length
    ? row.why.domain_evidence
    : ["No structured evidence recorded."];
  const classification = getClassificationRecord(row);
  const businessState = getBusinessStateRecord(row);
  const selectedHandler = getSelectedHandler(row);
  const responseGenerator = getResponseGenerator(row);
  const decisionResult = getDecisionResult(row);
  const blockedAt = getBlockedAt(row);
  const handlerEligible = getHandlerEligibility(row);
  const classificationStatus = textValue(
    classification["classification_status"],
    businessState["classification_status"],
    row.transport.blocked ? "blocked" : "",
    "unknown"
  );
  const businessDomain = textValue(
    row.domain,
    classification["business_domain"],
    businessState["business_domain"],
    "UNKNOWN"
  );
  const primaryIntent = textValue(
    row.intent,
    classification["primary_intent"],
    businessState["primary_intent"],
    "needs_review"
  );
  const confidence = textValue(row.domain_confidence, classification["confidence"], "unknown");
  const handlerBlockReason = textValue(
    classification["handler_block_reason"],
    businessState["handler_block_reason"],
    row.block_reason,
    row.transport.blocked_reason,
    row.transport.validation
  );
  const transportAttempted = row.transport.would_call_graph ? "YES" : "NO";
  const transportValidated = row.transport.validation || "UNKNOWN";

  return (
    <Card className="border border-cyan-900/40 bg-[#091925]/90">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className={domainTone(row.domain)}>
            {row.domain}
          </Badge>
          <Badge variant="outline" className={badgeTone(row.final_action)}>
            {row.final_action}
          </Badge>
          <Badge variant="outline" className="border-zinc-300/30 bg-zinc-500/10 text-zinc-100">
            {row.intent}
          </Badge>
          <Badge variant="outline" className="border-slate-300/30 bg-slate-500/10 text-slate-100">
            {row.message_origin}
          </Badge>
        </div>
        <CardTitle className="text-zinc-100 text-xl leading-tight">
          {row.subject || "No subject"}
        </CardTitle>
        <p className="text-sm text-zinc-400">
          From {row.sender || "unknown sender"} · {row.time || "unknown time"}
        </p>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-cyan-900/40 bg-[#0b2330]/70 p-4">
            <div className="flex items-center gap-2 text-sm text-cyan-100 font-medium mb-3">
              <Workflow className="w-4 h-4" />
              Complete decision chain
            </div>
            <div className="space-y-3">
              <StageCard
                title="Inbound Email"
                items={[
                  { label: "Sender", value: row.sender || "unknown sender" },
                  { label: "Subject", value: row.subject || "No subject" },
                  { label: "Body preview", value: row.body_preview || "No preview available" },
                  { label: "Thread context", value: row.thread_context || "No thread context recorded." },
                ]}
              />
              <div className="flex justify-center text-cyan-200/70">
                <ArrowRight className="h-4 w-4 rotate-90" />
              </div>
              <StageCard
                title="LLM Classification"
                items={[
                  { label: "Business domain", value: businessDomain },
                  { label: "Primary intent", value: primaryIntent },
                  { label: "Classification status", value: classificationStatus },
                  { label: "Confidence", value: confidence },
                  { label: "Evidence", value: evidence.join(" | ") },
                ]}
              />
              <div className="flex justify-center text-cyan-200/70">
                <ArrowRight className="h-4 w-4 rotate-90" />
              </div>
              <StageCard
                title="Policy Decision"
                items={[
                  { label: "Conversation owner", value: row.owner || "unknown" },
                  { label: "Automation permission", value: row.automation_permission || "unknown" },
                  { label: "Reply required", value: booleanText(row.reply_required) },
                  { label: "Send allowed", value: booleanText(row.send_allowed) },
                  { label: "Recipient policy", value: row.recipient_policy || "unknown" },
                ]}
              />
              <div className="flex justify-center text-cyan-200/70">
                <ArrowRight className="h-4 w-4 rotate-90" />
              </div>
              <StageCard
                title="Handler Choice"
                items={[
                  { label: "Selected handler", value: selectedHandler },
                  { label: "Domain allows handler", value: handlerEligible },
                  { label: "Handler executed", value: handlerEligible },
                  { label: "Response generator", value: responseGenerator },
                  { label: "Handler block reason", value: handlerBlockReason || "None" },
                ]}
              />
              <div className="flex justify-center text-cyan-200/70">
                <ArrowRight className="h-4 w-4 rotate-90" />
              </div>
              <StageCard
                title="Transport Decision"
                items={[
                  { label: "Transport attempted", value: transportAttempted },
                  { label: "Transport validation", value: transportValidated },
                  { label: "Would call Graph", value: row.transport.would_call_graph ? "YES" : "NO" },
                  { label: "Transport blocked", value: row.transport.blocked ? "YES" : "NO" },
                  { label: "Blocked reason", value: row.transport.blocked_reason || row.block_reason || "None" },
                ]}
              />
              <div className="flex justify-center text-cyan-200/70">
                <ArrowRight className="h-4 w-4 rotate-90" />
              </div>
              <StageCard
                title="Final Action"
                items={[
                  { label: "Final action", value: row.final_action || "unknown" },
                  { label: "Decision result", value: decisionResult },
                  { label: "Blocked at", value: blockedAt },
                  { label: "Reason", value: row.block_reason || row.transport.blocked_reason || row.transport.validation || "None" },
                ]}
              />
            </div>
          </div>

          <div className="rounded-2xl border border-cyan-900/40 bg-[#0b2330]/70 p-4">
            <div className="flex items-center gap-2 text-sm text-cyan-100 font-medium mb-3">
              <Eye className="w-4 h-4" />
              Why this decision happened
            </div>
            <ul className="space-y-2 text-sm text-zinc-300">
              {evidence.map((item, index) => (
                <li key={`${item}-${index}`} className="flex gap-2">
                  <ArrowRight className="w-4 h-4 text-cyan-200 shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <h3 className="text-sm font-semibold text-zinc-100 mb-3">Policy and ownership</h3>
              <DetailLine label="Conversation owner" value={row.owner} />
              <DetailLine label="Reply required" value={booleanText(row.reply_required)} />
              <DetailLine label="Send allowed" value={booleanText(row.send_allowed)} />
              <DetailLine label="Recipient policy" value={row.recipient_policy} />
              <DetailLine label="Blocked at" value={blockedAt} />
              <DetailLine label="Decision result" value={decisionResult} />
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <h3 className="text-sm font-semibold text-zinc-100 mb-3">Handler and transport</h3>
              <DetailLine label="Selected handler" value={selectedHandler} />
              <DetailLine label="Domain allows handler" value={handlerEligible} />
              <DetailLine label="Handler executed" value={handlerEligible} />
              <DetailLine label="Response generator" value={responseGenerator} />
              <DetailLine label="Transport validation" value={row.transport_validation} />
              <DetailLine label="Final action" value={row.final_action} />
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <h3 className="text-sm font-semibold text-zinc-100 mb-3">Provenance</h3>
              <DetailLine label="Graph message ID" value={row.provenance.graph_message_id} />
              <DetailLine label="Conversation ID" value={row.provenance.conversation_id} />
              <DetailLine label="Internet message ID" value={row.provenance.internet_message_id} />
              <DetailLine label="Automation ledger" value={row.provenance.automation_ledger_match} />
              <DetailLine label="Previous automation message" value={row.provenance.previous_automation_message_id} />
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
            <h3 className="text-sm font-semibold text-zinc-100 mb-3">Message Snapshot</h3>
            <DetailLine label="Body preview" value={row.body_preview || row.response_preview || "No preview available"} />
            <DetailLine label="Thread context" value={row.thread_context || "No thread context recorded."} />
            <DetailLine label="Automation permission" value={row.automation_permission} />
            <DetailLine label="Domain confidence" value={row.domain_confidence} />
            <DetailLine
              label="Domain alternatives"
              value={row.domain_alternatives.length ? row.domain_alternatives.join(", ") : "None recorded"}
            />
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
            <h3 className="text-sm font-semibold text-zinc-100 mb-3">Transport & Attachments</h3>
            <DetailLine label="Would call Graph" value={row.transport.would_call_graph ? "yes" : "no"} />
            <DetailLine label="Transport blocked" value={row.transport.blocked ? "yes" : "no"} />
            <DetailLine label="Block reason" value={row.transport.blocked_reason || row.block_reason || "None"} />
            <DetailLine label="Attachment count" value={String(row.attachments.count)} />
            <DetailLine label="Attachment files" value={row.attachments.files.length ? row.attachments.files.join(", ") : "None"} />
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
            <h3 className="text-sm font-semibold text-zinc-100 mb-3">Timeline</h3>
            <div className="space-y-2">
              {row.timeline.map((step) => (
                <div key={`${step.step}-${step.at}`} className="flex items-center justify-between gap-4 text-sm">
                  <span className="text-zinc-300 flex items-center gap-2">
                    <TimerReset className="w-4 h-4 text-cyan-200" />
                    {step.step}
                  </span>
                  <span className="text-zinc-500 text-xs">{step.at || "—"}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function EmailMonitorPage() {
  const summaryQuery = useQuery<EmailDecisionSummary>({
    queryKey: ["email-decision-dashboard-summary"],
    queryFn: () =>
      fetchGrantFlowQuery(
        "/api/email-monitor/decision-dashboard/summary?limit=200",
        parseEmailDecisionSummary
      ),
    retry: 1,
    refetchInterval: 60_000,
  });

  const recentQuery = useQuery<EmailDecisionRow[]>({
    queryKey: ["email-decision-dashboard-recent"],
    queryFn: () =>
      fetchGrantFlowQuery(
        "/api/email-monitor/decision-dashboard/recent?limit=40",
        parseEmailDecisionRecent
      ),
    retry: 1,
    refetchInterval: 30_000,
  });

  const controlsQuery = useQuery<EmailDecisionControlsResponse>({
    queryKey: ["email-decision-dashboard-controls"],
    queryFn: () =>
      fetchGrantFlowQuery(
        "/api/email-monitor/decision-dashboard/controls",
        parseEmailDecisionControls
      ),
    retry: 1,
  });

  const summary = summaryQuery.data;
  const recent = recentQuery.data ?? [];
  const controls = controlsQuery.data?.controls ?? [];
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedMessageId && recent.length) {
      setSelectedMessageId(recent[0].message_id);
    }
  }, [recent, selectedMessageId]);

  const selectedDecision = useMemo(
    () => recent.find((item) => item.message_id === selectedMessageId) ?? recent[0] ?? null,
    [recent, selectedMessageId]
  );

  const dangerousDecisions = recent.filter(
    (item) =>
      item.transport.blocked ||
      item.final_action === "BLOCKED" ||
      item.final_action === "REVIEW" ||
      item.transport.validation === "NEEDS_REVIEW"
  );

  const shadow = summary?.shadow_report;
  const legacyBlockedCount = summary?.legacy_recruiting_false_positives_caught_by_new_gate ?? 0;
  const currentLiveClassifierErrors =
    (summary?.current_domain_gated_false_positive_recruiting ?? 0) +
    (summary?.current_domain_gated_false_negative_recruiting ?? 0);
  const policyBlockCount =
    (summary?.unknown_domain_sends_blocked ?? 0) +
    (summary?.domain_intent_mismatches_blocked ?? 0) +
    (summary?.reply_all_attempts_blocked ?? 0) +
    (summary?.manual_thread_automation_blocks ?? 0) +
    recent.filter((item) => item.final_action === "REVIEW").length;
  const transportBlockCount =
    summary?.transport_revalidation_blocks ??
    recent.filter((item) => item.transport.blocked).length;

  const metrics = [
    {
      title: "Sample Size",
      value: String(summary?.sample_size ?? recent.length),
      description: "Most recent classified decisions included in the dashboard.",
      icon: Inbox,
    },
    {
      title: "Send Allowed",
      value: `${countValue(summary?.send_allowed.YES)} / ${countValue(summary?.send_allowed.NO)}`,
      description: "Allowed versus blocked outbound decisions.",
      icon: ShieldCheck,
    },
    {
      title: "Blocked",
      value: String(summary?.blocked_count ?? dangerousDecisions.length),
      description: "Transport or policy blocks visible in the stream.",
      icon: AlertTriangle,
    },
    {
      title: "Needs Review",
      value: String(summary?.needs_review_count ?? 0),
      description: "Records that should not auto-send and need human attention.",
      icon: CircleSlash2,
    },
    {
      title: "Automation Owned",
      value: String(summary?.automation_owner_count ?? 0),
      description: "Threads already owned by the automation lane.",
      icon: Workflow,
    },
    {
      title: "Manual Owned",
      value: String(summary?.manual_owner_count ?? 0),
      description: "Threads still under manual / operator ownership.",
      icon: Mail,
    },
  ];

  if (summaryQuery.isError) {
    const detail=(summaryQuery.error as {response?:{data?:{detail?:string}}}).response?.data?.detail;
    return <div className="p-6 space-y-4"><h1 className="text-2xl">Email Safety</h1><p role="alert">{detail || 'Email Safety could not be loaded.'}</p><p>This is an Anthesis platform operator view. GrantFlow organization access alone does not grant access to cross-organization email activity.</p><button className="underline" onClick={()=>summaryQuery.refetch()}>Retry</button></div>;
  }
  if (summaryQuery.isLoading) return <div className="p-6" role="status">Loading Email Safety?</div>;

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl p-5 sm:p-6 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_10%_15%,rgba(103,232,249,0.18),transparent_32%),radial-gradient(circle_at_80%_20%,rgba(251,191,36,0.14),transparent_36%)]" />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-3 max-w-4xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="border-cyan-300/50 bg-cyan-500/10 text-cyan-100">
                Read-only
              </Badge>
              <Badge variant="outline" className="border-amber-300/40 bg-amber-500/10 text-amber-100">
                No-send
              </Badge>
              <Badge variant="outline" className="border-emerald-300/40 bg-emerald-500/10 text-emerald-100">
                Domain-first decision chain
              </Badge>
            </div>
            <h1 className="text-3xl md:text-4xl font-semibold tracking-tight gradient-text">
              Email Decision / Safety Dashboard
            </h1>
            <p className="text-zinc-200/90 text-sm md:text-base leading-6">
              Inspect how the live email pipeline classifies each message, why the transport is allowed or blocked,
              and what evidence sits behind every outbound decision.
            </p>
          </div>
          <div className="rounded-2xl border border-cyan-300/30 bg-[#0b2330]/70 px-4 py-3 min-w-[220px]">
            <p className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/80">Latest evaluation</p>
            <div className="text-2xl font-semibold text-cyan-50 mt-1">
              {summaryQuery.isLoading
                ? "Syncing..."
                : summaryQuery.isError
                  ? "Unavailable"
                  : `${summary?.blocked_count ?? 0} blocked`}
            </div>
            <p className="text-xs text-zinc-400 mt-1">
              Source of truth: email_monitor_routes.py and scheduling_activity_log.
            </p>
          </div>
        </div>
      </motion.section>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {metrics.map((metric, index) => (
          <motion.div
            key={metric.title}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
          >
            <SummaryCard {...metric} />
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Legacy blocked</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold text-white">{String(legacyBlockedCount)}</div>
            <p className="text-xs text-zinc-400">
              Historical recruiting-like false positives caught by the new gate.
            </p>
          </CardContent>
        </Card>

        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Current live-classifier errors</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold text-white">{String(currentLiveClassifierErrors)}</div>
            <p className="text-xs text-zinc-400">
              Current recruiting false positives and false negatives only.
            </p>
          </CardContent>
        </Card>

        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Policy blocks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold text-white">{String(policyBlockCount)}</div>
            <p className="text-xs text-zinc-400">
              Unknown domain, mismatch, manual ownership, reply-all, and review blocks.
            </p>
          </CardContent>
        </Card>

        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Transport blocks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold text-white">{String(transportBlockCount)}</div>
            <p className="text-xs text-zinc-400">
              Final safety-layer revalidation blocks before any Graph call.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-zinc-100 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-200" />
              Legacy vs Current recruiting safety
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-zinc-400 text-xs uppercase tracking-[0.16em]">
                Legacy recruiting false positives caught
              </p>
              <div className="mt-2 text-3xl font-semibold text-white">
                {String(summary?.legacy_recruiting_false_positives_caught_by_new_gate ?? 0)}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-zinc-400 text-xs uppercase tracking-[0.16em]">
                Current domain-gated recruiting false positives
              </p>
              <div className="mt-2 text-3xl font-semibold text-white">
                {String(summary?.current_domain_gated_false_positive_recruiting ?? 0)}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-zinc-400 text-xs uppercase tracking-[0.16em]">
                Current domain-gated recruiting false negatives
              </p>
              <div className="mt-2 text-3xl font-semibold text-white">
                {String(summary?.current_domain_gated_false_negative_recruiting ?? 0)}
              </div>
            </div>
            <div className="md:col-span-3 rounded-2xl border border-cyan-900/40 bg-[#0b2330]/70 p-4 text-zinc-300">
              The dashboard shows the new gate separately from the legacy recruiting-like classification count so
              audits can distinguish old false positives from the current domain-first behavior.
            </div>
          </CardContent>
        </Card>

        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-zinc-100 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-cyan-200" />
              Shadow work-authorization report
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-zinc-300">
            <DetailLine label="Known auth" value={String(shadow?.candidate_counts?.known ?? 0)} />
            <DetailLine label="Unknown auth" value={String(shadow?.candidate_counts?.unknown ?? 0)} />
            <DetailLine
              label="Roles needing sponsorship"
              value={String(shadow?.active_roles_with_documented_sponsorship_requirements ?? 0)}
            />
            <DetailLine
              label="Roles with unknown requirements"
              value={String(shadow?.active_roles_unknown_auth_requirements ?? 0)}
            />
            <DetailLine
              label="Strong matches needing clarification"
              value={String(shadow?.strong_technical_matches_needing_clarification ?? 0)}
            />
            <DetailLine
              label="Placement conflicts"
              value={String(shadow?.genuine_documented_placement_conflicts ?? 0)}
            />
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="recent" className="space-y-4">
        <TabsList variant="line" className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="recent">Recent Decisions</TabsTrigger>
          <TabsTrigger value="dangerous">Dangerous Decisions</TabsTrigger>
          <TabsTrigger value="controls">Control Replays</TabsTrigger>
        </TabsList>

        <TabsContent value="recent" className="space-y-4">
          <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-6">
            <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
              <CardHeader>
                <CardTitle className="text-zinc-100 flex items-center gap-2">
                  <Inbox className="w-4 h-4 text-cyan-200" />
                  Recent decisions
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {recentQuery.isLoading ? (
                  <div className="p-6 space-y-3">
                    <div className="h-4 w-44 rounded bg-cyan-200/15 animate-pulse" />
                    <div className="h-4 w-full rounded bg-cyan-200/10 animate-pulse" />
                    <div className="h-4 w-5/6 rounded bg-cyan-200/10 animate-pulse" />
                  </div>
                ) : recentQuery.isError ? (
                  <div className="p-6 text-sm text-rose-200">
                    Recent decisions are unavailable while the API is unreachable.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Time</TableHead>
                        <TableHead>Sender</TableHead>
                        <TableHead>Intent</TableHead>
                        <TableHead>Domain</TableHead>
                        <TableHead>Action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {recent.map((row) => {
                        const active = row.message_id === selectedMessageId;
                        return (
                          <TableRow
                            key={row.message_id}
                            onClick={() => setSelectedMessageId(row.message_id)}
                            className={active ? "bg-cyan-500/10" : "cursor-pointer"}
                          >
                            <TableCell className="text-zinc-300 text-xs whitespace-nowrap">
                              {row.time || "—"}
                            </TableCell>
                            <TableCell className="text-zinc-200 max-w-[240px] truncate">
                              {row.sender || "—"}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className="border-zinc-300/30 bg-zinc-500/10 text-zinc-100">
                                {row.intent}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className={domainTone(row.domain)}>
                                {row.domain}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className={badgeTone(row.final_action)}>
                                {row.final_action}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <div className="space-y-4">
              <DecisionPanel row={selectedDecision} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="dangerous" className="space-y-4">
          <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
            <CardHeader>
              <CardTitle className="text-zinc-100 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-200" />
                Dangerous decisions queue
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dangerousDecisions.length === 0 ? (
                <p className="text-sm text-zinc-400">
                  No blocked or review-needed decisions are currently in the sampled set.
                </p>
              ) : (
                <div className="space-y-3">
                  {dangerousDecisions.map((row) => (
                    <div
                      key={row.message_id}
                      className="rounded-2xl border border-white/10 bg-black/20 p-4 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between"
                    >
                      <div>
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <Badge variant="outline" className={domainTone(row.domain)}>
                            {row.domain}
                          </Badge>
                          <Badge variant="outline" className={badgeTone(row.final_action)}>
                            {row.final_action}
                          </Badge>
                          <Badge variant="outline" className="border-zinc-300/30 bg-zinc-500/10 text-zinc-100">
                            {row.intent}
                          </Badge>
                        </div>
                        <p className="text-sm text-zinc-100 font-medium">{row.subject || "No subject"}</p>
                        <p className="text-xs text-zinc-400">{row.sender || "Unknown sender"}</p>
                      </div>
                      <div className="text-xs text-zinc-400 max-w-2xl lg:text-right">
                        {row.block_reason || row.transport.blocked_reason || row.transport.validation}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="controls" className="space-y-4">
          <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
            <CardHeader>
              <CardTitle className="text-zinc-100 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-cyan-200" />
                Read-only control replays
              </CardTitle>
            </CardHeader>
            <CardContent>
              {controlsQuery.isLoading ? (
                <div className="space-y-3">
                  <div className="h-4 w-48 rounded bg-cyan-200/15 animate-pulse" />
                  <div className="h-20 w-full rounded bg-cyan-200/10 animate-pulse" />
                </div>
              ) : controlsQuery.isError ? (
                <p className="text-sm text-rose-200">Control replays are unavailable right now.</p>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {controls.map((item) => (
                    <div key={String(item.id)} className="rounded-2xl border border-white/10 bg-black/20 p-4 space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-zinc-100">{item.title}</p>
                          <p className="text-xs text-zinc-400">{item.source}</p>
                        </div>
                        <Badge
                          variant="outline"
                          className={
                            item.pass
                              ? "border-emerald-300/40 bg-emerald-500/10 text-emerald-100"
                              : "border-rose-300/40 bg-rose-500/10 text-rose-100"
                          }
                        >
                          {item.pass ? "PASS" : "FAIL"}
                        </Badge>
                      </div>
                      <div className="space-y-1 text-xs text-zinc-300">
                        <div>
                          Expected: {item.expected.domain} / {item.expected.intent} / {item.expected.final_action}
                        </div>
                        <div>
                          Actual: {item.actual.domain} / {item.actual.intent} / {item.actual.final_action}
                        </div>
                        <div>Status: {item.actual.classification_status}</div>
                        <div>Reason: {item.actual.reason || "—"}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
