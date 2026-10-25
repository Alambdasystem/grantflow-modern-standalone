"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  BadgeCheck,
  Building2,
  CheckCircle2,
  ClipboardList,
  DollarSign,
  Handshake,
  Plus,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  RefreshCw,
  Save,
  Rocket,
  Trash2,
  Link2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Priority = {
  id: string;
  label: string;
  weight: number;
  score: number;
  rationale: string;
};

type Partner = {
  id: string;
  name: string;
  role: string;
  contribution: string;
  status: "target" | "engaged" | "confirmed";
};

type BudgetLine = {
  id: string;
  category: string;
  item: string;
  quantity: number;
  unitCost: number;
};

type ComplianceItem = {
  id: string;
  title: string;
  owner: string;
  status: "todo" | "reviewing" | "ready";
};

type GrantOption = {
  id: number;
  title: string;
  funding_agency?: string;
  ai_match_score?: number;
};

type PlanningProfileResponse = {
  id: number;
  grant_id: number;
  application_id?: number | null;
  strategic_fit: {
    north_star?: string;
    priorities?: Array<{ label: string; weight: number; score: number; rationale?: string }>;
    score?: number;
  };
  partners: Array<{ name: string; role: string; contribution?: string; status: Partner["status"] }>;
  budget_lines: Array<{ category: string; item: string; quantity: number; unit_cost: number }>;
  compliance_items: Array<{ title: string; owner?: string; status: ComplianceItem["status"] }>;
  summary?: Record<string, unknown>;
};

const partnerStatuses: Partner["status"][] = ["target", "engaged", "confirmed"];
const complianceStatuses: ComplianceItem["status"][] = ["todo", "reviewing", "ready"];

const defaultPriorities = (): Priority[] => [
  {
    id: "mission",
    label: "Mission alignment",
    weight: 5,
    score: 4,
    rationale: "The opportunity directly supports the organization's long-term program strategy.",
  },
  {
    id: "eligibility",
    label: "Eligibility clarity",
    weight: 4,
    score: 3,
    rationale: "Eligibility appears viable, but interpretation still needs legal or grants review.",
  },
  {
    id: "funder",
    label: "Funder priority overlap",
    weight: 5,
    score: 5,
    rationale: "Funder language strongly matches the target outcomes and service geography.",
  },
  {
    id: "capacity",
    label: "Operational readiness",
    weight: 3,
    score: 2,
    rationale: "Partnership staffing and reporting workflow would need to be tightened before submission.",
  },
];

const defaultPartners = (): Partner[] => [
  {
    id: "1",
    name: "Civic Workforce Alliance",
    role: "Employer pipeline",
    contribution: "Provide placement commitments and employer letters.",
    status: "engaged",
  },
  {
    id: "2",
    name: "Northside Learning Hub",
    role: "Program delivery",
    contribution: "Host after-school service cohort and collect attendance data.",
    status: "confirmed",
  },
];

const defaultBudgetLines = (): BudgetLine[] => [
  { id: "1", category: "Personnel", item: "Program manager", quantity: 12, unitCost: 6400 },
  { id: "2", category: "Fringe", item: "Benefits allocation", quantity: 12, unitCost: 1800 },
  { id: "3", category: "Supplies", item: "Participant toolkits", quantity: 75, unitCost: 120 },
];

const complianceTemplates: Record<string, ComplianceItem[]> = {
  federal: [
    { id: "sam", title: "SAM.gov registration current", owner: "Operations", status: "ready" },
    { id: "uei", title: "UEI verified on application profile", owner: "Finance", status: "reviewing" },
    { id: "subrecipient", title: "Subrecipient monitoring plan attached", owner: "Programs", status: "todo" },
    { id: "cost-principles", title: "Uniform guidance cost principles mapped to budget", owner: "Finance", status: "todo" },
  ],
  foundation: [
    { id: "board", title: "Board roster and term dates updated", owner: "Executive", status: "ready" },
    { id: "logic-model", title: "Program logic model tailored to funder priorities", owner: "Programs", status: "reviewing" },
    { id: "impact", title: "Outcome measurement narrative drafted", owner: "Evaluation", status: "todo" },
    { id: "attachments", title: "Attachment checklist reconciled with portal rules", owner: "Grants", status: "todo" },
  ],
  state: [
    { id: "state-reg", title: "State vendor registration active", owner: "Operations", status: "reviewing" },
    { id: "audit", title: "Single audit packet prepared", owner: "Finance", status: "todo" },
    { id: "match", title: "Match documentation assembled", owner: "Development", status: "todo" },
    { id: "narrative", title: "Required state narrative headings mapped", owner: "Grants", status: "ready" },
  ],
};

const statusTone: Record<string, string> = {
  target: "border-zinc-600/60 bg-zinc-500/10 text-zinc-100",
  engaged: "border-amber-400/50 bg-amber-500/10 text-amber-100",
  confirmed: "border-emerald-400/50 bg-emerald-500/10 text-emerald-100",
  todo: "border-rose-400/40 bg-rose-500/10 text-rose-100",
  reviewing: "border-cyan-400/50 bg-cyan-500/10 text-cyan-100",
  ready: "border-emerald-400/50 bg-emerald-500/10 text-emerald-100",
};

export default function GapSolutionsClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedGrantId, setSelectedGrantId] = useState<number | null>(null);
  const [linkedApplicationId, setLinkedApplicationId] = useState<number | null>(null);
  const [savedProfileId, setSavedProfileId] = useState<number | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [northStar, setNorthStar] = useState(
    "Prioritize youth-serving, workforce, and community resilience grants that can scale within 12 months.",
  );
  const [priorities, setPriorities] = useState<Priority[]>(defaultPriorities);
  const [partners, setPartners] = useState<Partner[]>(defaultPartners);
  const [budgetLines, setBudgetLines] = useState<BudgetLine[]>(defaultBudgetLines);
  const [newPartner, setNewPartner] = useState({ name: "", role: "", contribution: "" });
  const [grantType, setGrantType] = useState<keyof typeof complianceTemplates>("federal");
  const [complianceItems, setComplianceItems] = useState<ComplianceItem[]>(complianceTemplates.federal);

  const grantsQuery = useQuery<GrantOption[]>({
    queryKey: ["gap-solutions-grants"],
    queryFn: () => api.get("/api/grants/?limit=200&offset=0&status=active").then((response) => response.data),
  });

  useEffect(() => {
    if (!selectedGrantId && grantsQuery.data?.length) {
      setSelectedGrantId(grantsQuery.data[0].id);
    }
  }, [grantsQuery.data, selectedGrantId]);

  const profileQuery = useQuery<PlanningProfileResponse | null>({
    queryKey: ["grant-planning-profile", selectedGrantId],
    enabled: !!selectedGrantId,
    queryFn: async () => {
      try {
        const response = await api.get(`/api/grant-planning?grant_id=${selectedGrantId}`);
        return response.data;
      } catch (error: any) {
        if (error?.response?.status === 404) {
          return null;
        }
        throw error;
      }
    },
  });

  useEffect(() => {
    if (profileQuery.data === undefined) {
      return;
    }

    if (!profileQuery.data) {
      setNorthStar("Prioritize youth-serving, workforce, and community resilience grants that can scale within 12 months.");
      setPriorities(defaultPriorities());
      setPartners(defaultPartners());
      setBudgetLines(defaultBudgetLines());
      setGrantType("federal");
      setComplianceItems(complianceTemplates.federal);
      setSavedProfileId(null);
      setLinkedApplicationId(null);
      setLastSavedAt(null);
      return;
    }

    setSavedProfileId(profileQuery.data.id);
    setLinkedApplicationId(profileQuery.data.application_id ?? null);

    setNorthStar(profileQuery.data.strategic_fit?.north_star || "");
    setPriorities(
      (profileQuery.data.strategic_fit?.priorities || []).map((priority, index) => ({
        id: `${index}-${priority.label}`,
        label: priority.label,
        weight: priority.weight,
        score: priority.score,
        rationale: priority.rationale || "",
      })),
    );
    setPartners(
      (profileQuery.data.partners || []).map((partner, index) => ({
        id: `${index}-${partner.name}`,
        name: partner.name,
        role: partner.role,
        contribution: partner.contribution || "",
        status: partner.status,
      })),
    );
    setBudgetLines(
      (profileQuery.data.budget_lines || []).map((line, index) => ({
        id: `${index}-${line.item}`,
        category: line.category,
        item: line.item,
        quantity: line.quantity,
        unitCost: line.unit_cost,
      })),
    );
    const matchedTemplate = (Object.keys(complianceTemplates) as Array<keyof typeof complianceTemplates>).find((template) => {
      const templateTitles = complianceTemplates[template].map((item) => item.title).sort().join("|");
      const currentTitles = (profileQuery.data?.compliance_items || []).map((item) => item.title).sort().join("|");
      return templateTitles === currentTitles;
    });
    setGrantType(matchedTemplate || "federal");
    setComplianceItems(
      (profileQuery.data.compliance_items || []).map((item, index) => ({
        id: `${index}-${item.title}`,
        title: item.title,
        owner: item.owner || "",
        status: item.status,
      })),
    );
  }, [profileQuery.data]);

  const totalWeight = priorities.reduce((sum, priority) => sum + priority.weight, 0);
  const weightedScore = priorities.reduce((sum, priority) => sum + priority.weight * priority.score, 0);
  const strategicFitScore = totalWeight > 0 ? Math.round((weightedScore / (totalWeight * 5)) * 100) : 0;
  const strongestSignals = priorities.filter((priority) => priority.score >= 4);
  const watchItems = priorities.filter((priority) => priority.score <= 2);
  const budgetTotal = budgetLines.reduce((sum, line) => sum + line.quantity * line.unitCost, 0);
  const readyCompliance = complianceItems.filter((item) => item.status === "ready").length;

  const updatePriority = (id: string, field: keyof Priority, value: string | number) => {
    setPriorities((current) =>
      current.map((priority) => (priority.id === id ? { ...priority, [field]: value } : priority)),
    );
  };

  const cyclePartnerStatus = (id: string) => {
    setPartners((current) =>
      current.map((partner) => {
        if (partner.id !== id) {
          return partner;
        }
        const nextIndex = (partnerStatuses.indexOf(partner.status) + 1) % partnerStatuses.length;
        return { ...partner, status: partnerStatuses[nextIndex] };
      }),
    );
  };

  const addPartner = () => {
    if (!newPartner.name.trim() || !newPartner.role.trim()) {
      return;
    }
    setPartners((current) => [
      ...current,
      {
        id: String(Date.now()),
        name: newPartner.name.trim(),
        role: newPartner.role.trim(),
        contribution: newPartner.contribution.trim() || "Contribution scope pending.",
        status: "target",
      },
    ]);
    setNewPartner({ name: "", role: "", contribution: "" });
  };

  const updateBudgetLine = (id: string, field: keyof BudgetLine, value: string | number) => {
    setBudgetLines((current) => current.map((line) => (line.id === id ? { ...line, [field]: value } : line)));
  };

  const addBudgetLine = () => {
    setBudgetLines((current) => [
      ...current,
      { id: String(Date.now()), category: "Other", item: "New line item", quantity: 1, unitCost: 0 },
    ]);
  };

  const changeComplianceTemplate = (value: keyof typeof complianceTemplates) => {
    setGrantType(value);
    setComplianceItems(complianceTemplates[value]);
  };

  const removePartner = (id: string) => {
    setPartners((current) => current.filter((partner) => partner.id !== id));
  };

  const removeBudgetLine = (id: string) => {
    setBudgetLines((current) => current.filter((line) => line.id !== id));
  };

  const cycleComplianceStatus = (id: string) => {
    setComplianceItems((current) =>
      current.map((item) => {
        if (item.id !== id) {
          return item;
        }
        const nextIndex = (complianceStatuses.indexOf(item.status) + 1) % complianceStatuses.length;
        return { ...item, status: complianceStatuses[nextIndex] };
      }),
    );
  };

  const budgetJustification = budgetLines
    .map((line) => `${line.item}: ${line.quantity} x $${line.unitCost.toLocaleString()} in ${line.category.toLowerCase()}`)
    .join("; ");

  const buildPayload = () => {
    if (!selectedGrantId) {
      throw new Error("Select a grant first");
    }

    return {
      grant_id: selectedGrantId,
      ...(linkedApplicationId ? { application_id: linkedApplicationId } : {}),
      strategic_fit: {
        north_star: northStar,
        priorities: priorities.map((priority) => ({
          label: priority.label,
          weight: priority.weight,
          score: priority.score,
          rationale: priority.rationale,
        })),
        score: strategicFitScore,
      },
      partners: partners.map((partner) => ({
        name: partner.name,
        role: partner.role,
        contribution: partner.contribution,
        status: partner.status,
      })),
      budget_lines: budgetLines.map((line) => ({
        category: line.category,
        item: line.item,
        quantity: line.quantity,
        unit_cost: line.unitCost,
      })),
      compliance_items: complianceItems.map((item) => ({
        title: item.title,
        owner: item.owner,
        status: item.status,
      })),
      summary: {
        budget_total: budgetTotal,
        grant_type: grantType,
      },
    };
  };

  const saveProfile = useMutation({
    mutationFn: () => api.post("/api/grant-planning", buildPayload()),
    onSuccess: (response) => {
      toast.success("Planning profile saved");
      queryClient.setQueryData(["grant-planning-profile", selectedGrantId], response.data);
      setSavedProfileId(response.data.id);
      setLinkedApplicationId(response.data.application_id ?? null);
      setLastSavedAt(new Date());
    },
    onError: () => toast.error("Could not save planning profile"),
  });

  const promoteToApplication = useMutation({
    mutationFn: () =>
      api.post("/api/grant-planning/promote", {
        ...buildPayload(),
        application_title: `${selectedGrant?.title || "Grant"} Strategy Draft`,
      }),
    onSuccess: (response) => {
      toast.success("Promoted into application drafting flow");
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.setQueryData(["grant-planning-profile", selectedGrantId], response.data.planning_profile);
      setSavedProfileId(response.data.planning_profile.id);
      setLinkedApplicationId(response.data.application.id);
      setLastSavedAt(new Date());
      router.push(`/applications/${response.data.application.id}`);
    },
    onError: () => toast.error("Could not promote planning data to an application"),
  });

  const selectedGrant = grantsQuery.data?.find((grant) => grant.id === selectedGrantId);

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl border border-cyan-900/40 p-5 sm:p-6 overflow-hidden relative"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_18%,rgba(45,212,191,0.18),transparent_26%),radial-gradient(circle_at_82%_22%,rgba(251,191,36,0.16),transparent_30%),radial-gradient(circle_at_78%_78%,rgba(59,130,246,0.14),transparent_28%)]" />
        <div className="relative space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div className="space-y-2 max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="border-cyan-300/50 bg-cyan-500/10 text-cyan-100">Pre-Award Gap Lab</Badge>
                <Badge variant="outline" className="border-amber-300/40 bg-amber-500/10 text-amber-100">Prototype Modules</Badge>
                {selectedGrant && (
                  <Badge variant="outline" className="border-emerald-300/40 bg-emerald-500/10 text-emerald-100">
                    Grant #{selectedGrant.id}
                  </Badge>
                )}
              </div>
              <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-zinc-50">
                Grant Processing Gap Solutions
              </h1>
              <p className="text-sm md:text-base text-zinc-200/90">
                Turn qualitative grant-processing gaps into structured workflows: deeper fit assessment, partner coordination,
                budget development, and compliance readiness.
              </p>
            </div>
            <div className="rounded-2xl border border-cyan-300/30 bg-[#0a2230]/80 p-4 min-w-[240px]">
              <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/75">Recommended build order</div>
              <div className="mt-2 text-2xl font-semibold text-white">1. Strategic Fit</div>
              <div className="text-sm text-zinc-300 mt-1">Then collaboration, budget, and compliance as linked records.</div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_auto] lg:items-end">
            <div>
              <label className="text-xs uppercase tracking-[0.18em] text-zinc-400">Attach planning profile to grant</label>
              <select
                value={selectedGrantId ?? ""}
                onChange={(event) => setSelectedGrantId(Number(event.target.value) || null)}
                className="mt-2 h-11 w-full rounded-xl border border-cyan-900/40 bg-[#081c29]/85 px-3 text-sm text-zinc-100"
              >
                <option value="">Select active grant</option>
                {(grantsQuery.data || []).map((grant) => (
                  <option key={grant.id} value={grant.id}>
                    {grant.id} - {grant.title}
                  </option>
                ))}
              </select>
              {selectedGrant && (
                <p className="mt-2 text-xs text-zinc-400">
                  {selectedGrant.funding_agency || "Unknown agency"}
                  {selectedGrant.ai_match_score ? ` · ${Math.round(selectedGrant.ai_match_score)}% current AI match` : ""}
                </p>
              )}
            </div>
            <Button
              onClick={() => saveProfile.mutate()}
              disabled={!selectedGrantId || saveProfile.isPending || promoteToApplication.isPending}
              variant="outline"
              className="h-11 rounded-xl border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10"
            >
              {saveProfile.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {saveProfile.isPending ? "Saving…" : "Save Profile"}
            </Button>
            <Button
              onClick={() => promoteToApplication.mutate()}
              disabled={!selectedGrantId || saveProfile.isPending || promoteToApplication.isPending}
              className="h-11 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#03141c] font-semibold"
            >
              {promoteToApplication.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
              {promoteToApplication.isPending ? "Promoting…" : "Promote to Application"}
            </Button>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Strategic Fit Score", value: `${strategicFitScore}%`, icon: Target, tone: "text-cyan-100" },
              { label: "Partner Pipeline", value: `${partners.length} active`, icon: Handshake, tone: "text-amber-100" },
              { label: "Budget Draft", value: `$${budgetTotal.toLocaleString()}`, icon: DollarSign, tone: "text-emerald-100" },
              { label: "Compliance Ready", value: `${readyCompliance}/${complianceItems.length}`, icon: ShieldCheck, tone: "text-sky-100" },
            ].map((stat, index) => {
              const Icon = stat.icon;
              return (
                <motion.div key={stat.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.05 }}>
                  <Card className="border border-cyan-900/40 bg-[#081c29]/85">
                    <CardContent className="pt-5">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-xs uppercase tracking-[0.18em] text-zinc-400">{stat.label}</div>
                          <div className="text-2xl font-semibold text-zinc-50 mt-2">{stat.value}</div>
                        </div>
                        <div className="h-11 w-11 rounded-2xl border border-cyan-300/20 bg-cyan-400/10 flex items-center justify-center">
                          <Icon className={`w-5 h-5 ${stat.tone}`} />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </div>
      </motion.section>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-zinc-100 flex items-center gap-2">
              <Target className="w-4 h-4 text-cyan-200" />
              Strategic Fit Score Workbench
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {profileQuery.isLoading && selectedGrantId && (
              <div className="flex items-center gap-2 text-sm text-zinc-300">
                <RefreshCw className="w-4 h-4 animate-spin" /> Loading saved planning profile…
              </div>
            )}
            <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
              <div className="space-y-3">
                <div>
                  <label className="text-xs uppercase tracking-[0.18em] text-zinc-400">Strategic north star</label>
                  <Textarea
                    value={northStar}
                    onChange={(event) => setNorthStar(event.target.value)}
                    className="mt-2 min-h-24 border-cyan-900/40 bg-[#081c29]/80 text-zinc-100"
                  />
                </div>

                <div className="space-y-3">
                  {priorities.map((priority) => (
                    <div key={priority.id} className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-zinc-100">{priority.label}</div>
                          <div className="text-xs text-zinc-400">Weight this criterion and score a target opportunity.</div>
                        </div>
                        <Badge variant="outline" className="border-cyan-300/40 bg-cyan-500/10 text-cyan-100">
                          Weight {priority.weight}
                        </Badge>
                      </div>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div>
                          <label className="text-xs uppercase tracking-[0.18em] text-zinc-500">Weight</label>
                          <Input
                            type="number"
                            min={1}
                            max={5}
                            value={priority.weight}
                            onChange={(event) => updatePriority(priority.id, "weight", Number(event.target.value) || 1)}
                            className="mt-2 h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                          />
                        </div>
                        <div>
                          <label className="text-xs uppercase tracking-[0.18em] text-zinc-500">Grant score</label>
                          <Input
                            type="number"
                            min={1}
                            max={5}
                            value={priority.score}
                            onChange={(event) => updatePriority(priority.id, "score", Number(event.target.value) || 1)}
                            className="mt-2 h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                          />
                        </div>
                      </div>
                      <Textarea
                        value={priority.rationale}
                        onChange={(event) => updatePriority(priority.id, "rationale", event.target.value)}
                        className="min-h-20 border-cyan-900/40 bg-[#061723]/90 text-zinc-200"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-3xl border border-cyan-300/20 bg-[linear-gradient(180deg,rgba(13,38,53,0.92),rgba(5,17,25,0.92))] p-5 space-y-4">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] text-cyan-100/75">Strategic fit score</div>
                  <div className="text-5xl font-semibold text-white mt-2">{strategicFitScore}%</div>
                </div>
                <div className="space-y-2 text-sm text-zinc-300">
                  <p>{northStar}</p>
                  <p>
                    Strongest signals: {strongestSignals.length > 0 ? strongestSignals.map((item) => item.label).join(", ") : "No strong signals yet."}
                  </p>
                  <p>
                    Watch items: {watchItems.length > 0 ? watchItems.map((item) => item.label).join(", ") : "No critical blockers identified."}
                  </p>
                </div>
                <div className="rounded-2xl border border-cyan-900/30 bg-[#081723]/70 p-4 text-sm text-zinc-300">
                  <div className="flex items-center gap-2 text-zinc-100 font-medium mb-2">
                    <Sparkles className="w-4 h-4 text-cyan-200" />
                    AI explanation draft
                  </div>
                  <p>
                    This opportunity is most defensible when the narrative emphasizes {strongestSignals[0]?.label?.toLowerCase() ?? "organizational alignment"}.
                    The main diligence gap is {watchItems[0]?.label?.toLowerCase() ?? "operational readiness"}, which should be resolved before drafting the final submission package.
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
            <CardHeader>
              <CardTitle className="text-zinc-100 flex items-center gap-2">
                <Handshake className="w-4 h-4 text-amber-200" />
                Collaboration Module
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {partners.map((partner) => (
                <div key={partner.id} className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-zinc-100">{partner.name}</div>
                      <div className="text-xs text-zinc-400">{partner.role}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => cyclePartnerStatus(partner.id)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${statusTone[partner.status]}`}
                      >
                        {partner.status}
                      </button>
                      <button
                        type="button"
                        onClick={() => removePartner(partner.id)}
                        className="text-zinc-500 hover:text-rose-400 transition-colors"
                        aria-label="Remove partner"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <p className="text-sm text-zinc-300">{partner.contribution}</p>
                </div>
              ))}
              <div className="rounded-2xl border border-dashed border-cyan-900/40 bg-[#081723]/50 p-4 space-y-3">
                <Input
                  value={newPartner.name}
                  onChange={(event) => setNewPartner((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Partner organization"
                  className="h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                />
                <Input
                  value={newPartner.role}
                  onChange={(event) => setNewPartner((current) => ({ ...current, role: event.target.value }))}
                  placeholder="Role in the proposal"
                  className="h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                />
                <Textarea
                  value={newPartner.contribution}
                  onChange={(event) => setNewPartner((current) => ({ ...current, contribution: event.target.value }))}
                  placeholder="Contribution, agreement notes, or deliverables"
                  className="min-h-20 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                />
                <Button onClick={addPartner} className="w-full rounded-xl bg-amber-400 text-[#201204] hover:bg-amber-300 font-semibold">
                  <Plus className="w-4 h-4" />
                  Add Partner
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
            <CardHeader>
              <CardTitle className="text-zinc-100 flex items-center gap-2">
                <ClipboardList className="w-4 h-4 text-sky-200" />
                Compliance Checklist Generator
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs uppercase tracking-[0.18em] text-zinc-400">Template</label>
                <select
                  value={grantType}
                  onChange={(event) => changeComplianceTemplate(event.target.value as keyof typeof complianceTemplates)}
                  className="mt-2 h-10 w-full rounded-lg border border-cyan-900/40 bg-[#061723]/90 px-3 text-sm text-zinc-100"
                >
                  <option value="federal">Federal grant</option>
                  <option value="foundation">Foundation grant</option>
                  <option value="state">State grant</option>
                </select>
              </div>
              <div className="space-y-3">
                {complianceItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => cycleComplianceStatus(item.id)}
                    className="w-full rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 text-left"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-zinc-100">{item.title}</div>
                        <div className="text-xs text-zinc-400 mt-1">Owner: {item.owner}</div>
                      </div>
                      <span className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${statusTone[item.status]}`}>
                        {item.status}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-zinc-100 flex items-center gap-2">
              <Scale className="w-4 h-4 text-emerald-200" />
              Budget Builder and Justification Stub
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              {budgetLines.map((line) => (
                <div key={line.id} className="grid gap-3 rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 md:grid-cols-[1fr_1.2fr_120px_140px_100px_36px]">
                  <Input
                    value={line.category}
                    onChange={(event) => updateBudgetLine(line.id, "category", event.target.value)}
                    className="h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                  />
                  <Input
                    value={line.item}
                    onChange={(event) => updateBudgetLine(line.id, "item", event.target.value)}
                    className="h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                  />
                  <Input
                    type="number"
                    value={line.quantity}
                    onChange={(event) => updateBudgetLine(line.id, "quantity", Number(event.target.value) || 0)}
                    className="h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                  />
                  <Input
                    type="number"
                    value={line.unitCost}
                    onChange={(event) => updateBudgetLine(line.id, "unitCost", Number(event.target.value) || 0)}
                    className="h-10 border-cyan-900/40 bg-[#061723]/90 text-zinc-100"
                  />
                  <div className="h-10 rounded-lg border border-cyan-900/40 bg-[#061723]/90 px-3 flex items-center justify-end text-sm text-zinc-100">
                    ${(line.quantity * line.unitCost).toLocaleString()}
                  </div>
                  <button
                    type="button"
                    onClick={() => removeBudgetLine(line.id)}
                    className="h-10 flex items-center justify-center text-zinc-500 hover:text-rose-400 transition-colors"
                    aria-label="Remove line"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
              <Button onClick={addBudgetLine} variant="outline" className="border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10">
                <Plus className="w-4 h-4" />
                Add Line Item
              </Button>
              <div className="rounded-2xl border border-emerald-300/20 bg-emerald-500/10 px-4 py-3 text-right">
                <div className="text-xs uppercase tracking-[0.18em] text-emerald-100/80">Requested total</div>
                <div className="text-2xl font-semibold text-emerald-50 mt-1">${budgetTotal.toLocaleString()}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
          <CardHeader>
            <CardTitle className="text-zinc-100 flex items-center gap-2">
              <BadgeCheck className="w-4 h-4 text-cyan-200" />
              Proposal Readiness Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 space-y-3">
              <div className="flex items-center gap-2 text-zinc-100 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-200" />
                Suggested next workflow
              </div>
              <p className="text-sm text-zinc-300">
                Lock the fit rationale, confirm partner commitments, then export the budget and compliance checklist into the application workspace.
              </p>
            </div>
            <div className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 space-y-2">
              <div className="text-xs uppercase tracking-[0.18em] text-zinc-400">Budget justification draft</div>
              <p className="text-sm text-zinc-300">{budgetJustification}</p>
            </div>
            <div className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4 space-y-2">
              <div className="text-xs uppercase tracking-[0.18em] text-zinc-400">Saved state</div>
              {savedProfileId ? (
                <div className="space-y-1 text-sm text-zinc-300">
                  <p>Profile #{savedProfileId} persisted to this grant.</p>
                  {linkedApplicationId && (
                    <button
                      type="button"
                      onClick={() => router.push(`/applications/${linkedApplicationId}`)}
                      className="flex items-center gap-1 text-cyan-300 hover:text-cyan-200 transition-colors"
                    >
                      <Link2 className="w-3.5 h-3.5" />
                      Linked to application #{linkedApplicationId}
                    </button>
                  )}
                  {lastSavedAt && (
                    <p className="text-zinc-500 text-xs">Last saved {lastSavedAt.toLocaleTimeString()}</p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-zinc-400">Select a grant and save to persist fit, partners, budget, and compliance as linked records.</p>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4">
                <div className="flex items-center gap-2 text-zinc-100 font-medium">
                  <Building2 className="w-4 h-4 text-amber-200" />
                  Partners ready
                </div>
                <div className="text-2xl font-semibold text-zinc-50 mt-2">
                  {partners.filter((partner) => partner.status === "confirmed").length}
                </div>
              </div>
              <div className="rounded-2xl border border-cyan-900/30 bg-[#081c29]/70 p-4">
                <div className="flex items-center gap-2 text-zinc-100 font-medium">
                  <ShieldCheck className="w-4 h-4 text-sky-200" />
                  Checklist ready
                </div>
                <div className="text-2xl font-semibold text-zinc-50 mt-2">{readyCompliance}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
