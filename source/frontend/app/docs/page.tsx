"use client";
import { BookOpen, LogIn, LayoutDashboard, FileSearch, FolderOpen, RefreshCw, Zap, Bot, BarChart3, Settings, ChevronRight } from "lucide-react";

interface Section {
  id: string;
  title: string;
  icon: React.ReactNode;
  screenshot: string;
  alt: string;
  content: React.ReactNode;
}

const sections: Section[] = [
  {
    id: "login",
    title: "Getting Started — Login",
    icon: <LogIn className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/login.png",
    alt: "GrantFlow Modern Login Screen",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          GrantFlow Modern is a secured platform. Access requires valid credentials
          before any data or features become available.
        </p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Navigate to <code className="text-cyan-300 bg-cyan-950/50 px-1 rounded">/gfm-app/login</code> — you will be redirected here automatically if not authenticated.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Enter your <strong className="text-zinc-100">Username</strong> and <strong className="text-zinc-100">Password</strong> in the provided fields.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Click <strong className="text-zinc-100">Sign in</strong>. A JWT token is securely stored in your browser and used for all subsequent API calls.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>On success you are redirected to the <strong className="text-zinc-100">Mission Control Dashboard</strong> automatically.</span>
          </li>
        </ul>
        <div className="glass rounded-lg px-4 py-3 border border-amber-400/20 bg-amber-400/5">
          <p className="text-amber-300 text-xs font-medium">Tip</p>
          <p className="text-zinc-400 text-xs mt-1">If you are redirected to the login page unexpectedly, your session may have expired. Simply sign in again — all your data is persisted on the server.</p>
        </div>
      </div>
    ),
  },
  {
    id: "dashboard",
    title: "Mission Control Dashboard",
    icon: <LayoutDashboard className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/dashboard.png",
    alt: "GrantFlow Modern Dashboard",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Dashboard is your command center — it provides a real-time snapshot of your entire grant portfolio in a single view.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Stat Cards</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Active Grants</strong> — total number of grant opportunities tracked in the system.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Applications</strong> — all applications across every pipeline stage.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Approved</strong> — applications that have been approved and are funding your organization.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Pending Renewals</strong> — applications approaching their renewal deadline.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Automation Jobs</strong> — AI-powered background tasks currently queued or running.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Total Awarded</strong> — cumulative funding secured across all approved applications.</span>
          </li>
        </ul>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Pipeline Focus &amp; AI Quick Actions</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The <strong className="text-zinc-100">Pipeline Focus</strong> panel shows totals for grants tracked, submitted applications, and pending renewals at a glance.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The <strong className="text-zinc-100">AI Quick Actions</strong> panel on the right lets you ask the local AI model anything — use the quick-prompts or type a custom question in the chat input.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The dashboard <strong className="text-zinc-100">auto-refreshes every 30 seconds</strong> so stats always reflect live data without manual reloads.</span>
          </li>
        </ul>
        <p className="text-zinc-400 text-xs">The <strong className="text-emerald-300">Current Win Rate</strong> badge in the top-right corner shows your approval percentage across decided applications, and displays N/A until a decision exists.</p>
      </div>
    ),
  },
  {
    id: "grants",
    title: "Grant Discovery Engine",
    icon: <FileSearch className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/grants.png",
    alt: "Grant Discovery Engine",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Grant Discovery Engine is where you find and track funding opportunities. It combines a manually-curated library with AI-powered live-feed ingestion.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Finding Grants</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Use the <strong className="text-zinc-100">Search bar</strong> to filter by keyword, agency name, or grant category.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Use the <strong className="text-zinc-100">Category dropdown</strong> to narrow results to a specific funding domain (Health, Arts, Finance, etc.).</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Each grant card shows the <strong className="text-zinc-100">agency</strong>, <strong className="text-zinc-100">funding amount</strong>, <strong className="text-zinc-100">deadline</strong>, and an <strong className="text-zinc-100">AI match score</strong> (0–100) ranking how well it fits your organization profile.</span>
          </li>
        </ul>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Discovering New Grants</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Click <strong className="text-zinc-100">Discover New Grants</strong> (top-right) to trigger the AI grant discovery pipeline — it pulls fresh listings from live public feeds and scores them against your profile.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>New grants appear in the list immediately after ingestion, tagged with a <strong className="text-emerald-300">New</strong> badge.</span>
          </li>
        </ul>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Applying to a Grant</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Click <strong className="text-zinc-100">Apply with AI</strong> on any grant card to automatically create a draft application and populate it using the AI writing engine.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The new application will appear in the <strong className="text-zinc-100">Applications</strong> kanban in <em>Draft</em> status.</span>
          </li>
        </ul>
      </div>
    ),
  },
  {
    id: "applications",
    title: "Applications Pipeline",
    icon: <FolderOpen className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/applications.png",
    alt: "Applications Kanban Pipeline",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Applications page uses a Kanban-style pipeline to track every application from initial draft through final decision and renewal.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Pipeline Stages</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { stage: "Draft", desc: "Application created but not yet submitted." },
            { stage: "Submitted", desc: "Sent to the funding agency for review." },
            { stage: "In Review", desc: "Under evaluation by the granting body." },
            { stage: "Approved", desc: "Grant awarded — funding secured." },
            { stage: "Rejected", desc: "Application was not selected this cycle." },
            { stage: "Renewal Due", desc: "Approved grant approaching renewal window." },
          ].map(({ stage, desc }) => (
            <div key={stage} className="glass rounded-lg px-3 py-2 border border-cyan-900/30">
              <p className="text-cyan-300 text-xs font-semibold">{stage}</p>
              <p className="text-zinc-400 text-xs mt-0.5">{desc}</p>
            </div>
          ))}
        </div>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest mt-2">Creating an Application</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Click <strong className="text-zinc-100">New Application</strong> to open the form — select a grant from the dropdown, add a title and requested amount, then submit.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Move cards between columns to update their status. The change is saved to the server immediately.</span>
          </li>
        </ul>
      </div>
    ),
  },
  {
    id: "renewals",
    title: "Renewals Tracker",
    icon: <RefreshCw className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/renewals.png",
    alt: "Renewals Tracker",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Renewals page surfaces all applications that have a renewal deadline, sorted by urgency so you never miss a critical window.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Urgency Rings</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <span className="w-3 h-3 rounded-full bg-rose-500 mt-1 shrink-0" />
            <span><strong className="text-rose-300">Rose / Red</strong> — deadline is within 7 days. Immediate action required.</span>
          </li>
          <li className="flex gap-2">
            <span className="w-3 h-3 rounded-full bg-amber-400 mt-1 shrink-0" />
            <span><strong className="text-amber-300">Amber / Yellow</strong> — deadline is within 30 days. Plan your renewal submission soon.</span>
          </li>
          <li className="flex gap-2">
            <span className="w-3 h-3 rounded-full bg-cyan-400 mt-1 shrink-0" />
            <span><strong className="text-cyan-300">Cyan / Blue</strong> — deadline is more than 30 days away. No immediate action needed.</span>
          </li>
        </ul>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest mt-1">Auto-Renew</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Click <strong className="text-zinc-100">Auto-Renew</strong> on any card to trigger the AI renewal pipeline — it drafts a renewal submission using your organization profile and historical grant data.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The renewal job is queued as an <strong className="text-zinc-100">Automation Job</strong> and tracked on the Automation page.</span>
          </li>
        </ul>
      </div>
    ),
  },
  {
    id: "automation",
    title: "Automation Center",
    icon: <Zap className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/automation.png",
    alt: "Automation Center",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Automation Center lists all AI-powered background jobs running on your behalf — from grant discovery to application drafting and renewals.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Job Statuses</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { status: "Queued", color: "text-zinc-400", desc: "Job is waiting to start." },
            { status: "Running", color: "text-cyan-300", desc: "Job is actively executing." },
            { status: "Completed", color: "text-emerald-300", desc: "Job finished successfully." },
            { status: "Failed", color: "text-rose-300", desc: "Job encountered an error." },
          ].map(({ status, color, desc }) => (
            <div key={status} className="glass rounded-lg px-3 py-2 border border-cyan-900/30">
              <p className={`text-xs font-semibold ${color}`}>{status}</p>
              <p className="text-zinc-400 text-xs mt-0.5">{desc}</p>
            </div>
          ))}
        </div>
        <ul className="space-y-2 pl-4 mt-2">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Each running job shows a <strong className="text-zinc-100">progress bar</strong> and a <strong className="text-zinc-100">current step</strong> description so you know exactly what the AI is doing.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The page <strong className="text-zinc-100">auto-refreshes every 5 seconds</strong> while jobs are active — no need to manually reload.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Jobs are created automatically when you click <em>Apply with AI</em>, <em>Discover New Grants</em>, or <em>Auto-Renew</em>.</span>
          </li>
        </ul>
      </div>
    ),
  },
  {
    id: "ai",
    title: "AI Assistant",
    icon: <Bot className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/ai.png",
    alt: "AI Assistant Chat Interface",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The AI Assistant gives you a direct conversational interface to the local Ollama language model powering GrantFlow Modern.
        </p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Type any grant-related question into the chat input at the bottom — press <strong className="text-zinc-100">Enter</strong> or click Send.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The AI has context about your organization profile and can help draft narrative text, suggest eligibility improvements, interpret grant requirements, and more.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Chat history is maintained for the duration of your session — scroll up to review earlier responses.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>The same AI engine powers the Quick Actions panel on the Dashboard and the <em>Apply with AI</em> automation pipeline.</span>
          </li>
        </ul>
        <div className="glass rounded-lg px-4 py-3 border border-cyan-400/20 bg-cyan-400/5">
          <p className="text-cyan-300 text-xs font-medium">Suggested Questions</p>
          <ul className="text-zinc-400 text-xs mt-1 space-y-1 list-disc list-inside">
            <li>What grants best fit our mission statement?</li>
            <li>Summarize the pending renewal deadlines.</li>
            <li>Draft a 2-paragraph proposal intro for a health grant.</li>
            <li>How can we improve our approval rate?</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: "analytics",
    title: "Analytics",
    icon: <BarChart3 className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/analytics.png",
    alt: "Analytics Charts",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Analytics page visualizes the health and performance of your grant portfolio with interactive charts and funding summaries.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Application Pipeline Chart</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>A <strong className="text-zinc-100">Bar Chart</strong> breaks down your applications by pipeline status — approved, draft, in_review, renewal_due, etc. — so you can see where bottlenecks occur.</span>
          </li>
        </ul>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Funding Overview Panel</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Total Awarded</strong> — cumulative amount secured across all approved grants.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Success Rate</strong> — percentage of decided applications that were approved.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span><strong className="text-zinc-100">Active Grants</strong> and <strong className="text-zinc-100">Pending Renewals</strong> summary counts.</span>
          </li>
        </ul>
        <p className="text-zinc-400 text-xs">Use these metrics regularly to identify which grant categories yield the best approval rates and adjust your discovery strategy accordingly.</p>
      </div>
    ),
  },
  {
    id: "settings",
    title: "Settings — Organization Profile",
    icon: <Settings className="w-5 h-5 text-cyan-400" />,
    screenshot: "/docs/settings.png",
    alt: "Settings — Organization Profile",
    content: (
      <div className="space-y-3 text-zinc-300 text-sm leading-relaxed">
        <p>
          The Settings page is where you define your organization identity. This profile is used by the AI engine to score grant matches, draft proposals, and generate renewal content.
        </p>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest">Profile Fields</p>
        <div className="grid grid-cols-1 gap-1.5">
          {[
            ["Organization Name", "Legal or DBA name of your nonprofit or agency."],
            ["EIN", "Employer Identification Number for tax-exempt status verification."],
            ["Description", "A concise overview of what your organization does."],
            ["Mission Statement", "Your core purpose — used directly in AI-generated proposals."],
            ["Capabilities", "Key programs and competencies that differentiate your organization."],
            ["Website / Phone / Email", "Contact information for grant correspondence."],
            ["Address", "Physical address, used for locality-restricted grants."],
            ["Founded Year", "Year of establishment — signals organizational maturity to reviewers."],
            ["Organization Type", "E.g. 501(c)(3), government agency, fiscal sponsor, etc."],
            ["Categories (CSV)", "Comma-separated funding domains your org operates in (e.g. Health, Education)."],
            ["Eligibility Tags (CSV)", "Keywords that match you to grant eligibility criteria (e.g. BIPOC-led, rural)."],
          ].map(([field, desc]) => (
            <div key={field} className="flex gap-3 items-start">
              <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
              <span><strong className="text-zinc-100">{field}</strong> — {desc}</span>
            </div>
          ))}
        </div>
        <p className="text-zinc-400 font-medium text-xs uppercase tracking-widest mt-1">AI Profile Generation</p>
        <ul className="space-y-2 pl-4">
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Click <strong className="text-zinc-100">Generate with AI</strong> to have the local model draft your mission, description, and capabilities based on your organization name and type.</span>
          </li>
          <li className="flex gap-2">
            <ChevronRight className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <span>Always review and refine AI-generated content before saving — the more accurate your profile, the better the grant match scores.</span>
          </li>
        </ul>
        <div className="glass rounded-lg px-4 py-3 border border-emerald-400/20 bg-emerald-400/5">
          <p className="text-emerald-300 text-xs font-medium">Best Practice</p>
          <p className="text-zinc-400 text-xs mt-1">Keep your Categories and Eligibility Tags up to date. These are the primary signals the discovery engine uses to surface relevant grants and calculate AI match scores.</p>
        </div>
      </div>
    ),
  },
];

export default function DocsPage() {
  return (
    <div className="space-y-10 pb-16">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <BookOpen className="w-7 h-7 text-cyan-400" />
          <h1 className="gradient-text text-3xl font-bold tracking-tight">Documentation</h1>
        </div>
        <p className="text-zinc-400 text-sm">
          Complete guide to using every feature in GrantFlow Modern — from first login to advanced AI automation.
        </p>
      </div>

      {/* Quick Navigation */}
      <div className="glass rounded-xl border border-cyan-900/40 p-5">
        <p className="text-zinc-400 text-xs font-medium uppercase tracking-widest mb-3">Sections</p>
        <div className="flex flex-wrap gap-2">
          {sections.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-cyan-900/30 text-cyan-300 hover:bg-cyan-900/60 hover:text-cyan-100 transition-colors"
            >
              {s.icon}
              {s.title.split("—")[0].trim()}
            </a>
          ))}
        </div>
      </div>

      {/* Sections */}
      {sections.map((section) => (
        <section key={section.id} id={section.id} className="scroll-mt-6">
          <div className="glass rounded-2xl border border-cyan-900/40 overflow-hidden">
            {/* Section Header */}
            <div className="px-6 pt-6 pb-4 border-b border-cyan-900/30 flex items-center gap-3">
              {section.icon}
              <h2 className="text-zinc-100 font-semibold text-lg">{section.title}</h2>
            </div>

            <div className="p-6 grid grid-cols-1 xl:grid-cols-2 gap-8 items-start">
              {/* Text content */}
              <div>{section.content}</div>

              {/* Screenshot */}
              <div className="rounded-xl overflow-hidden border border-cyan-900/40 shadow-[0_0_40px_rgba(0,0,0,0.5)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/gfm-app${section.screenshot}`}
                  alt={section.alt}
                  className="w-full h-auto"
                  loading="eager"
                />
              </div>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
