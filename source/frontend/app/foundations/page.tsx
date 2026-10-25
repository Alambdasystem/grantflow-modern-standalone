"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2, Plus, Search, ExternalLink, Mail, Phone, Globe,
  ChevronRight, DollarSign, Calendar, X, Edit2, Trash2, UserPlus,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface FoundationContact {
  id: number;
  name: string;
  title?: string;
  email?: string;
  phone?: string;
  is_primary: boolean;
  relationship_notes?: string;
}

interface Foundation {
  id: number;
  name: string;
  description?: string;
  website?: string;
  grant_type: string;
  focus_areas: string[];
  geographic_focus?: string;
  portal_type: string;
  portal_url?: string;
  typical_amount_min?: number;
  typical_amount_max?: number;
  accepts_unsolicited: boolean;
  requires_loi: boolean;
  loi_deadline_days_before: number;
  cycle: string;
  eligibility_notes?: string;
  notes?: string;
  is_active: boolean;
  created_at?: string;
  contacts: FoundationContact[];
}

const CYCLES = ["rolling", "annual", "biannual", "invite-only"];
const GRANT_TYPES = ["private", "community", "corporate", "family", "public"];
const PORTAL_TYPES = ["website", "submittable", "fluxx", "zoomgrants", "email", "other"];

const CYCLE_COLORS: Record<string, string> = {
  rolling: "bg-green-500/20 text-green-300 border-green-500/30",
  annual: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  biannual: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  "invite-only": "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

function fmt(n?: number) {
  if (!n) return "—";
  return "$" + n.toLocaleString();
}

export default function FoundationsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [filterCycle, setFilterCycle] = useState("");
  const [filterType, setFilterType] = useState("");
  const [selected, setSelected] = useState<Foundation | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showContactForm, setShowContactForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const [form, setForm] = useState({
    name: "", description: "", website: "", grant_type: "private",
    focus_areas_raw: "", geographic_focus: "", portal_type: "website",
    portal_url: "", typical_amount_min: "", typical_amount_max: "",
    accepts_unsolicited: true, requires_loi: false,
    loi_deadline_days_before: 60, cycle: "rolling",
    eligibility_notes: "", notes: "",
  });

  const [contactForm, setContactForm] = useState({
    name: "", title: "", email: "", phone: "", is_primary: false,
    relationship_notes: "",
  });

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (filterCycle) params.set("cycle", filterCycle);
  if (filterType) params.set("grant_type", filterType);

  const { data, isLoading } = useQuery({
    queryKey: ["foundations", q, filterCycle, filterType],
    queryFn: () => apiFetch(`/api/foundations?${params}`),
  });

  const createMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch("/api/foundations", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foundations"] });
      setShowForm(false);
      resetForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      apiFetch(`/api/foundations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foundations"] });
      setShowForm(false);
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/foundations/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foundations"] });
      setSelected(null);
    },
  });

  const addContactMutation = useMutation({
    mutationFn: ({ fid, body }: { fid: number; body: Record<string, unknown> }) =>
      apiFetch(`/api/foundations/${fid}/contacts`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foundations"] });
      setShowContactForm(false);
      setContactForm({ name: "", title: "", email: "", phone: "", is_primary: false, relationship_notes: "" });
    },
  });

  const deleteContactMutation = useMutation({
    mutationFn: ({ fid, cid }: { fid: number; cid: number }) =>
      apiFetch(`/api/foundations/${fid}/contacts/${cid}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["foundations"] }),
  });

  function resetForm() {
    setForm({
      name: "", description: "", website: "", grant_type: "private",
      focus_areas_raw: "", geographic_focus: "", portal_type: "website",
      portal_url: "", typical_amount_min: "", typical_amount_max: "",
      accepts_unsolicited: true, requires_loi: false,
      loi_deadline_days_before: 60, cycle: "rolling",
      eligibility_notes: "", notes: "",
    });
    setEditingId(null);
  }

  function openEdit(f: Foundation) {
    setForm({
      name: f.name,
      description: f.description || "",
      website: f.website || "",
      grant_type: f.grant_type,
      focus_areas_raw: (f.focus_areas || []).join(", "),
      geographic_focus: f.geographic_focus || "",
      portal_type: f.portal_type,
      portal_url: f.portal_url || "",
      typical_amount_min: f.typical_amount_min ? String(f.typical_amount_min) : "",
      typical_amount_max: f.typical_amount_max ? String(f.typical_amount_max) : "",
      accepts_unsolicited: f.accepts_unsolicited,
      requires_loi: f.requires_loi,
      loi_deadline_days_before: f.loi_deadline_days_before,
      cycle: f.cycle,
      eligibility_notes: f.eligibility_notes || "",
      notes: f.notes || "",
    });
    setEditingId(f.id);
    setShowForm(true);
  }

  function submitForm() {
    const body: Record<string, unknown> = {
      name: form.name,
      description: form.description || null,
      website: form.website || null,
      grant_type: form.grant_type,
      focus_areas: form.focus_areas_raw.split(",").map(s => s.trim()).filter(Boolean),
      geographic_focus: form.geographic_focus || null,
      portal_type: form.portal_type,
      portal_url: form.portal_url || null,
      typical_amount_min: form.typical_amount_min ? parseFloat(form.typical_amount_min) : null,
      typical_amount_max: form.typical_amount_max ? parseFloat(form.typical_amount_max) : null,
      accepts_unsolicited: form.accepts_unsolicited,
      requires_loi: form.requires_loi,
      loi_deadline_days_before: form.loi_deadline_days_before,
      cycle: form.cycle,
      eligibility_notes: form.eligibility_notes || null,
      notes: form.notes || null,
    };
    if (editingId) {
      updateMutation.mutate({ id: editingId, body });
    } else {
      createMutation.mutate(body);
    }
  }

  const foundations: Foundation[] = data?.items || [];

  return (
    <div className="flex h-full min-h-screen bg-[#06121b] text-zinc-100">
      {/* List panel */}
      <div className="flex flex-col w-full max-w-sm border-r border-cyan-900/40 shrink-0">
        <div className="px-4 pt-5 pb-3 border-b border-cyan-900/40">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-cyan-400" /> Foundations
              </h1>
              <p className="text-xs text-zinc-500 mt-0.5">Private & community foundation grants</p>
            </div>
            <button
              onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 text-cyan-300 rounded-lg transition"
            >
              <Plus className="w-3.5 h-3.5" /> Add
            </button>
          </div>

          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-zinc-500" />
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search foundations…"
              className="w-full pl-8 pr-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-cyan-500/50"
            />
          </div>

          <div className="flex gap-2">
            <select
              value={filterCycle}
              onChange={e => setFilterCycle(e.target.value)}
              className="flex-1 text-xs bg-[#0d2433] border border-cyan-900/40 rounded-lg px-2 py-1.5 text-zinc-300 focus:outline-none"
            >
              <option value="">All cycles</option>
              {CYCLES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className="flex-1 text-xs bg-[#0d2433] border border-cyan-900/40 rounded-lg px-2 py-1.5 text-zinc-300 focus:outline-none"
            >
              <option value="">All types</option>
              {GRANT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-cyan-900/20">
          {isLoading ? (
            <div className="py-12 text-center text-zinc-500 text-sm">Loading…</div>
          ) : foundations.length === 0 ? (
            <div className="py-12 text-center text-zinc-500 text-sm">
              No foundations yet.<br />
              <span className="text-xs text-zinc-600">Add private, community, or corporate foundations.</span>
            </div>
          ) : foundations.map(f => (
            <button
              key={f.id}
              onClick={() => setSelected(f)}
              className={`w-full text-left px-4 py-3 hover:bg-[#0d2433] transition group ${selected?.id === f.id ? "bg-[#0d2433] border-l-2 border-cyan-400" : ""}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-200 truncate">{f.name}</p>
                  <p className="text-xs text-zinc-500 mt-0.5 truncate">{f.geographic_focus || f.website || f.grant_type}</p>
                </div>
                <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded border font-medium ${CYCLE_COLORS[f.cycle] || "bg-zinc-700/40 text-zinc-400 border-zinc-600"}`}>
                  {f.cycle}
                </span>
              </div>
              {(f.typical_amount_min || f.typical_amount_max) && (
                <p className="text-xs text-cyan-400/70 mt-1">
                  {fmt(f.typical_amount_min)} – {fmt(f.typical_amount_max)}
                </p>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto">
        {!selected && !showForm ? (
          <div className="flex flex-col items-center justify-center h-full text-zinc-600">
            <Building2 className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">Select a foundation to view details</p>
          </div>
        ) : showForm ? (
          <div className="max-w-2xl mx-auto p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-zinc-100">
                {editingId ? "Edit Foundation" : "Add Foundation"}
              </h2>
              <button onClick={() => { setShowForm(false); resetForm(); }} className="text-zinc-500 hover:text-zinc-300">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Name *</label>
                  <input value={form.name} onChange={e => setForm(s => ({ ...s, name: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Type</label>
                  <select value={form.grant_type} onChange={e => setForm(s => ({ ...s, grant_type: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none">
                    {GRANT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Grant Cycle</label>
                  <select value={form.cycle} onChange={e => setForm(s => ({ ...s, cycle: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none">
                    {CYCLES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Website</label>
                  <input value={form.website} onChange={e => setForm(s => ({ ...s, website: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Portal Type</label>
                  <select value={form.portal_type} onChange={e => setForm(s => ({ ...s, portal_type: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none">
                    {PORTAL_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Application Portal URL</label>
                  <input value={form.portal_url} onChange={e => setForm(s => ({ ...s, portal_url: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Min Grant ($)</label>
                  <input type="number" value={form.typical_amount_min} onChange={e => setForm(s => ({ ...s, typical_amount_min: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Max Grant ($)</label>
                  <input type="number" value={form.typical_amount_max} onChange={e => setForm(s => ({ ...s, typical_amount_max: e.target.value }))}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Focus Areas (comma-separated)</label>
                  <input value={form.focus_areas_raw} onChange={e => setForm(s => ({ ...s, focus_areas_raw: e.target.value }))}
                    placeholder="education, health, workforce development"
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Geographic Focus</label>
                  <input value={form.geographic_focus} onChange={e => setForm(s => ({ ...s, geographic_focus: e.target.value }))}
                    placeholder="e.g. St. Louis, MO; Missouri; National"
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Description</label>
                  <textarea value={form.description} onChange={e => setForm(s => ({ ...s, description: e.target.value }))}
                    rows={3}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50 resize-none" />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Eligibility Notes</label>
                  <textarea value={form.eligibility_notes} onChange={e => setForm(s => ({ ...s, eligibility_notes: e.target.value }))}
                    rows={2}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50 resize-none" />
                </div>
                <div className="col-span-2 flex gap-6">
                  <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                    <input type="checkbox" checked={form.accepts_unsolicited}
                      onChange={e => setForm(s => ({ ...s, accepts_unsolicited: e.target.checked }))}
                      className="rounded" />
                    Accepts unsolicited proposals
                  </label>
                  <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                    <input type="checkbox" checked={form.requires_loi}
                      onChange={e => setForm(s => ({ ...s, requires_loi: e.target.checked }))}
                      className="rounded" />
                    Requires LOI
                  </label>
                </div>
                {form.requires_loi && (
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">LOI Due (days before deadline)</label>
                    <input type="number" value={form.loi_deadline_days_before}
                      onChange={e => setForm(s => ({ ...s, loi_deadline_days_before: parseInt(e.target.value) || 60 }))}
                      className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50" />
                  </div>
                )}
                <div className="col-span-2">
                  <label className="block text-xs text-zinc-400 mb-1">Internal Notes</label>
                  <textarea value={form.notes} onChange={e => setForm(s => ({ ...s, notes: e.target.value }))}
                    rows={2}
                    className="w-full px-3 py-2 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500/50 resize-none" />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => { setShowForm(false); resetForm(); }}
                  className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition">
                  Cancel
                </button>
                <button onClick={submitForm} disabled={!form.name}
                  className="px-5 py-2 text-sm bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 text-cyan-300 rounded-lg transition disabled:opacity-40">
                  {editingId ? "Save Changes" : "Add Foundation"}
                </button>
              </div>
            </div>
          </div>
        ) : selected ? (
          <div className="max-w-2xl mx-auto p-6">
            {/* Header */}
            <div className="flex items-start justify-between mb-5">
              <div>
                <h2 className="text-xl font-semibold text-zinc-100">{selected.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-2 py-0.5 rounded border font-medium ${CYCLE_COLORS[selected.cycle] || "bg-zinc-700 text-zinc-400 border-zinc-600"}`}>
                    {selected.cycle}
                  </span>
                  <span className="text-xs text-zinc-500">{selected.grant_type} foundation</span>
                  {selected.requires_loi && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      LOI required
                    </span>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => openEdit(selected)}
                  className="p-2 rounded-lg hover:bg-[#0d2433] text-zinc-400 hover:text-zinc-200 transition">
                  <Edit2 className="w-4 h-4" />
                </button>
                <button onClick={() => { if (confirm("Delete this foundation?")) deleteMutation.mutate(selected.id); }}
                  className="p-2 rounded-lg hover:bg-red-900/20 text-zinc-400 hover:text-red-400 transition">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Info grid */}
            <div className="grid grid-cols-2 gap-3 mb-5">
              {selected.typical_amount_min || selected.typical_amount_max ? (
                <div className="bg-[#0d2433] rounded-xl p-3 border border-cyan-900/30">
                  <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
                    <DollarSign className="w-3.5 h-3.5" /> Typical Grant
                  </div>
                  <p className="text-sm font-medium text-zinc-200">
                    {fmt(selected.typical_amount_min)} – {fmt(selected.typical_amount_max)}
                  </p>
                </div>
              ) : null}

              {selected.geographic_focus && (
                <div className="bg-[#0d2433] rounded-xl p-3 border border-cyan-900/30">
                  <div className="text-xs text-zinc-500 mb-1">Geographic Focus</div>
                  <p className="text-sm text-zinc-200">{selected.geographic_focus}</p>
                </div>
              )}

              {selected.portal_type !== "website" && (
                <div className="bg-[#0d2433] rounded-xl p-3 border border-cyan-900/30">
                  <div className="text-xs text-zinc-500 mb-1">Application Portal</div>
                  <p className="text-sm text-zinc-200 capitalize">{selected.portal_type}</p>
                </div>
              )}

              <div className="bg-[#0d2433] rounded-xl p-3 border border-cyan-900/30">
                <div className="text-xs text-zinc-500 mb-1">Unsolicited</div>
                <p className="text-sm text-zinc-200">{selected.accepts_unsolicited ? "Yes" : "No"}</p>
              </div>
            </div>

            {/* Focus areas */}
            {selected.focus_areas?.length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-zinc-500 mb-2">Focus Areas</p>
                <div className="flex flex-wrap gap-1.5">
                  {selected.focus_areas.map(a => (
                    <span key={a} className="text-xs px-2 py-0.5 rounded-full bg-cyan-900/30 border border-cyan-900/50 text-cyan-300">
                      {a}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Links */}
            <div className="flex gap-3 mb-5">
              {selected.website && (
                <a href={selected.website} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 transition">
                  <Globe className="w-3.5 h-3.5" /> Website <ExternalLink className="w-3 h-3" />
                </a>
              )}
              {selected.portal_url && (
                <a href={selected.portal_url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 transition">
                  <ExternalLink className="w-3.5 h-3.5" /> Apply Portal
                </a>
              )}
            </div>

            {selected.description && (
              <div className="mb-5">
                <p className="text-xs text-zinc-500 mb-1.5">About</p>
                <p className="text-sm text-zinc-300 leading-relaxed">{selected.description}</p>
              </div>
            )}

            {selected.eligibility_notes && (
              <div className="mb-5 p-3 bg-amber-900/10 border border-amber-500/20 rounded-xl">
                <p className="text-xs text-amber-400 mb-1">Eligibility</p>
                <p className="text-sm text-zinc-300">{selected.eligibility_notes}</p>
              </div>
            )}

            {selected.requires_loi && (
              <div className="mb-5 p-3 bg-purple-900/10 border border-purple-500/20 rounded-xl">
                <p className="text-xs text-purple-400 mb-1 flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5" /> LOI Required
                </p>
                <p className="text-sm text-zinc-300">
                  Letter of Intent must be submitted <strong>{selected.loi_deadline_days_before} days</strong> before the grant deadline.
                </p>
              </div>
            )}

            {/* Contacts */}
            <div className="border-t border-cyan-900/30 pt-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-medium text-zinc-300">Program Contacts</p>
                <button onClick={() => setShowContactForm(true)}
                  className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition">
                  <UserPlus className="w-3.5 h-3.5" /> Add Contact
                </button>
              </div>

              {showContactForm && (
                <div className="mb-4 p-4 bg-[#0d2433] border border-cyan-900/40 rounded-xl space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">Name *</label>
                      <input value={contactForm.name} onChange={e => setContactForm(s => ({ ...s, name: e.target.value }))}
                        className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">Title</label>
                      <input value={contactForm.title} onChange={e => setContactForm(s => ({ ...s, title: e.target.value }))}
                        className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">Email</label>
                      <input value={contactForm.email} onChange={e => setContactForm(s => ({ ...s, email: e.target.value }))}
                        className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">Phone</label>
                      <input value={contactForm.phone} onChange={e => setContactForm(s => ({ ...s, phone: e.target.value }))}
                        className="w-full px-2 py-1.5 text-sm bg-[#06121b] border border-cyan-900/40 rounded text-zinc-200 focus:outline-none" />
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                    <input type="checkbox" checked={contactForm.is_primary}
                      onChange={e => setContactForm(s => ({ ...s, is_primary: e.target.checked }))} />
                    Primary contact
                  </label>
                  <div className="flex justify-end gap-2">
                    <button onClick={() => setShowContactForm(false)} className="text-xs text-zinc-500 hover:text-zinc-300">Cancel</button>
                    <button
                      onClick={() => addContactMutation.mutate({ fid: selected.id, body: contactForm })}
                      disabled={!contactForm.name}
                      className="text-xs px-3 py-1 bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 rounded hover:bg-cyan-500/30 disabled:opacity-40">
                      Save Contact
                    </button>
                  </div>
                </div>
              )}

              {selected.contacts?.length === 0 ? (
                <p className="text-sm text-zinc-600 py-2">No contacts yet.</p>
              ) : (
                <div className="space-y-2">
                  {selected.contacts.map(c => (
                    <div key={c.id} className="flex items-start justify-between p-3 bg-[#0d2433] rounded-xl border border-cyan-900/20">
                      <div>
                        <p className="text-sm font-medium text-zinc-200">
                          {c.name}
                          {c.is_primary && <span className="ml-1.5 text-xs text-cyan-400">(primary)</span>}
                        </p>
                        {c.title && <p className="text-xs text-zinc-500">{c.title}</p>}
                        <div className="flex gap-3 mt-1">
                          {c.email && (
                            <a href={`mailto:${c.email}`} className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300">
                              <Mail className="w-3 h-3" /> {c.email}
                            </a>
                          )}
                          {c.phone && (
                            <span className="flex items-center gap-1 text-xs text-zinc-400">
                              <Phone className="w-3 h-3" /> {c.phone}
                            </span>
                          )}
                        </div>
                      </div>
                      <button onClick={() => deleteContactMutation.mutate({ fid: selected.id, cid: c.id })}
                        className="text-zinc-600 hover:text-red-400 transition">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {selected.notes && (
              <div className="mt-5 p-3 bg-[#0d2433] rounded-xl border border-cyan-900/20">
                <p className="text-xs text-zinc-500 mb-1">Notes</p>
                <p className="text-sm text-zinc-300">{selected.notes}</p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
