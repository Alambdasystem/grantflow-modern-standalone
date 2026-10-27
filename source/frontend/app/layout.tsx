import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { Toaster } from "sonner";

const displayFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GrantFlow Modern",
  description: "AI-native grant management and renewal operating system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={displayFont.variable} suppressHydrationWarning>
        <QueryProvider>
          <div className="relative flex min-h-screen lg:h-screen lg:overflow-hidden mesh-bg">
            <div className="pointer-events-none fixed inset-0 z-0">
              <div className="absolute -left-32 top-[-8rem] h-72 w-72 rounded-full bg-cyan-300/20 blur-3xl ambient-float" />
              <div className="absolute right-[-8rem] top-[22%] h-72 w-72 rounded-full bg-amber-300/20 blur-3xl ambient-float" />
              <div className="absolute bottom-[-9rem] left-[35%] h-72 w-72 rounded-full bg-emerald-300/14 blur-3xl ambient-float" />
            </div>
            <Sidebar />
            <main className="relative z-10 min-w-0 flex-1 overflow-y-auto pt-14 lg:pt-0 bg-transparent scanline">
              <div className="mx-auto w-full max-w-[1600px]">{children}</div>
            </main>
          </div>
          <Toaster
            theme="dark"
            position="bottom-right"
            richColors
            closeButton
          />
        </QueryProvider>
      </body>
    </html>
  );
}
