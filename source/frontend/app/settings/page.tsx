"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Building2, Globe, FileText, Sparkles, Save, ShieldCheck, UserCheck } from "lucide-react";
import { toast } from "sonner";

type OrganizationPayload = {
  name: string;
  ein?: string;
  uei?: string;
  description?: string;
  mission?: string;
  capabilities?: string;
  website?: string;
  phone?: string;
  email?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  country?: string;
  congressional_district?: string;
  founded_year?: string;
  org_type?: string;
  aor_first_name?: string;
  aor_last_name?: string;
  aor_title?: string;
  aor_phone?: string;
  aor_email?: string;
  categories: string[];
  eligibility_tags: string[];
};

type Organization = OrganizationPayload & {
  id: number;
  profile_complete: boolean;
  created_at?: string;
};

function csvToList(value: string): string[] {
  return value
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [categoriesText, setCategoriesText] = useState("");
  const [eligibilityText, setEligibilityText] = useState("");

  const { data, isLoading } = useQuery<Organization>({
    queryKey: ["organization", "me"],
    queryFn: () => api.get("/api/organizations/me").then((r) => r.data),
  });

  const [form, setForm] = useState({
    name: "",
    ein: "",
    uei: "",
    description: "",
    mission: "",
    capabilities: "",
    website: "",
    phone: "",
    email: "",
    address: "",
    city: "",
    state: "",
    zip_code: "",
    country: "US",
    congressional_district: "",
    founded_year: "",
    org_type: "",
    aor_first_name: "",
    aor_last_name: "",
    aor_title: "",
    aor_phone: "",
    aor_email: "",
  });

  useEffect(() => {
    if (!data) {
      return;
    }
    setForm({
      name: data.name || "",
      ein: data.ein || "",
      uei: (data as OrganizationPayload & { uei?: string }).uei || "",
      description: data.description || "",
      mission: data.mission || "",
      capabilities: data.capabilities || "",
      website: data.website || "",
      phone: data.phone || "",
      email: data.email || "",
      address: data.address || "",
      city: (data as OrganizationPayload).city || "",
      state: (data as OrganizationPayload).state || "",
      zip_code: (data as OrganizationPayload).zip_code || "",
      country: (data as OrganizationPayload).country || "US",
      congressional_district: (data as OrganizationPayload).congressional_district || "",
      founded_year: data.founded_year || "",
      org_type: data.org_type || "",
      aor_first_name: (data as OrganizationPayload).aor_first_name || "",
      aor_last_name: (data as OrganizationPayload).aor_last_name || "",
      aor_title: (data as OrganizationPayload).aor_title || "",
      aor_phone: (data as OrganizationPayload).aor_phone || "",
      aor_email: (data as OrganizationPayload).aor_email || "",
    });
    setCategoriesText((data.categories || []).join(", "));
    setEligibilityText((data.eligibility_tags || []).join(", "));
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: (payload: OrganizationPayload) => api.patch("/api/organizations/me", payload),
    onSuccess: () => {
      toast.success("Organization profile saved");
      queryClient.invalidateQueries({ queryKey: ["organization", "me"] });
    },
    onError: () => {
      toast.error("Failed to save profile");
    },
  });

  const onSave = () => {
    if (!form.name.trim()) {
      toast.error("Organization name is required");
      return;
    }
    saveMutation.mutate({
      ...form,
      email: form.email.trim() || undefined,
      aor_email: form.aor_email.trim() || undefined,
      categories: csvToList(categoriesText),
      eligibility_tags: csvToList(eligibilityText),
    });
  };

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {isLoading && (
        <div className="text-zinc-200 text-sm">Loading organization profile...</div>
      )}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-2xl border border-cyan-900/40 bg-[#081f2c]/90 p-6">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_10%_20%,rgba(16,185,129,0.18),transparent_45%),radial-gradient(circle_at_80%_0%,rgba(59,130,246,0.22),transparent_38%)]" />
        <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-cyan-100/90 mb-2">
              <Sparkles className="w-3.5 h-3.5" />
              RAG Organization Context
            </div>
            <h1 className="text-3xl font-semibold text-white">Organization Profile</h1>
            <p className="text-zinc-200 text-sm mt-1 max-w-2xl">
              Edit the profile your AI uses for grant matching, autofill, and narrative generation. Core completion requires name, mission, contact email, EIN, organization type and categories; it does not certify eligibility or compliance.
            </p>
          </div>
          <div className="inline-flex items-center gap-3">
            <Badge variant="outline" className={data?.profile_complete ? "border-emerald-300/50 bg-emerald-500/10 text-emerald-100" : "border-amber-300/50 bg-amber-500/10 text-amber-100"}>
              {data?.profile_complete ? "Core Profile Fields Complete" : "Core Profile Fields Incomplete"}
            </Badge>
            <Button
              onClick={onSave}
              disabled={isLoading || saveMutation.isPending}
              className="h-10 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-[#03141c] font-semibold"
            >
              <Save className="w-4 h-4" />
              {saveMutation.isPending ? "Saving..." : "Save Profile"}
            </Button>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card className="glass rounded-2xl p-2 border border-cyan-900/40">
          <CardHeader>
          <div className="flex items-center gap-2 mb-4 text-zinc-100">
            <Building2 className="w-4 h-4" />
            <CardTitle className="font-medium">Identity</CardTitle>
          </div>
          </CardHeader>
          <CardContent>
          <div className="space-y-3">
            <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Organization Name" value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="EIN (XX-XXXXXXX)" value={form.ein} onChange={(e) => setForm((s) => ({ ...s, ein: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Organization Type" value={form.org_type} onChange={(e) => setForm((s) => ({ ...s, org_type: e.target.value }))} />
            </div>
            <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Founded Year" value={form.founded_year} onChange={(e) => setForm((s) => ({ ...s, founded_year: e.target.value }))} />
            <Textarea className="bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 min-h-[90px]" placeholder="Organization Description" value={form.description} onChange={(e) => setForm((s) => ({ ...s, description: e.target.value }))} />
            <Textarea className="bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 min-h-[90px]" placeholder="Mission Statement" value={form.mission} onChange={(e) => setForm((s) => ({ ...s, mission: e.target.value }))} />
          </div>
          </CardContent>
        </Card>

        <Card className="glass rounded-2xl p-2 border border-cyan-900/40">
          <CardHeader>
          <div className="flex items-center gap-2 mb-4 text-zinc-100">
            <Globe className="w-4 h-4" />
            <CardTitle className="font-medium">Contact and Eligibility</CardTitle>
          </div>
          </CardHeader>
          <CardContent>
          <div className="space-y-3">
            <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Website" value={form.website} onChange={(e) => setForm((s) => ({ ...s, website: e.target.value }))} />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Phone" value={form.phone} onChange={(e) => setForm((s) => ({ ...s, phone: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Email" value={form.email} onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))} />
            </div>
            <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Street Address" value={form.address} onChange={(e) => setForm((s) => ({ ...s, address: e.target.value }))} />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Input className="col-span-2 h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="City" value={form.city} onChange={(e) => setForm((s) => ({ ...s, city: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="State" value={form.state} onChange={(e) => setForm((s) => ({ ...s, state: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="ZIP" value={form.zip_code} onChange={(e) => setForm((s) => ({ ...s, zip_code: e.target.value }))} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Country (e.g. US)" value={form.country} onChange={(e) => setForm((s) => ({ ...s, country: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Congressional District (e.g. TX-30)" value={form.congressional_district} onChange={(e) => setForm((s) => ({ ...s, congressional_district: e.target.value }))} />
            </div>
            <Textarea className="bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 min-h-[80px]" placeholder="Capabilities (program strengths, service footprint, audited capacity)" value={form.capabilities} onChange={(e) => setForm((s) => ({ ...s, capabilities: e.target.value }))} />
            <Textarea className="bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 min-h-[62px]" placeholder="Categories (comma-separated). Example: Youth Services, STEM, Family Support" value={categoriesText} onChange={(e) => setCategoriesText(e.target.value)} />
            <Textarea className="bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 min-h-[62px]" placeholder="Eligibility Tags (comma-separated). Example: 501c3, Texas, Education" value={eligibilityText} onChange={(e) => setEligibilityText(e.target.value)} />
          </div>
          </CardContent>
        </Card>
      </div>

      {/* Federal Registration */}
      <Card className="glass rounded-2xl p-2 border border-amber-900/40">
        <CardHeader>
          <div className="flex items-center gap-2 mb-1 text-zinc-100">
            <ShieldCheck className="w-4 h-4 text-amber-300" />
            <CardTitle className="font-medium">Federal Registration (SAM.gov)</CardTitle>
          </div>
          <p className="text-xs text-zinc-400 ml-6">
            Required to apply for any federal grant. Your UEI (Unique Entity Identifier) replaced DUNS in 2022.{" "}
            <a href="https://sam.gov" target="_blank" rel="noopener noreferrer" className="text-amber-300 hover:text-amber-100 underline">Register at sam.gov →</a>
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">SAM.gov UEI (12-character)</label>
              <Input
                className={`h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100 font-mono tracking-wider ${form.uei ? "border-amber-500/50" : ""}`}
                placeholder="e.g. ABCDE123FGH4"
                value={form.uei}
                onChange={(e) => setForm((s) => ({ ...s, uei: e.target.value.toUpperCase() }))}
                maxLength={12}
              />
              {form.uei && form.uei.length !== 12 && (
                <p className="text-xs text-amber-400 mt-0.5">UEI should be exactly 12 characters</p>
              )}
            </div>
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">EIN (for SF-424 line 8b)</label>
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="XX-XXXXXXX" value={form.ein} onChange={(e) => setForm((s) => ({ ...s, ein: e.target.value }))} />
            </div>
          </div>
          {!form.uei && (
            <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
              ⚠ No UEI on file. You cannot apply for federal grants without SAM.gov registration. The SF-424 auto-fill will skip the UEI field.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Authorized Organizational Representative */}
      <Card className="glass rounded-2xl p-2 border border-cyan-900/40">
        <CardHeader>
          <div className="flex items-center gap-2 mb-1 text-zinc-100">
            <UserCheck className="w-4 h-4 text-cyan-300" />
            <CardTitle className="font-medium">Authorized Organizational Representative (AOR)</CardTitle>
          </div>
          <p className="text-xs text-zinc-400 ml-6">
            The AOR is the person authorized to submit federal grant applications on behalf of your organization. Their info appears on SF-424 Section 21.
          </p>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="First Name" value={form.aor_first_name} onChange={(e) => setForm((s) => ({ ...s, aor_first_name: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Last Name" value={form.aor_last_name} onChange={(e) => setForm((s) => ({ ...s, aor_last_name: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Title / Position" value={form.aor_title} onChange={(e) => setForm((s) => ({ ...s, aor_title: e.target.value }))} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Phone" value={form.aor_phone} onChange={(e) => setForm((s) => ({ ...s, aor_phone: e.target.value }))} />
              <Input className="h-10 bg-[#0d2635]/80 border-cyan-900/40 text-zinc-100" placeholder="Email" value={form.aor_email} onChange={(e) => setForm((s) => ({ ...s, aor_email: e.target.value }))} />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="glass rounded-2xl p-2 border border-cyan-900/40">
        <CardHeader>
        <div className="flex items-center gap-2 mb-2 text-zinc-100">
          <FileText className="w-4 h-4" />
          <CardTitle className="font-medium">How This Powers AI Autofill</CardTitle>
        </div>
        </CardHeader>
        <CardContent>
        <p className="text-zinc-400 text-sm">
          The AI engine uses this profile alongside knowledge documents to rank grants and draft proposal content. Keep mission, capabilities, categories, and eligibility tags current for higher match quality.
        </p>
        </CardContent>
      </Card>
    </div>
  );
}
