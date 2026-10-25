"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Knowledge = {
  refreshed_at: string; fingerprint: string; note: string;
  recommendations: {category: string; reason: string}[];
  sources: {id: number; type: string; title: string; revision: number | null; needs_review: boolean; review_due?: string}[];
};

export default function KnowledgeStatus() {
  const state = useQuery<Knowledge>({queryKey:["knowledge-status"],
    queryFn:()=>api.get('/api/operations/knowledge-status').then(r=>r.data), refetchInterval:60000});
  return <section className="rounded-xl border border-zinc-700 p-4 space-y-3" aria-label="Knowledge freshness">
    <div className="flex justify-between gap-3"><h2 className="text-xl">Knowledge freshness &amp; document recommendations</h2>
      <button className="underline" disabled={state.isFetching} onClick={()=>state.refetch()}>Refresh sources</button></div>
    {state.isLoading?<p>Checking current sources...</p>:state.isError?<p role="alert">Unable to check knowledge sources. Retry refresh.</p>:state.data&&<>
      <p className="text-sm text-zinc-400">Checked {new Date(state.data.refreshed_at).toLocaleString()}. Current saved sources are read for each AI request. This page refreshes every minute.</p>
      <p>{state.data.note}</p>
      {state.data.recommendations.length?<ul className="list-disc pl-6">{state.data.recommendations.map(r=><li key={r.category}><strong>{r.category.replaceAll('_',' ')}:</strong> {r.reason}</li>)}</ul>:<p>All source categories are present; human verification is still required.</p>}
      <details><summary className="cursor-pointer">Source inventory ({state.data.sources.length})</summary>
        <ul className="space-y-2 mt-3">{state.data.sources.map(s=><li key={`${s.type}-${s.id}`}>{s.title} ({s.type}{s.revision?`, revision ${s.revision}`:''}){s.needs_review&&<strong className="text-amber-300"> — Review overdue since {s.review_due}</strong>}</li>)}</ul>
      </details>
    </>}
  </section>;
}
