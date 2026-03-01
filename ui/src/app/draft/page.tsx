"use client";
import { useEffect, useState } from "react";
import { Card, CardTitle, StatBadge } from "@/components/Card";
import { ArrowRight, Gavel, DollarSign, AlertTriangle, Target } from "lucide-react";
import PlayerInput from "@/components/PlayerInput";

const BASE = "http://localhost:8000";
const fetchJ = <T,>(url: string, opts?: RequestInit): Promise<T> => fetch(`${BASE}${url}`, { headers: { "Content-Type": "application/json" }, ...opts }).then(r => r.json());

interface PlayerVal { name: string; nba_team: string; position: string; fair_value: number; tier: string; z_total: number; drafted: boolean }
interface Budget { team_name: string; remaining: number; spent: number; players_drafted: number; roster_spots_left: number; max_bid: number }
interface Pick { player_name: string; team: string; bid: number; fair_value: number; surplus: number }
interface BidRec { player_name: string; fair_value: number; max_bid: number; action: string; reason: string; priority: number }
interface Nomination { player_name: string; reason: string; strategy: string }

export default function DraftPage() {
  const [initialized, setInitialized] = useState(false);
  const [available, setAvailable] = useState<PlayerVal[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [log, setLog] = useState<Pick[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [bidRec, setBidRec] = useState<BidRec | null>(null);
  const [nominations, setNominations] = useState<Nomination[]>([]);

  // Pick form
  const [pickPlayer, setPickPlayer] = useState("");
  const [pickTeam, setPickTeam] = useState("");
  const [pickBid, setPickBid] = useState("");

  // Bid check
  const [checkPlayer, setCheckPlayer] = useState("");

  async function initDraft() {
    await fetchJ("/draft/init", { method: "POST", body: JSON.stringify({ my_team: "He Who Remains", budget: 233 }) });
    setInitialized(true);
    refresh();
  }

  async function refresh() {
    fetchJ<PlayerVal[]>("/draft/available?top=40").then(setAvailable).catch(() => {});
    fetchJ<Budget[]>("/draft/budgets").then(setBudgets).catch(() => {});
    fetchJ<Pick[]>("/draft/log").then(setLog).catch(() => {});
    fetchJ<Record<string, number>>("/draft/summary").then(setSummary).catch(() => {});
    fetchJ<Nomination[]>("/draft/nominate").then(setNominations).catch(() => {});
  }

  async function recordPick() {
    if (!pickPlayer || !pickTeam || !pickBid) return;
    const result = await fetchJ<Record<string, unknown>>("/draft/pick", {
      method: "POST",
      body: JSON.stringify({ player_name: pickPlayer, team: pickTeam, bid: parseFloat(pickBid) }),
    });
    setPickPlayer(""); setPickBid("");
    refresh();
  }

  async function checkBid() {
    if (!checkPlayer) return;
    const rec = await fetchJ<BidRec>(`/draft/recommend/${encodeURIComponent(checkPlayer)}`);
    setBidRec(rec);
  }

  const actionColors: Record<string, string> = {
    strong_bid: "bg-green-500/20 text-green-400 border-green-500/30",
    bid: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    pass: "bg-red-500/20 text-red-400 border-red-500/30",
    let_go: "bg-zinc-500/20 text-zinc-400 border-zinc-700",
  };

  const tierColors: Record<string, string> = {
    elite: "bg-purple-500/10 text-purple-400",
    starter: "bg-blue-500/10 text-blue-400",
    bench: "bg-zinc-500/10 text-zinc-400",
    replacement: "bg-zinc-800 text-zinc-600",
  };

  if (!initialized) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Draft Room</h1>
        <Card className="text-center py-12">
          <Gavel size={48} className="mx-auto text-zinc-600 mb-4" />
          <h2 className="text-xl font-bold mb-2">Auction Draft Assistant</h2>
          <p className="text-zinc-500 mb-6">Real-time bid recommendations, value tracking, and nomination strategy.</p>
          <button onClick={initDraft} className="px-6 py-3 bg-blue-600 text-white rounded-xl text-lg hover:bg-blue-500">
            Start Draft Session
          </button>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Draft Room</h1>
        <div className="flex gap-3 text-sm text-zinc-400">
          <span>Picks: {summary.picks_made || 0}</span>
          <span>Remaining: {summary.players_remaining || 0}</span>
          <span>Avg price: ${summary.avg_pick_price || 0}</span>
        </div>
      </div>

      {/* Top row: Record pick + Bid check */}
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardTitle>Record a Pick</CardTitle>
          <div className="flex gap-2">
            <div className="flex-1"><PlayerInput value={pickPlayer} onChange={setPickPlayer} placeholder="Player name" /></div>
            <input value={pickTeam} onChange={e => setPickTeam(e.target.value)} placeholder="Team" className="w-40 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500" />
            <input value={pickBid} onChange={e => setPickBid(e.target.value)} placeholder="$" className="w-20 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500" />
            <button onClick={recordPick} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500">Pick</button>
          </div>
        </Card>
        <Card>
          <CardTitle>Should I Bid?</CardTitle>
          <div className="flex gap-2">
            <div className="flex-1"><PlayerInput value={checkPlayer} onChange={setCheckPlayer} placeholder="Player name" onKeyDown={e => e.key === "Enter" && checkBid()} /></div>
            <button onClick={checkBid} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500">Check</button>
          </div>
          {bidRec && (
            <div className={`mt-3 p-3 rounded-lg border ${actionColors[bidRec.action] || ""}`}>
              <div className="flex items-center justify-between">
                <span className="font-bold text-lg">{bidRec.action.replace("_", " ").toUpperCase()}</span>
                <span className="text-sm">Fair: ${bidRec.fair_value} | Max: ${bidRec.max_bid}</span>
              </div>
              <p className="text-sm mt-1 opacity-80">{bidRec.reason}</p>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Nomination Strategy */}
        <Card>
          <CardTitle><Target size={14} className="inline mr-1" /> Nomination Strategy</CardTitle>
          <div className="space-y-2">
            {nominations.map((n, i) => (
              <div key={i} className="p-2 rounded-lg bg-zinc-900/50 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{n.player_name}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${n.strategy === "target" ? "bg-green-500/10 text-green-400" : n.strategy === "drive_price" ? "bg-red-500/10 text-red-400" : "bg-blue-500/10 text-blue-400"}`}>
                    {n.strategy.replace("_", " ")}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 mt-1">{n.reason.slice(0, 80)}</p>
              </div>
            ))}
          </div>
        </Card>

        {/* Team Budgets */}
        <Card>
          <CardTitle><DollarSign size={14} className="inline mr-1" /> Budgets</CardTitle>
          <div className="space-y-1.5 max-h-60 overflow-y-auto">
            {budgets.map(b => (
              <div key={b.team_name} className={`flex items-center justify-between text-xs p-1.5 rounded ${b.team_name === "He Who Remains" ? "bg-blue-500/5" : ""}`}>
                <span className="w-32 truncate">{b.team_name}</span>
                <div className="flex-1 mx-2 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-green-500 rounded-full" style={{ width: `${(b.remaining / 233) * 100}%` }} />
                </div>
                <span className="text-zinc-400 w-16 text-right">${b.remaining.toFixed(0)}</span>
                <span className="text-zinc-600 w-8 text-right">{b.players_drafted}p</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Recent Picks */}
        <Card>
          <CardTitle>Recent Picks</CardTitle>
          <div className="space-y-1.5 max-h-60 overflow-y-auto">
            {log.slice(0, 12).map((p, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="font-medium w-32 truncate">{p.player_name}</span>
                <span className="text-zinc-500 w-28 truncate">{p.team}</span>
                <span className="text-zinc-400">${p.bid}</span>
                <span className={`font-mono ${p.surplus > 2 ? "text-green-400" : p.surplus < -2 ? "text-red-400" : "text-zinc-500"}`}>
                  {p.surplus > 0 ? "+" : ""}{p.surplus.toFixed(0)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Available Players */}
      <Card>
        <CardTitle>Best Available Players</CardTitle>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                <th className="text-left py-2">#</th>
                <th className="text-left py-2">Player</th>
                <th className="text-left py-2">Team</th>
                <th className="text-left py-2">Pos</th>
                <th className="text-center py-2">Tier</th>
                <th className="text-right py-2">Fair $</th>
                <th className="text-right py-2">Z-Score</th>
              </tr>
            </thead>
            <tbody>
              {available.slice(0, 30).map((v, i) => (
                <tr key={v.name} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
                  <td className="py-1.5 text-zinc-500">{i + 1}</td>
                  <td className="py-1.5 font-medium">{v.name}</td>
                  <td className="py-1.5 text-zinc-400 text-xs">{v.nba_team}</td>
                  <td className="py-1.5 text-zinc-500 text-xs">{v.position}</td>
                  <td className="py-1.5 text-center"><span className={`text-[10px] px-1.5 py-0.5 rounded ${tierColors[v.tier] || ""}`}>{v.tier}</span></td>
                  <td className="py-1.5 text-right font-mono text-green-400">${v.fair_value.toFixed(0)}</td>
                  <td className={`py-1.5 text-right font-mono ${v.z_total > 3 ? "text-green-400" : "text-zinc-400"}`}>{v.z_total > 0 ? "+" : ""}{v.z_total.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
