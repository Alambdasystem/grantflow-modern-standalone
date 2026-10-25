"use client";
import {useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {api} from '@/lib/api';

type EvidenceDate={as_of:string;review_due:string;date_confirmed:boolean;stale:boolean;basis:string};
type ReviewItem={id:number;status:string;current:boolean;extraction_revision:string;freshness:EvidenceDate;extracted?:{text:string}};
function message(e:unknown){const detail=(e as {response?:{data?:{detail?:unknown}}}).response?.data?.detail;return typeof detail==='string'?detail:'Could not save. Check the fields and try again.';}

export function ReviewTools({item,canReview}:{item:ReviewItem;canReview:boolean}){
 const qc=useQueryClient();
 const [editing,setEditing]=useState(false),[text,setText]=useState(''),[reason,setReason]=useState(''),[revision,setRevision]=useState('');
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const [asOf,setAsOf]=useState(item.freshness.as_of),[due,setDue]=useState(item.freshness.review_due);
 const history=useQuery<{id:number;actor:number;at:string;reason:string;diff:string;truncated:boolean}[]>({queryKey:['ingestion-corrections',item.id],queryFn:()=>api.get(`/api/ingestion/documents/${item.id}/corrections`).then(r=>r.data)});
 async function refresh(){await Promise.all(['ingestion','ingestion-detail','ingestion-search','ingestion-monitor','ingestion-corrections'].map(key=>qc.invalidateQueries({queryKey:[key]})));}
 async function saveCorrection(){setBusy(true);setNotice('');try{
  await api.post(`/api/ingestion/documents/${item.id}/corrections`,{text,reason,revision});setEditing(false);setConfirmed(false);await refresh();setNotice('Correction recorded. Review and approve the corrected extraction before AI use.');
 }catch(e){setNotice(message(e));}finally{setBusy(false);}}
 async function saveDates(){setBusy(true);setNotice('');try{await api.put(`/api/ingestion/documents/${item.id}/freshness`,{as_of:asOf,review_due:due});await refresh();setNotice('Evidence dates saved.');}catch(e){setNotice(message(e));}finally{setBusy(false);}}
 return <section className="space-y-3 border-t border-zinc-700 pt-3">
  <h4 className="font-semibold">Evidence freshness</h4>
  <p className={item.freshness.stale?'text-amber-300':'text-zinc-300'}>{item.freshness.stale?'Evidence review overdue':'Evidence review due'}: {item.freshness.review_due}. {item.freshness.basis}.</p>
  <p className="text-sm text-zinc-400">Checking unchanged source files does not renew their evidence dates. Dates are reminders; overdue evidence remains searchable until replaced or removed.</p>
  {canReview&&item.current&&item.status!=='deleted'&&<details><summary className="cursor-pointer">Set evidence dates</summary><div className="flex flex-wrap gap-3 mt-2">
   <label>Evidence as of<input aria-label="Evidence as of" type="date" value={asOf} onChange={e=>setAsOf(e.target.value)} className="block bg-zinc-900 border rounded p-2"/></label>
   <label>Review due<input aria-label="Evidence review due" type="date" value={due} onChange={e=>setDue(e.target.value)} className="block bg-zinc-900 border rounded p-2"/></label>
   <button disabled={busy||!asOf||!due} onClick={saveDates} className="underline">Save evidence dates</button>
  </div></details>}
  {canReview&&item.current&&item.status==='needs_review'&&!editing&&<button className="underline text-cyan-300" onClick={()=>{setText(item.extracted?.text||'');setRevision(item.extraction_revision);setReason('');setConfirmed(false);setEditing(true);}}>Correct extracted text and table values</button>}
  {editing&&<div className="space-y-3 rounded border border-amber-600 p-3">
   <p>Edit the complete transcription, including table values. The original file stays unchanged. This replaces the structured preview with your corrected text so old cells cannot remain as conflicting evidence.</p>
   <label className="block">Corrected extraction<textarea aria-label="Corrected extraction" className="w-full bg-zinc-900 border rounded p-2 font-mono text-sm min-h-64" maxLength={500000} value={text} onChange={e=>{setText(e.target.value);setConfirmed(false);}}/></label>
   <label className="block">Correction reason<input aria-label="Correction reason" className="block w-full bg-zinc-900 border rounded p-2" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label>
   <label className="block"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> Record these corrections and retain the original for comparison.</label>
   {revision!==item.extraction_revision&&<p role="alert">The extraction changed while you were editing. Cancel and reopen the editor before saving.</p>}
   <div className="flex gap-3"><button className="rounded bg-cyan-700 p-2 disabled:opacity-40" disabled={busy||!confirmed||reason.trim().length<5||!text.trim()||revision!==item.extraction_revision} onClick={saveCorrection}>Save correction for review</button><button disabled={busy} className="underline" onClick={()=>setEditing(false)}>Cancel correction</button></div>
  </div>}
  {notice&&<p role="status">{notice}</p>}
  <details><summary className="cursor-pointer">Correction audit ({history.data?.length||0} recent)</summary>{history.isError&&<p role="alert">Correction history could not be loaded.</p>}{history.data?.map(h=><article key={h.id} className="border-t border-zinc-700 py-2"><p>{h.at} - user {h.actor}: {h.reason}</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs">{h.diff}</pre>{h.truncated&&<p>Preview shortened. Full snapshots are retained in the correction audit store.</p>}</article>)}</details>
 </section>;
}

type Monitor={counts:Record<string,number>;oldest_pending_seconds:number;stale_documents:number;coordinator_status:string;last_poll_at:string|null;local_extraction_enabled:boolean;alerts:string[];workers:{id:string;status:string;last_seen:string|null}[];failures:{id:number;name:string;error:string;attempts:number;retry_at:string|null}[];freshness_items:{id:number;name:string;review_due:string}[]};
export function IngestionMonitor({select}:{select:(id:number)=>void}){
 const query=useQuery<Monitor>({queryKey:['ingestion-monitor'],queryFn:()=>api.get('/api/ingestion/monitor').then(r=>r.data),refetchInterval:10000});
 const m=query.data;
 return <section className="rounded-xl border border-zinc-700 p-5 space-y-3"><h2 className="text-xl">Ingestion health</h2>
 {query.isError&&<p role="alert" className="text-red-300">Monitoring is unavailable. Service health is unknown; retry or contact the operator.</p>}
 {m&&<><div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[['Queued',m.counts.queued||0],['Processing',m.counts.processing||0],['Needs review',m.counts.needs_review||0],['Failed',m.counts.failed||0],['Ready',m.counts.ready||0],['Evidence overdue',m.stale_documents]].map(([label,count])=><div key={label} className="border border-zinc-700 rounded p-3"><p className="text-sm">{label}</p><strong className="text-2xl">{count}</strong></div>)}</div>
 <p>Oldest pending job: {Math.floor(m.oldest_pending_seconds/60)} minutes. Coordinator: {m.coordinator_status.replaceAll('_',' ')}. Local extraction: {m.local_extraction_enabled?'enabled':'disabled'}.</p>
 <p className="text-sm text-zinc-400">Last coordinator poll: {m.last_poll_at||'Not observed'}. Alerts refresh while this page is open; no email notifications are sent.</p>
 {m.alerts.map(a=><p key={a} role="alert" className="rounded border border-amber-600 p-2 text-amber-200">{a}</p>)}
 <details><summary>Extraction workers ({m.workers.length})</summary>{m.workers.length===0&&<p>No remote workers assigned; local extraction is shown above.</p>}{m.workers.map(w=><p key={w.id}>{w.id}: {w.status.replaceAll('_',' ')} - last contact {w.last_seen||'never'}</p>)}</details>
 {m.failures.map(f=><div key={f.id}><button className="underline text-red-300" onClick={()=>select(f.id)}>{f.name}: {f.error}</button><p className="text-sm">Attempts: {f.attempts}. {f.retry_at?`Retry scheduled: ${f.retry_at}`:'Manual retry required.'}</p></div>)}
 {m.freshness_items.length>0&&<details><summary>Evidence needing a freshness review</summary>{m.freshness_items.map(d=><button key={d.id} className="block underline" onClick={()=>select(d.id)}>{d.name} - due {d.review_due}</button>)}</details>}
 </>}
 </section>;
}
