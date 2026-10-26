"use client";

import { useEffect, useState, FormEvent } from 'react';

export default function LoginPage() {
  const [mode,setMode]=useState('loading');
  const [setup,setSetup]=useState(false);
  const [invite,setInvite]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  useEffect(()=>{
    const fragment=new URLSearchParams(window.location.hash.slice(1));
    const token=fragment.get('invite')||'';
    if(token){setInvite(token);window.history.replaceState(null,'',window.location.pathname);}
    fetch('/gfm-app/api/auth/status',{cache:'no-store'}).then(async r=>{
      if(!r.ok)throw new Error('Sign-in is unavailable. Try again shortly.');
      const data=await r.json();setMode(data.mode);setSetup(data.setup_required);
      if(data.mode==='anthesis')window.location.replace('/auth/login?next=%2Fgfm-app%2Fdashboard');
    }).catch(e=>{setMode('error');setError(e.message);});
  },[]);
  async function submit(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError('');
    const form=new FormData(e.currentTarget);
    const payload:Record<string,unknown>={username:form.get('username'),password:form.get('password')};
    let action='login';
    if(invite){action='accept';payload.token=invite;}
    else if(setup){action='setup';payload.email=form.get('email');payload.organization=form.get('organization');payload.bootstrap_token=form.get('bootstrap_token');}
    try{
      const r=await fetch('/gfm-app/api/auth/'+action,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const data=await r.json();
      if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check the form and try again.');
      if(invite){setInvite('');setSetup(false);setNotice('Account saved. Sign in with your password.');return;}
      localStorage.removeItem('authToken');localStorage.removeItem('gfm_token');
      // A display hint only; the HttpOnly server cookie authorizes all API access.
      localStorage.setItem('gfm_session_hint','1');
      const next=new URLSearchParams(window.location.search).get('next')||'/gfm-app/dashboard';
      const safe=next.startsWith('/gfm-app/')&&!/[\\\r\n]/.test(next)&&!next.includes('//')&&!next.includes('..');
      window.location.replace(safe?next:'/gfm-app/dashboard');
    }catch(e){setError(e instanceof Error?e.message:'Sign-in failed. Try again.');}
    finally{setBusy(false);}
  }
  return <main className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100 px-6">
    <section className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-8 shadow-xl">
      <h1 className="text-3xl font-semibold mb-2">GrantFlow Modern</h1>
      <p className="text-slate-300 mb-6">{invite?'Accept your invitation or recover your account':setup?'Set up your administrator account':'Sign in to your workspace'}</p>
      {error&&<p role="alert" className="text-red-300 mb-4">{error}</p>}
      {notice&&<p role="status" className="text-green-300 mb-4">{notice}</p>}
      {mode==='standalone'&&<form onSubmit={submit} className="space-y-4">
        {setup&&!invite&&<>
          <label className="block">Setup code<input name="bootstrap_token" type="password" required minLength={32} autoComplete="off" className="block w-full bg-slate-800 rounded p-3 mt-1"/></label>
          <label className="block">Email<input name="email" type="email" required autoComplete="email" className="block w-full bg-slate-800 rounded p-3 mt-1"/></label>
          <label className="block">Organization<input name="organization" required maxLength={255} className="block w-full bg-slate-800 rounded p-3 mt-1"/></label>
        </>}
        <label className="block">Username<input name="username" required autoComplete="username" maxLength={100} className="block w-full bg-slate-800 rounded p-3 mt-1"/></label>
        <label className="block">Password<input name="password" type="password" required minLength={invite||setup?14:1} maxLength={128} autoComplete={invite||setup?'new-password':'current-password'} className="block w-full bg-slate-800 rounded p-3 mt-1"/></label>
        {(invite||setup)&&<p className="text-sm text-slate-400">Use a password or passphrase of at least 14 characters.</p>}
        <button disabled={busy} className="w-full rounded bg-cyan-600 p-3 font-semibold disabled:opacity-50">{busy?'Please wait…':invite?'Save password':setup?'Create administrator':'Sign in'}</button>
        {!setup&&!invite&&<p className="text-sm text-slate-400">Need an account or password recovery? Ask your administrator for a private invitation or recovery link.</p>}
      </form>}
      {mode==='loading'&&<p role="status">Checking sign-in…</p>}
    </section>
  </main>;
}
