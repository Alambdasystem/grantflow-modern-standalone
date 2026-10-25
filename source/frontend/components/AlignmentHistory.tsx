"use client";
import { useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Run = { id:number; revision:number; data:{at:string; matches:{grant_id:number;title:string;score:number;scoring_version:string}[];feedback:{grant_id:number;useful:boolean;reason:string;actor:string}[]} };
export default function AlignmentHistory({writable}:{writable:boolean}) {
 const qc=useQueryClient(); const [notice,setNotice]=useState("");
 const [selected,setSelected]=useState(""); const [reason,setReason]=useState(""); const [useful,setUseful]=useState(true);
 const runs=useQuery<Run[]>({queryKey:["alignment-runs"],queryFn:()=>api.get('/api/operations/alignment-runs').then(r=>r.data)});
 const refresh=()=>qc.invalidateQueries({queryKey:["alignment-runs"]});
 const save=useMutation({mutationFn:()=>api.post('/api/operations/alignment-runs'),onSuccess:()=>{refresh();setNotice('Evaluation saved with source revisions and profile fingerprint.');},onError:()=>setNotice('Could not save evaluation. Please retry.')});
 const feedback=useMutation({mutationFn:()=>{const [runId,grantId]=selected.split(':').map(Number);const run=runs.data?.find(r=>r.id===runId);return api.post(`/api/operations/alignment-runs/${runId}/feedback`,{grant_id:grantId,useful,reason,revision:run?.revision});},onSuccess:()=>{refresh();setReason('');setNotice('Feedback recorded. Scores were not silently changed.');},onError:()=>{refresh();setNotice('Feedback could not be saved. Reload the evaluation and retry.');}});
 return <section className="border border-zinc-700 rounded-xl p-5 space-y-4">
  <h2 className="text-xl">Alignment evaluation history</h2>
  <p className="text-sm text-zinc-400">Save an evaluation before and after knowledge or profile changes to compare scores. Feedback records human judgments for review; it does not train a model or imply funding probability.</p>
  {writable&&<button className="bg-cyan-700 rounded px-4 py-2" disabled={save.isPending} onClick={()=>save.mutate()}>Save current evaluation</button>}
  {notice&&<p role="status">{notice}</p>}
  {runs.isLoading?<p>Loading evaluations…</p>:runs.isError?<p role="alert">Evaluations unavailable. <button onClick={()=>runs.refetch()}>Retry</button></p>:!runs.data?.length?<p>No saved evaluations yet.</p>:runs.data.map((run,i)=><details key={run.id}><summary>{new Date(run.data.at).toLocaleString()} · {run.data.matches.length} grants · {run.data.feedback.length} feedback entries</summary>
   <ul className="space-y-2 mt-2">{run.data.matches.map(m=>{const before=runs.data?.[i+1]?.data.matches.find(old=>old.grant_id===m.grant_id);return <li key={m.grant_id}>{m.title}: {m.score}/100 {before&&<span>({m.score-before.score>=0?'+':''}{Math.round((m.score-before.score)*10)/10} from previous evaluation)</span>} · {m.scoring_version}</li>;})}</ul>
   {run.data.feedback.map((f,j)=><p key={j}>Grant {f.grant_id}: {f.useful?'Useful':'Needs improvement'} — {f.reason} ({f.actor})</p>)}
  </details>)}
  {writable&&!!runs.data?.length&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();feedback.mutate();}}><label className="block">Evaluate a recommendation<select required className="block bg-zinc-900 border rounded p-2 w-full" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select evaluation and grant</option>{runs.data.map(r=>r.data.matches.map(m=><option key={`${r.id}:${m.grant_id}`} value={`${r.id}:${m.grant_id}`}>Evaluation {r.id}: {m.title}</option>))}</select></label>
   <label className="block">Judgment<select className="block bg-zinc-900 p-2" value={String(useful)} onChange={e=>setUseful(e.target.value==='true')}><option value="true">Useful recommendation</option><option value="false">Needs improvement</option></select></label>
   <label className="block">Reason<textarea required maxLength={2000} className="block w-full bg-zinc-900 border rounded p-2" value={reason} onChange={e=>setReason(e.target.value)}/></label><button disabled={feedback.isPending} className="border rounded px-4 py-2">Record feedback</button>
  </form>}
 </section>;
}
