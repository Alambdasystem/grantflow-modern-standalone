"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Heart, Plus, Search, DollarSign, Users, TrendingUp,
  ExternalLink, Copy, Check, X, Edit2, Mail, Phone,
  Calendar, Target, BarChart2,
} from "lucide-react";
import { api, apiFetch } from "@/lib/api";

interface Donor {
  id: number;
  donor_type: string;
  display_name: string;
  first_name?: string;
  last_name?: string;
  organization_name?: string;
  email?: string;
  phone?: string;
  city?: string;
  state?: string;
  is_anonymous: boolean;
  total_donated: number;
  tags: string[];
  notes?: string;
  created_at?: string;
  donations?: DonationRecord[];
}

interface DonationRecord {
  id: number;
  amount: number;
  currency: string;
  donation_type: string;
  is_restricted: boolean;
  restriction_purpose?: string;
  received_at?: string;
  acknowledgment_sent: boolean;
  notes?: string;
}

interface Campaign {
  id: number;
  name: string;
  description?: string;
  slug: string;
  goal_amount?: number;
  raised_amount: number;
  progress_pct: number;
  campaign_type: string;
  start_date?: string;
  end_date?: string;
  is_active: boolean;
  is_public: boolean;
  donation_count: number;
  thank_you_message?: string;
  created_at?: string;
}

type Tab = "donors" | "campaigns";

const TYPE_COLORS: Record<string, string> = {
  individual: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  business: "bg-green-500/20 text-green-300 border-green-500/30",
  foundation: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  government: "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

const CAMPAIGN_TYPE_COLORS: Record<string, string> = {
  general: "bg-zinc-700/40 text-zinc-400 border-zinc-600",
  capital: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  program: "bg-green-500/20 text-green-300 border-green-500/30",
  event: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  emergency: "bg-red-500/20 text-red-300 border-red-500/30",
};

function fmt(n: number) {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtDate(s?: string) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function DonorsPage() {
  const qc = useQueryClient();
  const me=useQuery<{role:string}>({queryKey:["me"],queryFn:()=>api.get("/api/auth/me").then(r=>r.data)});
  const [tab, setTab] = useState<Tab>("donors");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Donor | Campaign | null>(null);
  const [showDonorForm, setShowDonorForm] = useState(false);
  const [showCampaignForm, setShowCampaignForm] = useState(false);
  const [showDonationForm, setShowDonationForm] = useState(false);
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);

  const [donorForm, setDonorForm] = useState({
    donor_type: "individual", first_name: "", last_name: "",
    organization_name: "", email: "", phone: "", city: "", state: "",
    zip_code: "", is_anonymous: false, notes: "",
  });

  const [campaignForm, setCampaignForm] = useState({
    name: "", description: "", slug: "", goal_amount: "",
    campaign_type: "general", is_active: true, is_public: true,
    thank_you_message: "",
  });

  const [donationForm, setDonationForm] = useState({
    amount: "", donation_type: "cash", is_restricted: false,
    restriction_purpose: "", received_at: "", notes: "",
    donor_first_name: "", donor_last_name: "", donor_email: "",
    donor_type: "individual", campaign_id: "",
    is_anonymous: false,
  });

  // Donors data
  const donorsQuery = useQuery({
    queryKey: ["donors", q],
    queryFn: () => apiFetch(`/api/donors?q=${encodeURIComponent(q)}&limit=100`),
    enabled: me.data?.role === "admin" && tab === "donors",
  });

  // Campaigns data
  const campaignsQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiFetch("/api/donors/campaigns/list?limit=100"),
    enabled: me.data?.role === "admin" && tab === "campaigns",
  });

  const createDonorMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch("/api/donors", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["donors"] }); setShowDonorForm(false); },
  });

  const createCampaignMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch("/api/donors/campaigns", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["campaigns"] }); setShowCampaignForm(false); },
  });

  const recordDonationMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch("/api/donors/donations", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["donors"] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["donor-detail"] });
      setShowDonationForm(false);
    },
  });

  const ackMutation = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/donors/donations/${id}/acknowledge`, { method: "PATCH" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["donor-detail"] }),
  });

  function copyShareLink(slug: string) {
    const url = `${window.location.origin}/give/${slug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedSlug(slug);
      setTimeout(() => setCopiedSlug(null), 2000);
    });
  }

  const donors: Donor[] = donorsQuery.data?.items || [];
  const campaigns: Campaign[] = campaignsQuery.data?.items || [];
  const totalRaised: number = donorsQuery.data?.total_raised || 0;

  if(me.isLoading) return <p className="p-6">Checking account permissions...</p>;
  if(me.data?.role!=="admin") return <p role="alert" className="p-6">Donor and campaign management requires administrator access. Your current role cannot view these private records.</p>;
  if(donorsQuery.isError || campaignsQuery.isError) return <p role="alert" className="p-6">Donor or campaign records could not be loaded. This is an error, not an empty directory. Please retry.</p>;
  return (
    <div className="flex h-full min-h-screen bg-[#06121b] text-zinc-100">
      {/* Left panel */}
      <div className="flex flex-col w-full max-w-sm border-r border-cyan-900/40 shrink-0">
        <div className="px-4 pt-5 pb-3 border-b border-cyan-900/40">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
                <Heart className="w-5 h-5 text-rose-400" /> Donors
              </h1>
              <p className="text-xs text-zinc-500 mt-0.5">Donors, campaigns & donations</p>
            </div>
            <button
              onClick={() => tab === "donors" ? setShowDonorForm(true) : setShowCampaignForm(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/30 text-rose-300 rounded-lg transition"
            >
              <Plus className="w-3.5 h-3.5" /> Add
            </button>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-3 bg-[#0d2433] rounded-lg p-0.5">
            {(["donors", "campaigns"] as Tab[]).map(t => (
              <button key={t}
                onClick={() => { setTab(t); setSelected(null); }}
                className={`flex-1 py-1.5 text-xs rounded-md font-medium transition capitalize ${tab === t ? "bg-rose-500/20 text-rose-300 border border-rose-500/30" : "text-zinc-500 hover:text-zinc-300"}`}>
                {t}
              </button>
            ))}
          </div>

          {tab === "donors" && (
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-zinc-500" />
              <input
                value={q} onChange={e => setQ(e.target.value)}
                placeholder="Search donors…"
                className="w-full pl-8 pr-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-rose-500/50"
              />
            </div>
          )}

          {tab === "donors" && donorsQuery.data && (
            <div className="mt-2 flex gap-3">
              <div className="flex-1 bg-[#0d2433] rounded-lg p-2 border border-cyan-900/20">
                <p className="text-[10px] text-zinc-500">Total Donors</p>
                <p className="text-sm font-semibold text-zinc-200">{donorsQuery.data.total}</p>
              </div>
              <div className="flex-1 bg-[#0d2433] rounded-lg p-2 border border-cyan-900/20">
                <p className="text-[10px] text-zinc-500">Total Raised</p>
                <p className="text-sm font-semibold text-rose-300">{fmt(totalRaised)}</p>
              </div>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-cyan-900/20">
          {tab === "donors" && (
            donorsQuery.isLoading ? (
              <div className="py-12 text-center text-zinc-500 text-sm">Loading…</div>
            ) : donors.length === 0 ? (
              <div className="py-12 text-center text-zinc-500 text-sm">
                No donors yet.<br />
                <span className="text-xs text-zinc-600">Add donors or share a campaign link.</span>
              </div>
            ) : donors.map(d => (
              <button key={d.id} onClick={() => setSelected(d)}
                className={`w-full text-left px-4 py-3 hover:bg-[#0d2433] transition ${selected && "id" in selected && selected.id === d.id ? "bg-[#0d2433] border-l-2 border-rose-400" : ""}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200 truncate">{d.display_name}</p>
                    <p className="text-xs text-zinc-500 truncate">{d.email || d.city || "—"}</p>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <p className="text-xs font-medium text-rose-300">{fmt(d.total_donated)}</p>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${TYPE_COLORS[d.donor_type] || "bg-zinc-700 text-zinc-400 border-zinc-600"}`}>
                      {d.donor_type}
                    </span>
                  </div>
                </div>
              </button>
            ))
          )}

          {tab === "campaigns" && (
            campaignsQuery.isLoading ? (
              <div className="py-12 text-center text-zinc-500 text-sm">Loading…</div>
            ) : campaigns.length === 0 ? (
              <div className="py-12 text-center text-zinc-500 text-sm">
                No campaigns yet.<br />
                <span className="text-xs text-zinc-600">Create a campaign and share the link.</span>
              </div>
            ) : campaigns.map(c => (
              <button key={c.id} onClick={() => setSelected(c)}
                className={`w-full text-left px-4 py-3 hover:bg-[#0d2433] transition ${selected && "slug" in selected && selected.id === c.id ? "bg-[#0d2433] border-l-2 border-rose-400" : ""}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200 truncate">{c.name}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${CAMPAIGN_TYPE_COLORS[c.campaign_type] || ""}`}>
                        {c.campaign_type}
                      </span>
                      {!c.is_active && <span className="text-[10px] text-zinc-600">inactive</span>}
                    </div>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <p className="text-xs font-medium text-rose-300">{fmt(c.raised_amount)}</p>
                    {c.goal_amount && <p className="text-[10px] text-zinc-500">{c.progress_pct}% of goal</p>}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Detail / form panel */}
      <div className="flex-1 overflow-y-auto">
        {showDonorForm && (
          <div className="max-w-2xl mx-auto p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-zinc-100">Add Donor</h2>
              <button onClick={() => setShowDonorForm(false)} className="text-zinc-500 hover:text-zinc-300"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Donor Type</label>
                <select value={donorForm.donor_type} onChange={e => setDonorForm(s => ({ ...s, donor_type: e.target.value }))}
                  className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none">
                  {["individual", "business", "foundation", "government", "other"].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              {donorForm.donor_type === "individual" ? (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">First Name</label>
                    <input value={donorForm.first_name} onChange={e => setDonorForm(s => ({ ...s, first_name: e.target.value }))}
                      className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Last Name</label>
                    <input value={donorForm.last_name} onChange={e => setDonorForm(s => ({ ...s, last_name: e.target.value }))}
                      className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                  </div>
                </div>
              ) : (
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Organization Name</label>
                  <input value={donorForm.organization_name} onChange={e => setDonorForm(s => ({ ...s, organization_name: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Email</label>
                  <input type="email" value={donorForm.email} onChange={e => setDonorForm(s => ({ ...s, email: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Phone</label>
                  <input value={donorForm.phone} onChange={e => setDonorForm(s => ({ ...s, phone: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">City</label>
                  <input value={donorForm.city} onChange={e => setDonorForm(s => ({ ...s, city: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">State</label>
                  <input value={donorForm.state} onChange={e => setDonorForm(s => ({ ...s, state: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={donorForm.is_anonymous}
                  onChange={e => setDonorForm(s => ({ ...s, is_anonymous: e.target.checked }))} />
                Anonymous donor
              </label>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Notes</label>
                <textarea value={donorForm.notes} onChange={e => setDonorForm(s => ({ ...s, notes: e.target.value }))}
                  rows={2} className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none resize-none" />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowDonorForm(false)} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
                <button
                  onClick={() => createDonorMutation.mutate(donorForm)}
                  className="px-5 py-2 text-sm bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/30 text-rose-300 rounded-lg transition">
                  Add Donor
                </button>
              </div>
            </div>
          </div>
        )}

        {showCampaignForm && (
          <div className="max-w-2xl mx-auto p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-zinc-100">Create Campaign</h2>
              <button onClick={() => setShowCampaignForm(false)} className="text-zinc-500 hover:text-zinc-300"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Campaign Name *</label>
                <input value={campaignForm.name} onChange={e => setCampaignForm(s => ({ ...s, name: e.target.value }))}
                  className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-rose-500/50" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Type</label>
                  <select value={campaignForm.campaign_type} onChange={e => setCampaignForm(s => ({ ...s, campaign_type: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none">
                    {["general", "capital", "program", "event", "emergency"].map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Goal Amount ($)</label>
                  <input type="number" value={campaignForm.goal_amount} onChange={e => setCampaignForm(s => ({ ...s, goal_amount: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
                </div>
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  URL Slug <span className="text-zinc-600">(auto-generated from name if blank)</span>
                </label>
                <input value={campaignForm.slug} onChange={e => setCampaignForm(s => ({ ...s, slug: e.target.value }))}
                  placeholder="my-campaign-name"
                  className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Description</label>
                <textarea value={campaignForm.description} onChange={e => setCampaignForm(s => ({ ...s, description: e.target.value }))}
                  rows={3} className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none resize-none" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Thank-You Message</label>
                <textarea value={campaignForm.thank_you_message} onChange={e => setCampaignForm(s => ({ ...s, thank_you_message: e.target.value }))}
                  rows={2} placeholder="Thank you for your generous support!"
                  className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none resize-none" />
              </div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                  <input type="checkbox" checked={campaignForm.is_active}
                    onChange={e => setCampaignForm(s => ({ ...s, is_active: e.target.checked }))} />
                  Active
                </label>
                <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                  <input type="checkbox" checked={campaignForm.is_public}
                    onChange={e => setCampaignForm(s => ({ ...s, is_public: e.target.checked }))} />
                  Public (shareable link)
                </label>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowCampaignForm(false)} className="px-4 py-2 text-sm text-zinc-400">Cancel</button>
                <button
                  onClick={() => createCampaignMutation.mutate({
                    ...campaignForm,
                    goal_amount: campaignForm.goal_amount ? parseFloat(campaignForm.goal_amount) : null,
                  })}
                  disabled={!campaignForm.name}
                  className="px-5 py-2 text-sm bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/30 text-rose-300 rounded-lg transition disabled:opacity-40">
                  Create Campaign
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Donor detail */}
        {!showDonorForm && !showCampaignForm && selected && "display_name" in selected && (
          <div className="max-w-2xl mx-auto p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-xl font-semibold text-zinc-100">{selected.display_name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-2 py-0.5 rounded border ${TYPE_COLORS[selected.donor_type] || ""}`}>
                    {selected.donor_type}
                  </span>
                  {selected.is_anonymous && <span className="text-xs text-zinc-500">Anonymous</span>}
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-rose-300">{fmt(selected.total_donated)}</p>
                <p className="text-xs text-zinc-500">total donated</p>
              </div>
            </div>

            <div className="flex gap-3 mb-5">
              {selected.email && (
                <a href={`mailto:${selected.email}`} className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300">
                  <Mail className="w-3.5 h-3.5" /> {selected.email}
                </a>
              )}
              {selected.phone && (
                <span className="flex items-center gap-1 text-xs text-zinc-400">
                  <Phone className="w-3.5 h-3.5" /> {selected.phone}
                </span>
              )}
            </div>

            {selected.notes && (
              <div className="mb-5 p-3 bg-[#0d2433] rounded-xl border border-cyan-900/20">
                <p className="text-xs text-zinc-500 mb-1">Notes</p>
                <p className="text-sm text-zinc-300">{selected.notes}</p>
              </div>
            )}

            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-medium text-zinc-300">Donation History</p>
              <button
                onClick={() => setShowDonationForm(true)}
                className="flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300 transition">
                <Plus className="w-3.5 h-3.5" /> Record Donation
              </button>
            </div>

            {showDonationForm && (
              <div className="mb-4 p-4 bg-[#0d2433] border border-rose-900/40 rounded-xl space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Amount *</label>
                    <input type="number" value={donationForm.amount}
                      onChange={e => setDonationForm(s => ({ ...s, amount: e.target.value }))}
                      className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Type</label>
                    <select value={donationForm.donation_type}
                      onChange={e => setDonationForm(s => ({ ...s, donation_type: e.target.value }))}
                      className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none">
                      {["cash", "check", "in-kind", "stock", "pledge", "grant-award", "wire"].map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-zinc-500 mb-1">Received Date</label>
                    <input type="date" value={donationForm.received_at}
                      onChange={e => setDonationForm(s => ({ ...s, received_at: e.target.value }))}
                      className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-zinc-500 mb-1">Notes</label>
                    <input value={donationForm.notes}
                      onChange={e => setDonationForm(s => ({ ...s, notes: e.target.value }))}
                      className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                  </div>
                </div>
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={donationForm.is_restricted}
                    onChange={e => setDonationForm(s => ({ ...s, is_restricted: e.target.checked }))} />
                  Restricted gift
                </label>
                {donationForm.is_restricted && (
                  <input value={donationForm.restriction_purpose}
                    onChange={e => setDonationForm(s => ({ ...s, restriction_purpose: e.target.value }))}
                    placeholder="Restriction purpose…"
                    className="w-full px-2 py-1.5 text-xs bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                )}
                <div className="flex justify-end gap-2">
                  <button onClick={() => setShowDonationForm(false)} className="text-xs text-zinc-500">Cancel</button>
                  <button
                    onClick={() => recordDonationMutation.mutate({
                      donor_id: selected.id,
                      amount: parseFloat(donationForm.amount),
                      donation_type: donationForm.donation_type,
                      is_restricted: donationForm.is_restricted,
                      restriction_purpose: donationForm.restriction_purpose || null,
                      received_at: donationForm.received_at ? new Date(donationForm.received_at).toISOString() : null,
                      notes: donationForm.notes || null,
                    })}
                    disabled={!donationForm.amount}
                    className="text-xs px-3 py-1.5 bg-rose-500/20 border border-rose-500/30 text-rose-300 rounded hover:bg-rose-500/30 disabled:opacity-40">
                    Record
                  </button>
                </div>
              </div>
            )}

            {(!selected.donations || selected.donations.length === 0) ? (
              <p className="text-sm text-zinc-600 py-3">No donations recorded yet.</p>
            ) : (
              <div className="space-y-2">
                {selected.donations!.map(d => (
                  <div key={d.id} className="flex items-center justify-between p-3 bg-[#0d2433] rounded-xl border border-cyan-900/20">
                    <div>
                      <p className="text-sm font-medium text-zinc-200">{fmt(d.amount)}</p>
                      <p className="text-xs text-zinc-500">{d.donation_type} • {fmtDate(d.received_at)}</p>
                      {d.is_restricted && (
                        <p className="text-xs text-amber-400 mt-0.5">Restricted: {d.restriction_purpose}</p>
                      )}
                    </div>
                    {!d.acknowledgment_sent && (
                      <button onClick={() => ackMutation.mutate(d.id)}
                        className="text-xs text-zinc-500 hover:text-green-400 border border-zinc-700 hover:border-green-400/40 rounded px-2 py-1 transition">
                        Acknowledge
                      </button>
                    )}
                    {d.acknowledgment_sent && (
                      <span className="text-xs text-green-400 flex items-center gap-1">
                        <Check className="w-3 h-3" /> Ack sent
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Campaign detail */}
        {!showDonorForm && !showCampaignForm && selected && "slug" in selected && (
          <div className="max-w-2xl mx-auto p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-xl font-semibold text-zinc-100">{selected.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-2 py-0.5 rounded border ${CAMPAIGN_TYPE_COLORS[selected.campaign_type] || ""}`}>
                    {selected.campaign_type}
                  </span>
                  <span className={`text-xs ${selected.is_active ? "text-green-400" : "text-zinc-500"}`}>
                    {selected.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            </div>

            {/* Progress */}
            <div className="mb-5 p-4 bg-[#0d2433] rounded-xl border border-cyan-900/30">
              <div className="flex justify-between items-end mb-2">
                <div>
                  <p className="text-2xl font-bold text-rose-300">{fmt(selected.raised_amount)}</p>
                  <p className="text-xs text-zinc-500">raised{selected.goal_amount ? ` of ${fmt(selected.goal_amount)} goal` : ""}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-zinc-300">{selected.donation_count} donations</p>
                  {selected.goal_amount && <p className="text-xs text-zinc-500">{selected.progress_pct}%</p>}
                </div>
              </div>
              {selected.goal_amount && (
                <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-rose-500 to-rose-400 rounded-full transition-all"
                    style={{ width: `${Math.min(100, selected.progress_pct)}%` }}
                  />
                </div>
              )}
            </div>

            {/* Share link */}
            {selected.is_public && (
              <div className="mb-5 p-3 bg-[#0d2433] rounded-xl border border-cyan-900/30">
                <p className="text-xs text-zinc-500 mb-1.5 flex items-center gap-1.5">
                  <ExternalLink className="w-3.5 h-3.5" /> Shareable Donation Link
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs text-cyan-400 truncate">
                    /give/{selected.slug}
                  </code>
                  <button
                    onClick={() => copyShareLink(selected.slug)}
                    className="shrink-0 flex items-center gap-1 text-xs px-2.5 py-1.5 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 rounded transition"
                  >
                    {copiedSlug === selected.slug ? <><Check className="w-3 h-3" /> Copied</> : <><Copy className="w-3 h-3" /> Copy</>}
                  </button>
                </div>
              </div>
            )}

            {selected.description && (
              <div className="mb-4">
                <p className="text-xs text-zinc-500 mb-1.5">Description</p>
                <p className="text-sm text-zinc-300">{selected.description}</p>
              </div>
            )}

            {selected.thank_you_message && (
              <div className="mb-4 p-3 bg-green-900/10 border border-green-500/20 rounded-xl">
                <p className="text-xs text-green-400 mb-1">Thank-You Message</p>
                <p className="text-sm text-zinc-300">{selected.thank_you_message}</p>
              </div>
            )}

            {(selected.start_date || selected.end_date) && (
              <div className="flex gap-4 mb-4 text-xs text-zinc-400">
                {selected.start_date && <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> Start: {fmtDate(selected.start_date)}</span>}
                {selected.end_date && <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> End: {fmtDate(selected.end_date)}</span>}
              </div>
            )}
          </div>
        )}

        {!showDonorForm && !showCampaignForm && !selected && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-600">
            <Heart className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">Select a donor or campaign to view details</p>
          </div>
        )}
      </div>
    </div>
  );
}
