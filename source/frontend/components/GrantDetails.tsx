"use client";
import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import Link from 'next/link';
import {api} from '@/lib/api';

type Detail = {
 grant:{description:string|null;eligibility:string|null;deadline:string|null;deadline_str:string|null;amount:number|null;amount_max:number|null;source_url:string|null};
 alignment:{score:number;scoring_version:string;missing_information:string[];factors:{name:string;score:number;weight:number;evidence:unknown}[]};
 requirements:unknown;requirements_fetched_at:string|null;requirements_warning?:string|null;
 source_review?:{status:string;reason?:string;retrieved_at?:string;fields?:{deadline?:string;application_url?:string};evidence?:{url:string}[]}|null;
 applications:{id:number;title:string;status:string;updated_at:string}[];
 reviews:{id:number;application_id:number;status:string;feedback:string;created_at:string}[];
 workflows:{application_id:number;stage:string;status:string}[];
 documents:{id:number;title:string;type:string|null}[];
};

export default function GrantDetails({id}:{id:number}) {
 const [open,setOpen]=useState(false);
 const query=useQuery<Detail>({queryKey:['grant-workspace',id],queryFn:()=>api.get(`/api/grants/${id}/workspace`).then(r=>r.data),enabled:open,retry:false});
 const d=query.data;
 return <details className="mt-3 border-t border-cyan-900/40 pt-3 text-sm" onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary className="cursor-pointer text-cyan-200">Grant details, alignment &amp; activity</summary>
  {query.isLoading?<p>Loading grant details...</p>:query.isError?<p role="alert">Unable to load grant details. <button className="underline" onClick={()=>query.refetch()}>Retry</button></p>:d&&<div className="space-y-4 mt-3 break-words">
   <p className="whitespace-pre-wrap">{d.grant.description||'Description not provided.'}</p>
   <p><strong>Eligibility:</strong> {d.grant.eligibility||'Source review required.'}</p>
   <p><strong>Deadline:</strong> {d.grant.deadline||d.grant.deadline_str||'Not provided'}</p>
   <p><strong>Funding:</strong> {d.grant.amount===null?'Not provided':`$${d.grant.amount.toLocaleString()}`}{d.grant.amount_max!==null?` to $${d.grant.amount_max.toLocaleString()}`:''}</p>
   <h4 className="font-semibold">Alignment: {d.alignment.score}/100</h4>
   <p>Evidence alignment, not award probability. {d.alignment.scoring_version}</p>
   {d.alignment.factors.map(f=><p key={f.name}>{f.name}: {f.score}/{f.weight}. Evidence: {JSON.stringify(f.evidence)}</p>)}
   <p>Missing evidence: {d.alignment.missing_information.join(', ')||'None recorded'}</p>
   <h4 className="font-semibold">Submission requirements</h4>
   {d.requirements_warning&&<p role="alert" className="text-amber-300">{d.requirements_warning}</p>}
   {d.requirements_warning&&<p>You can continue drafting. Submission readiness remains unconfirmed until the missing source evidence is reviewed.</p>}
   {d.source_review&&<div><p>Source review: {d.source_review.status==='verified'?'Source association verified':'Needs source verification'} · {d.source_review.retrieved_at}</p><p>{d.source_review.reason}</p>{d.source_review.fields?.deadline&&<p>Reviewed deadline: {d.source_review.fields.deadline}. A historical deadline does not reopen an opportunity.</p>}{d.source_review.evidence?.map(e=><p key={e.url}><a className="underline break-all" href={e.url} target="_blank" rel="noreferrer">Authoritative source evidence</a></p>)}</div>}
   <p>Last retrieved: {d.requirements_fetched_at||'Not yet retrieved; verify the funder source.'}</p>
   <pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(d.requirements,null,2)}</pre>
   {d.grant.source_url&&/^https?:\/\//.test(d.grant.source_url)&&<a className="underline" href={d.grant.source_url} target="_blank" rel="noreferrer">Verify funder source</a>}
   <h4 className="font-semibold">Applications &amp; progress</h4>
   {!d.applications.length?<p>No accessible applications for this grant.</p>:d.applications.map(a=><div key={a.id}><Link className="underline" href={`/applications/${a.id}`}>{a.title||`Application ${a.id}`}</Link> — {a.status}<p>Updated {new Date(a.updated_at).toLocaleString()}</p>{d.workflows.filter(w=>w.application_id===a.id).map(w=><p key={w.stage}>{w.stage}: {w.status}</p>)}</div>)}
   <h4 className="font-semibold">Approval activity</h4>
   {!d.reviews.length?<p>No review recorded.</p>:d.reviews.map(r=><p key={r.id}>Application {r.application_id}: {r.status} — {r.feedback} ({new Date(r.created_at).toLocaleString()})</p>)}
   <h4 className="font-semibold">Supporting documents</h4>
   {!d.documents.length?<p>No accessible uploaded documents.</p>:d.documents.map(x=><p key={x.id}>{x.title} ({x.type||'document'})</p>)}
   <Link className="underline" href="/operations">Review organizational knowledge and document recommendations</Link>
  </div>}
 </details>;
}
