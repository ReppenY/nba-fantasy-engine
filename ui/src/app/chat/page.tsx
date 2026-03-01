"use client";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Send, RotateCcw, Bot, User } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState<"claude" | "openai">("claude");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setLoading(true);

    try {
      const res = await api.chat(msg, provider);
      setMessages((prev) => [...prev, { role: "assistant", content: `**[${provider.toUpperCase()}]**\n\n${res.response}` }]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${e instanceof Error ? e.message : "Failed to reach coach. Is ANTHROPIC_API_KEY set?"}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function reset() {
    await api.resetChat().catch(() => {});
    setMessages([]);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">AI Coach</h1>
          <p className="text-sm text-zinc-500">Ask about trades, lineup, strategy — backed by real analytics</p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex rounded-lg border border-zinc-700 overflow-hidden">
            {(["claude", "openai"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setProvider(p)}
                className={`px-3 py-1.5 text-xs ${
                  provider === p ? "bg-blue-600 text-white" : "text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {p === "claude" ? "Claude" : "GPT-5.2"}
              </button>
            ))}
          </div>
          <button
            onClick={reset}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-zinc-400 border border-zinc-700 rounded-lg hover:bg-zinc-800"
          >
            <RotateCcw size={14} /> Reset
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-zinc-600">
            <div className="text-center space-y-3">
              <Bot size={48} className="mx-auto opacity-30" />
              <p className="text-lg">Ask me anything about your fantasy team</p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {[
                  "Should I trade LeBron for Amen Thompson?",
                  "What should my punt strategy be?",
                  "Who should I start this week?",
                  "Who are the best free agents?",
                  "Is Giannis worth his $34 salary?",
                  "Find me some trades",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => { setInput(q); }}
                    className="text-xs px-3 py-1.5 rounded-full border border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                <Bot size={16} className="text-blue-400" />
              </div>
            )}
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-[#1a1b23] border border-[#2a2b35] text-zinc-200"
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
            {msg.role === "user" && (
              <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center flex-shrink-0">
                <User size={16} className="text-zinc-300" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
              <Bot size={16} className="text-blue-400" />
            </div>
            <div className="bg-[#1a1b23] border border-[#2a2b35] rounded-2xl px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-zinc-800 pt-4">
        <form
          onSubmit={(e) => { e.preventDefault(); send(); }}
          className="flex gap-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask your coach..."
            className="flex-1 bg-[#1a1b23] border border-[#2a2b35] rounded-xl px-4 py-3 text-sm outline-none focus:border-blue-500 placeholder:text-zinc-600"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}
