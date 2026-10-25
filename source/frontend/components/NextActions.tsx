"use client";
import {useQuery} from '@tanstack/react-query';
import Link from 'next/link';
import {api} from '@/lib/api';
export function NextActions(){
 const q=useQuery<{title:string;reason:string;href:string;due:string|null}[]>({queryKey:['next-actions'],queryFn:()=>api.get('/api/operations/next-actions').then(r=>r.data),retry:false});
 return <section className="glass p-5 rounded-xl"><h2 className="text-xl font-semibold mb-3">Your next actions</h2>{q.isLoading?<p>Loading actions…</p>:q.isError?<p className="text-amber-200">Actions unavailable. Check your organization assignment or <button className="underline" onClick={()=>q.refetch()}>retry</button>.</p>:!q.data?.length?<p className="text-zinc-400">No pending actions in your organization records.</p>:<ul className="space-y-3">{q.data.map((a,i)=><li key={i}><Link className="text-cyan-200 underline" href={a.href}>{a.title}</Link><p className="text-sm text-zinc-400">{a.reason}{a.due?' · Due '+a.due.slice(0,10):''}</p></li>)}</ul>}</section>;
}
