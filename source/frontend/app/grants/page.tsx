"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { postGrantFlowQuery } from "@/lib/query";
import { GrantListItem, parseGrantList } from "@/lib/grants";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Search, ExternalLink, Sparkles, RefreshCw, Building2, DollarSign, Wand2 } from "lucide-react";
import { toast } from "sonner";
import GrantDetails from "@/components/GrantDetails";
import { FormEvent } from 'react';

export default function GrantsPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [applyingId, setApplyingId] = useState<number | null>(null);
  const me=useQuery<{role:string}>({queryKey:['me'],queryFn:()=>api.get('/api/auth/me').then(r=>r.data)});
  const [showManual,setShowManual]=useState(false);
  const [manualError,setManualError]=useState('');
  async function saveOpportunity(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setManualError('');const f=new FormData(e.currentTarget);
    try{await api.post('/api/grants/',{title:f.get('title'),funding_agency:f.get('funding_agency'),description:f.get('description'),source_url:f.get('source_url')||null});setShowManual(false);await queryClient.invalidateQueries({queryKey:['grants']});}
    catch{setManualError('Opportunity could not be saved. Check the fields and your administrator access.');}
  }

  const {
    data: grants = [],
    isLoading,
    isError,
    error,
    isFetching,
    refetch,
  } = useQuery<GrantListItem[]>({
    queryKey: ["grants", search, category],
    queryFn: () =>
      postGrantFlowQuery(
        "/api/grants/search",
        {
          query: search || undefined,
          category: category || undefined,
          offset: 0,
          limit: 50,
        },
        parseGrantList
      ),
    retry: 1,
  });

  const discover = useMutation({
    mutationFn: () =>
      api.post("/api/automation/jobs", {
        job_type: "scrape",
        params: {query: search || "youth literacy mentoring education nonprofit"},
      }),
    onSuccess: (res) => {
      toast.success(`Discovery job #${res.data.id} queued. Review progress in Automation.`);
      router.push('/automation');
    },
    onError: (error: unknown) => toast.error((error as {response?:{data?:{detail?:string}}}).response?.data?.detail || "Grant discovery failed"),
  });

  const applyWithAi = useMutation({
    mutationFn: async (grant: GrantListItem) => {
      setApplyingId(grant.id);
      const create = await api.post("/api/applications/", {
        grant_id: grant.id,
        title: grant.title,
        amount_requested: grant.amount,
      });
      const appId = create.data?.id;
      let generated = false;
      try {
        await api.post("/api/ai/generate", {
          application_id: appId,
          grant_id: grant.id,
          task: "proposal",
          stream: false,
        });
        generated = true;
      } catch {
        /* AI may be unavailable; application is still created */
      }
      return {appId:appId as number, generated};
    },
    onSuccess: ({appId,generated}) => {
      if(generated) toast.success("Application drafted with AI");
      else toast.warning("Application saved, but AI generation failed. Retry AI Fill on the application page.");
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      router.push(`/applications/${appId}`);
    },
    onError: () => toast.error("Could not start AI application"),
    onSettled: () => setApplyingId(null),
  });

  const featured = grants?.slice(0, 3) ?? [];
  const sourcedCount = grants?.filter((grant) => !!grant.source_url).length ?? 0;

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
        <div className="glass p-5 sm:p-6 rounded-2xl overflow-hidden relative border border-cyan-900/40">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.22),transparent_35%),radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.14),transparent_30%)]" />
          <div className="relative space-y-4">
            <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2 mb-2">
                  <Badge variant="outline" className="border-cyan-300/50 bg-cyan-500/10 text-cyan-100">Source Radar</Badge>
                  <Badge variant="outline" className="border-emerald-300/40 bg-emerald-500/10 text-emerald-100">Live Public Feeds</Badge>
                </div>
                <h1 className="text-3xl font-semibold text-zinc-50">Grant Discovery Engine</h1>
                {me.data?.role==='admin'&&<Button type="button" onClick={()=>setShowManual(!showManual)}>Add opportunity</Button>}
                {showManual&&<form onSubmit={saveOpportunity} className="space-y-3 rounded border border-slate-700 p-4">
                  <label className="block">Opportunity title<Input name="title" required minLength={3} maxLength={500}/></label>
                  <label className="block">Funding agency<Input name="funding_agency" maxLength={255}/></label>
                  <label className="block">Source URL<Input name="source_url" type="url"/></label>
                  <label className="block">Description<textarea name="description" maxLength={20000} className="block w-full bg-slate-900 p-2"/></label>
                  <p className="text-xs text-slate-300">Opportunities are shared catalog records. Keep private proposal details in an application.</p>
                  {manualError&&<p role="alert">{manualError}</p>}
                  <Button type="submit">Save opportunity</Button>
                </form>}
                <p className="text-zinc-200 text-sm max-w-2xl">
                  Search sourced opportunities, queue fresh listings, and compare evidence against your organization profile.
                </p>
              </div>
              <Button
                onClick={() => discover.mutate()}
                disabled={discover.isPending}
                className="h-10 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#02131b] font-semibold"
              >
                {discover.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Discover New Grants
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="rounded-xl border border-cyan-900/40 bg-[#0d2635]/75 p-4">
                <div className="text-zinc-300 text-xs uppercase tracking-[0.2em] mb-2">Visible Grants</div>
                <div className="text-2xl font-semibold text-cyan-50">{grants?.length ?? 0}</div>
              </div>
              <div className="rounded-xl border border-cyan-900/40 bg-[#0d2635]/75 p-4">
                <div className="text-zinc-300 text-xs uppercase tracking-[0.2em] mb-2">Source Links</div>
                <div className="text-2xl font-semibold text-cyan-50">{sourcedCount}</div>
              </div>
              <div className="rounded-xl border border-cyan-900/40 bg-[#0d2635]/75 p-4">
                <div className="text-zinc-300 text-xs uppercase tracking-[0.2em] mb-2">Top Match</div>
                <div className="text-2xl font-semibold text-cyan-50">{featured[0]?.ai_match_score !== undefined ? `${Math.round(featured[0].ai_match_score)}/100` : "-"}</div>
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 w-4 h-4" />
          <Input
            className="h-10 pl-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100"
            placeholder="Search grants by keyword, agency, or category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Input
          className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 sm:w-44"
          placeholder="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <Button
          onClick={() => queryClient.invalidateQueries({ queryKey: ["grants"] })}
          variant="outline"
          className="h-10 border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10"
        >
          Search
        </Button>
      </div>

      {!isError && featured.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {featured.map((grant) => (
            <motion.div
              key={`featured-${grant.id}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card className="border border-cyan-900/40 bg-[#0b2231]/85 h-full">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <Badge variant="outline" className="border-emerald-300/40 bg-emerald-500/10 text-emerald-100">
                      {grant.ai_match_score ? `${Math.round(grant.ai_match_score)}/100 alignment` : "New"}
                    </Badge>
                    {grant.source_url && <ExternalLink className="w-4 h-4 text-zinc-400" />}
                  </div>
                  <CardTitle className="text-lg font-semibold text-zinc-50 line-clamp-2 mt-2">{grant.title}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-center gap-2 text-sm text-zinc-300">
                    <Building2 className="w-4 h-4" />
                    <span className="line-clamp-1">{grant.funding_agency || "Unknown agency"}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-zinc-300">
                    <DollarSign className="w-4 h-4" />
                    <span>{grant.amount ? `$${grant.amount.toLocaleString()}` : "Amount TBD"}</span>
                  </div>
                  <p className="text-sm text-zinc-300 line-clamp-3">{grant.ai_summary || grant.eligibility || "AI fit summary will appear here."}</p>
                  <Button
                    onClick={() => applyWithAi.mutate(grant)}
                    disabled={applyingId === grant.id}
                    className="w-full mt-3 h-9 rounded-xl bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-[#02131b] font-semibold"
                  >
                    {applyingId === grant.id ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Wand2 className="w-4 h-4" />
                    )}
                    {applyingId === grant.id ? "Drafting…" : "Apply with AI"}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        {isLoading ? (
          <div className="text-zinc-300 text-sm">Loading grants...</div>
        ) : isError ? (
          <Card className="border border-rose-500/30 bg-[#201015]/90">
            <CardContent className="py-8 space-y-3">
              <p className="text-zinc-100 text-sm font-medium">Grant Discovery could not load results.</p>
              <p className="text-zinc-400 text-xs">
                {error instanceof Error ? error.message : "The grant search request timed out or failed."}
              </p>
              <Button
                onClick={() => refetch()}
                disabled={isFetching}
                variant="outline"
                className="h-9 border-cyan-700/50 bg-[#0d2635]/80 text-zinc-100 hover:bg-cyan-500/10"
              >
                {isFetching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                Retry Search
              </Button>
            </CardContent>
          </Card>
        ) : grants.length === 0 ? (
          <div className="text-zinc-300 text-sm">No grants found.</div>
        ) : (
          grants.map((grant) => (
            <motion.div
              key={grant.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card className="border border-cyan-900/40 bg-[#0a1f2d]/85">
                <CardContent className="py-4 flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className="border-cyan-400/30 bg-cyan-500/10 text-cyan-100">
                        {grant.category || "General"}
                      </Badge>
                      {grant.ai_match_score !== undefined && grant.ai_match_score !== null && (
                        <span className="text-xs text-emerald-300 font-medium">
                          {Math.round(grant.ai_match_score)}/100 alignment
                        </span>
                      )}
                    </div>
                    <h3 className="text-zinc-100 font-medium text-sm truncate">{grant.title}</h3>
                    <p className="text-zinc-300 text-xs mt-0.5">
                      {grant.funding_agency || "Unknown Agency"} · {grant.amount ? `$${grant.amount.toLocaleString()}` : "Amount TBD"} · {grant.deadline_str || "No deadline"}
                    </p>
                    {grant.ai_summary && <p className="text-zinc-300 text-xs mt-2 line-clamp-2">{grant.ai_summary}</p>}
                    <GrantDetails id={grant.id}/>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {grant.source_url && (
                      <a
                        href={grant.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label="Open source"
                        className="p-2 rounded-md hover:bg-cyan-400/10 text-zinc-300"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                    <Button
                      onClick={() => applyWithAi.mutate(grant)}
                      disabled={applyingId === grant.id}
                      className="h-9 rounded-xl bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-[#02131b] font-semibold"
                    >
                      {applyingId === grant.id ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Wand2 className="w-3.5 h-3.5" />
                      )}
                      <span className="hidden sm:inline">{applyingId === grant.id ? "Drafting" : "Apply with AI"}</span>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
