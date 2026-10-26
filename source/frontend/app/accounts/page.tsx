"use client";
import { useState, FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

type User={id:number;username:string;email:string;role:string;is_active:boolean};
export default function Accounts(){
  const me=useQuery<User>({queryKey:['me'],queryFn:()=>api.get('/api/auth/me').then(r=>r.data)});
  const users=useQuery<User[]>({queryKey:['accounts'],enabled:me.data?.role==='admin',queryFn:()=>api.get('/api/users/').then(r=>r.data)});
  const orgs=useQuery<{id:number;name:string}[]>({queryKey:['organizations'],enabled:me.data?.role==='admin',queryFn:()=>api.get('/api/organizations/').then(r=>r.data)});
  const [url,setUrl]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  async function invite(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError('');setUrl('');
    const form=new FormData(e.currentTarget);const reset=Number(form.get('reset_user_id'))||null;
    try{
      const r=await api.post('/api/auth/invitations',{email:form.get('email'),role:form.get('role'),organization_id:Number(form.get('organization_id')),reset_user_id:reset});
      setUrl(r.data.url);
    }catch(e:unknown){setError(e instanceof Error?e.message:'Invitation failed.');}finally{setBusy(false);}
  }
  if(me.isLoading)return <p>Loading account permissions…</p>;
  if(me.data?.role!=='admin')return <p>Administrator access is required to manage accounts.</p>;
  return <main className="max-w-4xl mx-auto p-6 space-y-6 text-slate-100">
    <h1 className="text-3xl font-semibold">Accounts and invitations</h1>
    <p>Accounts belong to this GrantFlow installation. Invitation and recovery links expire after 24 hours and can be used once. Share links privately; this app does not email them.</p>
    {error&&<p role="alert" className="text-red-300">{error}</p>}
    <form onSubmit={invite} className="grid gap-4 rounded border border-slate-700 p-5">
      <label>Email<input className="block w-full bg-slate-800 p-2 rounded" name="email" type="email" required/></label>
      <label>Organization<select className="block w-full bg-slate-800 p-2 rounded" name="organization_id" required>{orgs.data?.map(o=><option key={o.id} value={o.id}>{o.name} (ID {o.id})</option>)}</select></label>
      <label>Role for a new account<select name="role" className="block w-full bg-slate-800 p-2 rounded">{['grant_writer','reviewer','viewer','admin'].map(r=><option key={r}>{r}</option>)}</select></label>
      <label>Recovery account ID (leave blank for a new account)<input name="reset_user_id" type="number" min={1} className="block w-full bg-slate-800 p-2 rounded"/></label>
      <p className="text-sm text-slate-400">Recovery requires the exact existing account ID, email and organization and preserves its role and ownership.</p>
      <button disabled={busy} className="rounded bg-cyan-700 px-4 py-2 disabled:opacity-50">{busy?'Creating…':'Create private link'}</button>
    </form>
    {url&&<section className="p-4 border border-cyan-700 rounded"><p>Copy this private link now. It is shown once.</p><textarea aria-label="Private invitation link" readOnly value={url} className="w-full bg-slate-800 p-2"/><button onClick={()=>navigator.clipboard.writeText(url)}>Copy link</button></section>}
    <h2 className="text-xl">Existing accounts</h2>
    {users.isError&&<p role="alert">Accounts could not be loaded.</p>}
    <ul className="space-y-3">{users.data?.map(u=><li key={u.id} className="border border-slate-700 rounded p-3">ID {u.id}: {u.username} · {u.email} · {u.role} · {u.is_active?'active':'disabled'}
      {u.id!==me.data?.id&&<button className="ml-4 underline" onClick={async()=>{try{await api.patch('/api/auth/accounts/'+u.id,{is_active:!u.is_active,role:u.role});await users.refetch();}catch{setError('Account change failed.');}}}>{u.is_active?'Disable and revoke sessions':'Enable account'}</button>}
    </li>)}</ul>
  </main>;
}
