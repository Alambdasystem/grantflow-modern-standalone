"use client";
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
export default function RuntimeNotice(){
  const status=useQuery({queryKey:['runtime'],queryFn:()=>api.get('/api/runtime').then(r=>r.data),refetchInterval:60000,retry:false});
  if(!status.data||status.data.authentication!=='standalone')return null;
  return <p className="rounded border border-slate-700 bg-slate-900 p-3 text-sm text-slate-300">AI: {status.data.ai.ready?(status.data.ai.provider==='alambda'?'Alambda chat recently verified':'approved model ready'):status.data.ai.reason.replaceAll('_',' ')}. {!status.data.email_safety_connected&&'Email Safety is not connected; no email actions are available.'}</p>;
}
