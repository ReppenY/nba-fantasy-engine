"use client";
import { useEffect, useState } from "react";
import { api, TradeResponse, TradeProposal } from "@/lib/api";
import { Card, CardTitle } from "@/components/Card";
import { ArrowRight, Search } from "lucide-react";

const CATS = ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "tov"];
const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

export default function TradesPage() {
  const [giveInput, setGiveInput] = useState("");
  const [receiveInput, setReceiveInput] = useState("");
  const [result, setResult] = useState<TradeResponse | null>(null);
  const [proposals, setProposals] = useState<TradeProposal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getTradeProposals(10).then(setProposals).catch(() => {});
  }, []);

  async function evaluate() {
    setError("");
    setResult(null);
    const give = giveInput.split(",").map((s) => s.trim()).filter(Boolean);
    const receive = receiveInput.split(",").map((s) => s.trim()).filter(Boolean);
    if (!give.length || !receive.length) { setError("Enter player names on both sides"); return; }
    setLoading(true);
    try {
      const res = await api.evaluateTrade(give, receive);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Trade evaluation failed");
    } finally {
      setLoading(false);
    }
  }

  const verdictColors: Record<string, string> = {
    strong_accept: "text-green-400 bg-green-500/10",
    accept: "text-green-400 bg-green-500/10",
    slight_accept: "text-green-300 bg-green-500/5",
    slight_decline: "text-red-300 bg-red-500/5",
    decline: "text-red-400 bg-red-500/10",
    strong_decline: "text-red-400 bg-red-500/10",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trade Center</h1>

      {/* Trade Evaluator */}
      <Card>
        <CardTitle>Evaluate a Trade</CardTitle>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">You give</label>
            <input
              value={giveInput}
              onChange={(e) => setGiveInput(e.target.value)}
              placeholder="LeBron James, Kyle Kuzma"
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500"
            />
          </div>
          <ArrowRight size={20} className="text-zinc-500 mb-2" />
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">You receive</label>
            <input
              value={receiveInput}
              onChange={(e) => setReceiveInput(e.target.value)}
              placeholder="Amen Thompson"
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500"
            />
          </div>
          <button
            onClick={evaluate}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 flex items-center gap-2"
          >
            <Search size={16} /> {loading ? "..." : "Evaluate"}
          </button>
        </div>
        {error && <p className="text-red-400 text-sm mt-2">{error}</p>}

        {result && (
          <div className="mt-4 space-y-3">
            <div className={`inline-block px-3 py-1.5 rounded-lg text-sm font-bold ${verdictColors[result.verdict] || "text-zinc-400 bg-zinc-800"}`}>
              {result.verdict.replace(/_/g, " ").toUpperCase()} (score: {result.combined_score.toFixed(1)})
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-zinc-500">Z-score change:</span>{" "}
                <span className={result.z_diff > 0 ? "text-green-400" : "text-red-400"}>
                  {result.z_diff > 0 ? "+" : ""}{result.z_diff.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-zinc-500">Salary impact:</span>{" "}
                <span className={result.salary_impact < 0 ? "text-green-400" : "text-yellow-400"}>
                  {result.salary_impact > 0 ? "+" : ""}${result.salary_impact.toFixed(1)}
                </span>
              </div>
              <div>
                <span className="text-zinc-500">Dynasty diff:</span>{" "}
                <span className={result.dynasty_diff > 0 ? "text-green-400" : "text-red-400"}>
                  {result.dynasty_diff > 0 ? "+" : ""}{result.dynasty_diff.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-zinc-500">Cap after:</span> ${result.cap_room_after.toFixed(1)}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs mt-2">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-1">Cat</th>
                    <th className="text-right py-1">Give</th>
                    <th className="text-right py-1">Receive</th>
                    <th className="text-right py-1">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {CATS.map((cat) => {
                    const delta = result.cat_impact[cat] || 0;
                    return (
                      <tr key={cat} className="border-b border-zinc-800/50">
                        <td className="py-1 text-zinc-400">{CAT_LABELS[cat]}</td>
                        <td className="py-1 text-right font-mono">{(result.give.z_per_cat[cat] || 0).toFixed(1)}</td>
                        <td className="py-1 text-right font-mono">{(result.receive.z_per_cat[cat] || 0).toFixed(1)}</td>
                        <td className={`py-1 text-right font-mono font-bold ${delta > 0.1 ? "text-green-400" : delta < -0.1 ? "text-red-400" : "text-zinc-500"}`}>
                          {delta > 0 ? "+" : ""}{delta.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      {/* Trade Finder */}
      {proposals.length > 0 && (
        <Card>
          <CardTitle>Trade Finder — Mutually Beneficial Proposals</CardTitle>
          <div className="space-y-3">
            {proposals.map((p, i) => (
              <div key={i} className="p-3 border border-zinc-800 rounded-lg hover:border-zinc-700">
                <div className="flex items-center justify-between">
                  <div className="text-sm">
                    <span className="text-zinc-500">vs</span>{" "}
                    <span className="font-medium">{p.opponent_team}</span>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400">
                    mutual: {p.mutual_score.toFixed(1)}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-2 text-sm">
                  <div className="text-red-300">Give: {p.give.join(", ")}</div>
                  <ArrowRight size={14} className="text-zinc-600" />
                  <div className="text-green-300">Get: {p.receive.join(", ")}</div>
                </div>
                <div className="flex gap-4 mt-1 text-xs text-zinc-500">
                  <span>Helps you: {p.improves_me.map(c => CAT_LABELS[c] || c).join(", ")}</span>
                  <span>Helps them: {p.improves_them.map(c => CAT_LABELS[c] || c).join(", ")}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
