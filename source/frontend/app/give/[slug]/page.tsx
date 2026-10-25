"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Heart, DollarSign, Check, AlertCircle, Loader2 } from "lucide-react";

const API_BASE = "/gfm-app";

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts?.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

interface CampaignPublic {
  id: number;
  name: string;
  description?: string;
  goal_amount?: number;
  raised_amount: number;
  progress_pct: number;
  campaign_type: string;
  end_date?: string;
  is_active: boolean;
  donation_count: number;
  thank_you_message?: string;
}

function fmt(n: number) {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

export default function GivePage() {
  const slug = useParams<{ slug: string }>()?.slug || "";

  const [step, setStep] = useState<"form" | "success">("form");
  const [amount, setAmount] = useState("");
  const [donorType, setDonorType] = useState("individual");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [donationType, setDonationType] = useState("cash");
  const [isAnonymous, setIsAnonymous] = useState(false);
  const [isRestricted, setIsRestricted] = useState(false);
  const [restrictionPurpose, setRestrictionPurpose] = useState("");
  const [thankYouMessage, setThankYouMessage] = useState("");
  const [error, setError] = useState("");

  const PRESET_AMOUNTS = [50, 100, 250, 500, 1000, 2500];

  const { data: campaign, isLoading, isError } = useQuery<CampaignPublic>({
    queryKey: ["give", slug],
    enabled: !!slug,
    queryFn: () => apiFetch(`/api/give/${slug}`),
    retry: false,
  });

  const donateMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch(`/api/give/${slug}/donate`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      setThankYouMessage(data?.thank_you_message || "Thank you for your generous contribution!");
      setStep("success");
    },
    onError: (err: Error) => setError(err.message || "Submission failed. Please try again."),
  });

  function handleSubmit() {
    setError("");
    const amountNum = parseFloat(amount);
    if (!amountNum || amountNum <= 0) {
      setError("Please enter a valid amount.");
      return;
    }
    if (!email && !isAnonymous) {
      setError("Please enter an email address or mark as anonymous.");
      return;
    }

    donateMutation.mutate({
      amount: amountNum,
      donation_type: donationType,
      donor_type: donorType,
      donor_first_name: firstName || null,
      donor_last_name: lastName || null,
      donor_organization_name: orgName || null,
      donor_email: email || null,
      donor_phone: phone || null,
      is_anonymous: isAnonymous,
      is_restricted: isRestricted,
      restriction_purpose: isRestricted ? restrictionPurpose : null,
    });
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#06121b] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-rose-400 animate-spin" />
      </div>
    );
  }

  if (isError || !campaign) {
    return (
      <div className="min-h-screen bg-[#06121b] flex items-center justify-center text-zinc-400">
        <div className="text-center">
          <AlertCircle className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
          <p className="text-lg font-medium text-zinc-300">Campaign not found</p>
          <p className="text-sm mt-1">This donation link is no longer active or doesn't exist.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#06121b] text-zinc-100">
      {/* Header band */}
      <div className="bg-gradient-to-br from-rose-900/40 to-[#06121b] border-b border-rose-900/30 px-4 py-8">
        <div className="max-w-lg mx-auto text-center">
          <div className="w-12 h-12 rounded-2xl bg-rose-500/20 border border-rose-400/30 flex items-center justify-center mx-auto mb-4">
            <Heart className="w-6 h-6 text-rose-400" />
          </div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-1">{campaign.name}</h1>
          {campaign.description && (
            <p className="text-sm text-zinc-400 leading-relaxed">{campaign.description}</p>
          )}
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-8">
        {/* Progress bar */}
        {campaign.goal_amount && (
          <div className="mb-8 p-4 bg-[#0d2433] rounded-2xl border border-rose-900/30">
            <div className="flex justify-between items-end mb-2">
              <div>
                <p className="text-xl font-bold text-rose-300">{fmt(campaign.raised_amount)}</p>
                <p className="text-xs text-zinc-500">raised of {fmt(campaign.goal_amount)} goal</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-zinc-400">{campaign.donation_count} donations</p>
                <p className="text-xs text-zinc-600">{campaign.progress_pct}%</p>
              </div>
            </div>
            <div className="w-full h-2.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-rose-600 to-rose-400 rounded-full transition-all"
                style={{ width: `${Math.min(100, campaign.progress_pct)}%` }}
              />
            </div>
          </div>
        )}

        {step === "success" ? (
          <div className="text-center py-10">
            <div className="w-16 h-16 rounded-full bg-green-500/20 border border-green-400/30 flex items-center justify-center mx-auto mb-4">
              <Check className="w-8 h-8 text-green-400" />
            </div>
            <h2 className="text-xl font-semibold text-zinc-100 mb-2">Thank You!</h2>
            <p className="text-zinc-400 text-sm leading-relaxed">{thankYouMessage}</p>
            <button
              onClick={() => { setStep("form"); setAmount(""); setEmail(""); }}
              className="mt-6 text-xs text-zinc-500 hover:text-zinc-300 underline"
            >
              Make another donation
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Amount */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">Donation Amount</label>
              <div className="grid grid-cols-3 gap-2 mb-3">
                {PRESET_AMOUNTS.map(a => (
                  <button key={a}
                    onClick={() => setAmount(String(a))}
                    className={`py-2.5 text-sm font-medium rounded-xl border transition ${amount === String(a) ? "bg-rose-500/30 border-rose-400/50 text-rose-300" : "bg-[#0d2433] border-cyan-900/40 text-zinc-300 hover:border-rose-500/30 hover:text-rose-300"}`}>
                    {fmt(a)}
                  </button>
                ))}
              </div>
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400">
                  <DollarSign className="w-4 h-4" />
                </span>
                <input
                  type="number"
                  value={amount}
                  onChange={e => setAmount(e.target.value)}
                  placeholder="Enter custom amount"
                  className="w-full pl-9 pr-4 py-3 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-rose-500/50"
                />
              </div>
            </div>

            {/* Donation type */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">Payment Method</label>
              <select value={donationType} onChange={e => setDonationType(e.target.value)}
                className="w-full px-3 py-2.5 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 focus:outline-none">
                <option value="cash">Cash</option>
                <option value="check">Check</option>
                <option value="pledge">Pledge (promise to give)</option>
                <option value="in-kind">In-Kind</option>
                <option value="wire">Wire Transfer</option>
                <option value="stock">Stock / Securities</option>
              </select>
            </div>

            {/* Donor info */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">Donor Information</label>

              <label className="flex items-center gap-2 mb-3 text-sm text-zinc-400 cursor-pointer">
                <input type="checkbox" checked={isAnonymous}
                  onChange={e => setIsAnonymous(e.target.checked)}
                  className="rounded border-zinc-600" />
                Make this donation anonymous
              </label>

              {!isAnonymous && (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <button onClick={() => setDonorType("individual")}
                      className={`flex-1 py-1.5 text-xs rounded-lg border transition ${donorType === "individual" ? "bg-rose-500/20 border-rose-400/40 text-rose-300" : "bg-[#0d2433] border-zinc-700 text-zinc-500"}`}>
                      Individual
                    </button>
                    <button onClick={() => setDonorType("business")}
                      className={`flex-1 py-1.5 text-xs rounded-lg border transition ${donorType === "business" ? "bg-rose-500/20 border-rose-400/40 text-rose-300" : "bg-[#0d2433] border-zinc-700 text-zinc-500"}`}>
                      Business / Org
                    </button>
                  </div>

                  {donorType === "individual" ? (
                    <div className="grid grid-cols-2 gap-2">
                      <input value={firstName} onChange={e => setFirstName(e.target.value)}
                        placeholder="First name"
                        className="px-3 py-2.5 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none" />
                      <input value={lastName} onChange={e => setLastName(e.target.value)}
                        placeholder="Last name"
                        className="px-3 py-2.5 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none" />
                    </div>
                  ) : (
                    <input value={orgName} onChange={e => setOrgName(e.target.value)}
                      placeholder="Organization name"
                      className="w-full px-3 py-2.5 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none" />
                  )}

                  <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                    placeholder="Email address *"
                    className="w-full px-3 py-2.5 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none" />

                  <input value={phone} onChange={e => setPhone(e.target.value)}
                    placeholder="Phone (optional)"
                    className="w-full px-3 py-2.5 text-sm bg-[#0d2433] border border-cyan-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none" />
                </div>
              )}
            </div>

            {/* Restricted */}
            <div>
              <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
                <input type="checkbox" checked={isRestricted}
                  onChange={e => setIsRestricted(e.target.checked)}
                  className="rounded border-zinc-600" />
                Designate this gift for a specific purpose
              </label>
              {isRestricted && (
                <input
                  value={restrictionPurpose}
                  onChange={e => setRestrictionPurpose(e.target.value)}
                  placeholder="e.g. Youth Scholarship Fund"
                  className="mt-2 w-full px-3 py-2.5 text-sm bg-[#0d2433] border border-amber-900/40 rounded-xl text-zinc-200 placeholder-zinc-600 focus:outline-none"
                />
              )}
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 bg-red-900/20 border border-red-500/30 rounded-xl text-sm text-red-300">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                {error}
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={donateMutation.isPending}
              className="w-full py-3.5 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-semibold text-sm rounded-xl transition flex items-center justify-center gap-2"
            >
              {donateMutation.isPending ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Processing…</>
              ) : (
                <><Heart className="w-4 h-4" /> {amount ? `Donate ${fmt(parseFloat(amount) || 0)}` : "Submit Donation"}</>
              )}
            </button>

            <p className="text-xs text-zinc-600 text-center leading-relaxed">
              Your donation information will be securely recorded and a receipt will be provided.
              For questions, contact the organization directly.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
