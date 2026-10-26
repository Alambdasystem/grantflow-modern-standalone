"use client";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  FileSearch,
  FolderOpen,
  Zap,
  Bot,
  BarChart3,
  RefreshCw,
  Settings,
  Menu,
  X,
  BookOpen,
  ShieldCheck,
  LogOut,
} from "lucide-react";
import {
  isGrantFlowLoginPath,
  isGrantFlowPublicPath,
  logoutGrantFlowClient,
  requireGrantFlowAuth,
} from "@/lib/auth-session";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/grants", label: "Grant Discovery", icon: FileSearch },
  { href: "/applications", label: "Applications", icon: FolderOpen },
  { href: "/operations", label: "Organization Workspace", icon: BookOpen },
  { href: "/documents", label: "Document ingestion", icon: BookOpen },
  { href: "/renewals", label: "Renewals", icon: RefreshCw },
  { href: "/automation", label: "Automation", icon: Zap },
  { href: "/ai", label: "AI Assistant", icon: Bot },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/accounts", label: "Accounts", icon: ShieldCheck },
  { href: "/email-monitor", label: "Email Safety", icon: ShieldCheck },
  { href: "/gap-solutions", label: "Gap Solutions", icon: ShieldCheck },
  { href: "/docs", label: "Documentation", icon: BookOpen },
];

function SidebarBody({
  pathname,
  onNavigate,
  onLogout,
}: {
  pathname: string | null;
  onNavigate?: () => void;
  onLogout: () => void;
}) {
  return (
    <>
      <div className="pointer-events-none absolute -left-20 top-[-3rem] h-44 w-44 rounded-full bg-cyan-300/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-20 bottom-[-4rem] h-52 w-52 rounded-full bg-amber-300/15 blur-3xl" />

      <div className="px-5 py-5 border-b border-cyan-900/50 relative z-10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-cyan-400/20 border border-cyan-300/30 flex items-center justify-center shadow-[0_0_18px_rgba(56,189,248,0.35)]">
            <span className="text-cyan-200 font-bold text-sm">GF</span>
          </div>
          <div>
            <div className="text-zinc-100 font-semibold text-sm leading-tight">
              GrantFlow
            </div>
            <div className="text-cyan-200/70 text-xs tracking-[0.18em] uppercase">
              Control Room
            </div>
          </div>
        </div>
      </div>

      <div className="relative z-10 flex-1 px-3 py-4 space-y-1.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href || (pathname?.startsWith(href + "/") ?? false);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={clsx(
                "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-200",
                active
                  ? "bg-cyan-400/15 text-cyan-200 font-medium border border-cyan-300/30"
                  : "text-zinc-300 hover:text-white hover:bg-[#112536]"
              )}
            >
              <Icon
                className={clsx(
                  "w-4 h-4 shrink-0 transition-transform group-hover:scale-110",
                  active && "drop-shadow-[0_0_10px_rgba(103,232,249,0.6)]"
                )}
              />
              {label}
            </Link>
          );
        })}
      </div>

      <div className="relative z-10 px-3 pb-4 border-t border-cyan-900/50 pt-3 space-y-1">
        <Link
          href="/settings"
          onClick={onNavigate}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-zinc-300 hover:text-white hover:bg-[#112536] transition"
        >
          <Settings className="w-4 h-4" />
          Settings
        </Link>
        <button
          type="button"
          onClick={onLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-zinc-400 hover:text-red-300 hover:bg-red-900/20 transition"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
      </div>
    </>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const loggingOutRef = useRef(false);

  // Auth guard: redirect to /login if no token (skip on login page itself)
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    requireGrantFlowAuth({
      pathname,
      loggingOut: loggingOutRef.current,
      localStorage: window.localStorage,
      location: window.location,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  async function handleLogout() {
    loggingOutRef.current = true;
    setOpen(false);
    if (typeof window !== "undefined") {
      const token = window.localStorage.getItem("authToken");
      const csrf=document.cookie.match(/(?:^|; )(__Host-gfm_csrf|gfm_csrf)=([^;]*)/);
      try {
        const response = await fetch("/gfm-app/api/auth/logout", {
          method: "POST",
          headers: {...(token ? { Authorization: `Bearer ${token}` } : {}),...(csrf?{'X-CSRF-Token':decodeURIComponent(csrf[2])}:{})},
        });
        if (!response.ok) throw new Error("Central sign-out failed");
        logoutGrantFlowClient({
          localStorage: window.localStorage,
          sessionStorage: window.sessionStorage,
          queryClient,
          location: window.location,
        });
      } catch {
        loggingOutRef.current = false;
        window.alert("Sign-out could not be confirmed. Please try again.");
      }
    }
  }

  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // Don't render sidebar on login page
  if (isGrantFlowLoginPath(pathname) || isGrantFlowPublicPath(pathname)) return null;

  return (
    <>
      <header className="lg:hidden fixed top-0 inset-x-0 z-40 flex items-center justify-between px-4 h-14 bg-[#06121b]/95 backdrop-blur border-b border-cyan-900/50">
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5"
        >
          <div className="w-8 h-8 rounded-lg bg-cyan-400/20 border border-cyan-300/30 flex items-center justify-center">
            <span className="text-cyan-200 font-bold text-xs">GF</span>
          </div>
          <span className="text-zinc-100 font-semibold text-sm">
            GrantFlow
          </span>
        </Link>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          className="inline-flex items-center justify-center h-10 w-10 rounded-lg border border-cyan-900/60 bg-[#0d2433] text-cyan-100 hover:bg-cyan-500/10 transition"
        >
          <Menu className="w-5 h-5" />
        </button>
      </header>

      <div className="lg:hidden h-14 shrink-0" aria-hidden />

      <nav className="relative w-64 shrink-0 hidden lg:flex flex-col h-screen overflow-hidden border-r border-cyan-900/50 bg-[#08141f]/90 backdrop-blur-xl">
        <SidebarBody pathname={pathname} onLogout={handleLogout} />
      </nav>

      {open && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <nav className="relative w-72 max-w-[85%] h-full flex flex-col overflow-hidden border-r border-cyan-900/50 bg-[#08141f]/95 backdrop-blur-xl">
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close navigation"
              className="absolute top-3 right-3 z-20 inline-flex items-center justify-center h-9 w-9 rounded-lg border border-cyan-900/60 bg-[#0d2433] text-cyan-100"
            >
              <X className="w-5 h-5" />
            </button>
            <SidebarBody
              pathname={pathname}
              onNavigate={() => setOpen(false)}
              onLogout={handleLogout}
            />
          </nav>
        </div>
      )}
    </>
  );
}
