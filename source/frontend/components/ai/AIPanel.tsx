"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Sparkles, Send, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";

const QUICK_PROMPTS = [
  "Summarize recent grant opportunities",
  "Draft a 2-paragraph proposal intro",
  "List upcoming renewal deadlines",
];

export function AIPanel() {
  const [prompt, setPrompt] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [aiError, setAiError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const canSend = prompt.trim().length > 0 && !isGenerating;

  const generate = async (text: string) => {
    const nextPrompt = text.trim();
    if (!nextPrompt || isGenerating) return;

    setIsGenerating(true);
    setAiResponse("");
    setAiError("");
    try {
      const res = await api.post("/api/ai/generate", {
        task: "general",
        context: nextPrompt,
        stream: false,
      });
      setAiResponse(
        res.data?.result || res.data?.text || "No response generated."
      );
    } catch {
      setAiError(
        "AI service is unavailable. Make sure Ollama is running on the backend."
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSubmit = async (event?: React.FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    await generate(prompt);
  };

  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5 flex flex-col gap-4 border border-cyan-900/40">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_85%_15%,rgba(245,158,11,0.18),transparent_38%),radial-gradient(circle_at_10%_90%,rgba(56,189,248,0.18),transparent_36%)]" />
      <div className="relative flex items-center gap-2">
        <div className="w-8 h-8 rounded-xl bg-amber-400/15 border border-amber-300/30 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-amber-200" />
        </div>
        <div>
          <h2 className="text-zinc-100 font-semibold text-sm">AI Quick Actions</h2>
          <p className="text-zinc-300 text-[11px]">
            Powered by your local Ollama model
          </p>
        </div>
      </div>

      <div className="relative space-y-2">
        {QUICK_PROMPTS.map((p) => (
          <button
            key={p}
            onClick={() => {
              setPrompt(p);
              void generate(p);
            }}
            disabled={isGenerating}
            className="w-full text-left px-3 py-2 rounded-xl bg-[#0d2434]/85 hover:bg-cyan-500/10 border border-cyan-900/40 hover:border-cyan-300/40 text-zinc-200 text-xs transition disabled:opacity-50"
          >
            {p}
          </button>
        ))}
      </div>

      <form className="relative flex gap-2" onSubmit={handleSubmit}>
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask the AI…"
          className="flex-1 bg-[#0d2434]/80 border border-cyan-900/40 rounded-xl px-3 py-2 text-zinc-100 placeholder-zinc-400 text-xs focus:outline-none focus:border-cyan-300/60"
        />
        <button
          type="submit"
          disabled={!canSend}
          className="px-3 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 disabled:opacity-50 text-[#03141c] text-xs font-semibold"
          aria-label="Send"
        >
          {isGenerating ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Send className="w-3.5 h-3.5" />
          )}
        </button>
      </form>

      {(isGenerating || aiResponse || aiError) && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative bg-[#0d2434]/85 border border-cyan-900/40 rounded-xl p-3 max-h-56 overflow-y-auto"
        >
          <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-200/80 mb-2">
            Latest AI response
          </p>
          {isGenerating ? (
            <p className="text-xs text-cyan-200 animate-pulse">Generating…</p>
          ) : aiError ? (
            <p className="text-xs text-rose-200 leading-relaxed whitespace-pre-wrap">{aiError}</p>
          ) : (
            <p className="text-xs text-zinc-200 leading-relaxed whitespace-pre-wrap">{aiResponse}</p>
          )}
        </motion.div>
      )}
    </div>
  );
}
