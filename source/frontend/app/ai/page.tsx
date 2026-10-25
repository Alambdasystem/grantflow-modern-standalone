"use client";
import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import Link from "next/link";
import { Send, Bot, User, Sparkles } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function AIPage() {
  const [conversationId,setConversationId] = useState<number|null>(null);
  const [history,setHistory] = useState<{id:number;messages:Message[]}[]>([]);
  const [historyError,setHistoryError] = useState("");
  useEffect(()=>{api.get('/api/ai/conversations').then(r=>{
    setHistory(r.data);
    if(r.data[0]) {setConversationId(r.data[0].id);setMessages(r.data[0].messages);}
  }).catch(()=>setHistoryError('Saved conversations unavailable.'));},[]);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm your GrantFlow AI assistant. I can help you write grant proposals, analyze funding opportunities, check compliance requirements, and more. What would you like to work on today?",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [requestError,setRequestError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setRequestError("");

    try {
      const updatedMessages = [...messages, userMsg];
      const res = await api.post("/api/ai/chat", {
        messages: updatedMessages,
        conversation_id: conversationId,
        stream: false,
      });
      setConversationId(res.data.conversation_id);
      api.get('/api/ai/conversations').then(r=>setHistory(r.data)).catch(()=>setHistoryError('Saved conversations unavailable.'));
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.data.reply || "I couldn't generate a response." },
      ]);
    } catch (error) {
      const detail=(error as {response?:{data?:{detail?:string}}}).response?.data?.detail;
      setMessages(messages);
      setInput(userMsg.content);
      setRequestError(detail || "The AI request failed. Please retry; your saved conversation has not changed.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col h-screen p-6">
      <div className="flex flex-wrap gap-3 mb-3 text-sm">
        <Link className="underline" href="/operations">Knowledge, alignment &amp; LOI drafts</Link>
        <select disabled={loading} aria-label="Saved conversations" className="bg-zinc-900 p-1" value={conversationId||''} onChange={e=>{const id=Number(e.target.value);const saved=history.find(h=>h.id===id);setConversationId(id||null);setMessages(saved?.messages||[]);setRequestError("");}}><option value="">New conversation</option>{history.map(h=><option key={h.id} value={h.id}>Conversation {h.id}</option>)}</select>
        <button className="underline" onClick={()=>{const url=URL.createObjectURL(new Blob([messages.map(m=>m.role+': '+m.content).join('\n\n')],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download='grantflow-conversation.txt';a.click();URL.revokeObjectURL(url);}}>Export conversation</button>
        {historyError&&<span role="status">{historyError}</span>}
      </div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 rounded-xl bg-indigo-500/20 flex items-center justify-center">
          <Sparkles className="w-5 h-5 text-indigo-400" />
        </div>
        <div>
          <h1 className="text-2xl font-bold gradient-text">AI Assistant</h1>
          <p className="text-zinc-500 text-xs">Powered by Ollama · llama3.2</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === "assistant"
                    ? "bg-indigo-500/20"
                    : "bg-zinc-700"
                }`}
              >
                {msg.role === "assistant" ? (
                  <Bot className="w-4 h-4 text-indigo-400" />
                ) : (
                  <User className="w-4 h-4 text-zinc-400" />
                )}
              </div>
              <div
                className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "assistant"
                    ? "glass text-zinc-100"
                    : "bg-indigo-600 text-white"
                }`}
              >
                {msg.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center">
              <Bot className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="glass px-4 py-3 rounded-2xl text-sm text-zinc-400">
              <span className="animate-pulse">Generating response...</span>
            </div>
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {requestError&&<p role="alert" className="text-amber-300 py-2">{requestError}</p>}
      <div className="flex gap-3 pt-4 border-t border-zinc-800">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about grants, request a proposal draft, check compliance..."
          rows={2}
          className="flex-1 resize-none bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-zinc-100 placeholder-zinc-500 text-sm focus:outline-none focus:border-indigo-500"
        />
        <button
          aria-label="Send message"
          onClick={send}
          disabled={loading || !input.trim()}
          className="px-4 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition flex items-center gap-2 text-sm font-medium"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
