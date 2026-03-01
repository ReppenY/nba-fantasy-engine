"use client";
import { useEffect, useState } from "react";
import { Card, CardTitle, StatBadge } from "@/components/Card";
import { ArrowRight } from "lucide-react";
import PlayerInput from "@/components/PlayerInput";
import PickSelector from "@/components/PickSelector";

const BASE = "http://localhost:8000";
const fetchJ = <T,>(url: string): Promise<T> => fetch(`${BASE}${url}`).then(r => r.json());

const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

type Tab = "suggestions" | "evaluate" | "simulator" | "profiles" | "history" | "expendables" | "matrix";

interface Suggestion { rank: number; give_players: string[]; receive_players: string[]; opponent: string; my_benefit: number; their_benefit: number; acceptance_likelihood: number; strategic_rationale: string; salary_impact: number; my_cat_changes: Record<string, number> }
interface Profile { team_id: string; team_name: string; archetype: string; strongest_cats: string[]; weakest_cats: string[]; total_z: number; total_salary: number; cap_room: number; avg_age: number; num_expiring: number; waiver_moves: number; num_trades: number; picks_traded_away: number; picks_acquired: number; trade_partners: string[]; core_players: string[]; expendable_players: string[]; buying_signal: number; trade_openness: number }
interface Grade { team_name: string; letter_grade: string; numeric_score: number; z_change: number; salary_change: number; players_out: string[]; players_in: string[]; picks_out: number; picks_in: number; rationale: string }
interface GradedTrade { date: string; period: number; teams: string[]; grades: Grade[]; winner: string; fairness: string }
interface Tradeable { name: string; team: string; salary: number; z_total: number; age: number; years_remaining: number; reasons: string[]; trade_block_score: number; best_fit_teams: string[] }
interface MatrixEntry { team_a: string; team_b: string; probability: number; complementary_score: number; common_ground: string[]; historical_trades: number }

export default function TradeIntelPage() {
  const [tab, setTab] = useState<Tab>("suggestions");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trade Center</h1>
      <div className="flex gap-2 flex-wrap">
        {([["suggestions", "Suggestions"], ["evaluate", "Evaluate"], ["simulator", "Simulator"], ["profiles", "Managers"], ["history", "History"], ["expendables", "Expendables"], ["matrix", "Matrix"]] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm rounded-lg border ${tab === t ? "border-blue-500 bg-blue-500/10 text-blue-400" : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === "suggestions" && <SuggestionsTab />}
      {tab === "evaluate" && <EvaluateTab />}
      {tab === "simulator" && <SimulatorTab />}
      {tab === "profiles" && <ProfilesTab />}
      {tab === "history" && <HistoryTab />}
      {tab === "expendables" && <ExpendablesTab />}
      {tab === "matrix" && <MatrixTab />}
    </div>
  );
}

function SuggestionsTab() {
  const [data, setData] = useState<Suggestion[]>([]);
  useEffect(() => { fetchJ<Suggestion[]>("/trade-intel/suggestions?top=15").then(setData).catch(() => {}); }, []);

  return (
    <Card>
      <CardTitle>Proactive Trade Recommendations</CardTitle>
      <p className="text-xs text-zinc-500 mb-4">Ranked by combined strategic value and acceptance likelihood.</p>
      <div className="space-y-3">
        {data.map(s => (
          <div key={s.rank} className="p-4 border border-zinc-800 rounded-lg hover:border-zinc-700">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-zinc-500">#{s.rank}</span>
              <div className="flex gap-3 items-center">
                <span className="text-xs">Acceptance: <span className={`font-bold ${s.acceptance_likelihood > 0.7 ? "text-green-400" : s.acceptance_likelihood > 0.4 ? "text-yellow-400" : "text-red-400"}`}>{(s.acceptance_likelihood * 100).toFixed(0)}%</span></span>
                <div className="w-24 h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${s.acceptance_likelihood > 0.7 ? "bg-green-500" : s.acceptance_likelihood > 0.4 ? "bg-yellow-500" : "bg-red-500"}`} style={{ width: `${s.acceptance_likelihood * 100}%` }} />
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className="text-red-300">Give: {s.give_players.join(", ")}</span>
              <ArrowRight size={14} className="text-zinc-600" />
              <span className="text-green-300">Get: {s.receive_players.join(", ")}</span>
              <span className="text-zinc-500">vs {s.opponent}</span>
            </div>
            <div className="flex gap-4 mt-2 text-xs text-zinc-500">
              <span>Your gain: <span className="text-green-400">{s.my_benefit.toFixed(1)}</span></span>
              <span>Their gain: <span className="text-blue-400">{s.their_benefit.toFixed(1)}</span></span>
              <span>Salary: {s.salary_impact > 0 ? "+" : ""}${s.salary_impact.toFixed(0)}</span>
            </div>
            <p className="text-xs text-zinc-400 mt-2">{s.strategic_rationale}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ProfilesTab() {
  const [data, setData] = useState<Profile[]>([]);
  const [selected, setSelected] = useState<Profile | null>(null);
  useEffect(() => { fetchJ<Profile[]>("/trade-intel/manager-profiles").then(setData).catch(() => {}); }, []);

  const archetypeColors: Record<string, string> = {
    contender: "bg-green-500/10 text-green-400",
    rebuilder: "bg-blue-500/10 text-blue-400",
    tinkerer: "bg-yellow-500/10 text-yellow-400",
    seller: "bg-red-500/10 text-red-400",
    buyer: "bg-purple-500/10 text-purple-400",
    passive: "bg-zinc-500/10 text-zinc-400",
  };

  return (
    <>
      <div className="grid grid-cols-3 gap-4">
        {data.map(p => (
          <Card key={p.team_id} className={`cursor-pointer hover:border-zinc-600 ${selected?.team_id === p.team_id ? "border-blue-500" : ""}`}>
            <div onClick={() => setSelected(p)}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-sm">{p.team_name}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded ${archetypeColors[p.archetype] || ""}`}>{p.archetype}</span>
              </div>
              <div className="text-xs text-zinc-400 space-y-1">
                <div>Z: <span className={p.total_z > 0 ? "text-green-400" : "text-red-400"}>{p.total_z > 0 ? "+" : ""}{p.total_z.toFixed(0)}</span> | Trades: {p.num_trades} | Picks: +{p.picks_acquired}/-{p.picks_traded_away}</div>
                <div>Strong: <span className="text-green-400">{p.strongest_cats.map(c => CAT_LABELS[c] || c).join(", ")}</span></div>
                <div>Weak: <span className="text-red-400">{p.weakest_cats.map(c => CAT_LABELS[c] || c).join(", ")}</span></div>
                <div>Openness: {(p.trade_openness * 100).toFixed(0)}%</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
      {selected && (
        <Card>
          <CardTitle>{selected.team_name} — Detail</CardTitle>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div><span className="text-zinc-500">Salary:</span> ${selected.total_salary.toFixed(0)} / $233 (room: ${selected.cap_room.toFixed(0)})</div>
            <div><span className="text-zinc-500">Avg Age:</span> {selected.avg_age.toFixed(1)}</div>
            <div><span className="text-zinc-500">Expiring:</span> {selected.num_expiring} players</div>
            <div><span className="text-zinc-500">Waiver Moves:</span> {selected.waiver_moves}</div>
            <div><span className="text-zinc-500">Trade Partners:</span> {selected.trade_partners.join(", ") || "None"}</div>
            <div><span className="text-zinc-500">Buying Signal:</span> <span className={selected.buying_signal > 0 ? "text-green-400" : "text-red-400"}>{selected.buying_signal > 0 ? "Buyer" : "Seller"} ({selected.buying_signal.toFixed(2)})</span></div>
          </div>
          <div className="mt-3">
            <span className="text-xs text-zinc-500">Core Players:</span>
            <span className="text-sm ml-2">{selected.core_players.join(", ") || "N/A"}</span>
          </div>
          <div className="mt-1">
            <span className="text-xs text-zinc-500">Expendable:</span>
            <span className="text-sm ml-2 text-yellow-400">{selected.expendable_players.join(", ") || "None"}</span>
          </div>
        </Card>
      )}
    </>
  );
}

function HistoryTab() {
  const [data, setData] = useState<GradedTrade[]>([]);
  useEffect(() => { fetchJ<GradedTrade[]>("/trade-intel/graded-trades").then(setData).catch(() => {}); }, []);

  const gradeColors: Record<string, string> = {
    "A+": "text-green-400", "A": "text-green-400", "A-": "text-green-300",
    "B+": "text-blue-400", "B": "text-blue-400", "B-": "text-blue-300",
    "C+": "text-yellow-400", "C": "text-yellow-400", "C-": "text-yellow-300",
    "D": "text-red-400", "F": "text-red-500",
  };

  const fairColors: Record<string, string> = {
    fair: "bg-green-500/10 text-green-400",
    lopsided: "bg-yellow-500/10 text-yellow-400",
    robbery: "bg-red-500/10 text-red-400",
  };

  return (
    <div className="space-y-4">
      {data.map((t, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="text-sm font-medium">{t.date}</span>
              <span className="text-xs text-zinc-500 ml-2">Period {t.period}</span>
            </div>
            <div className="flex gap-2 items-center">
              <span className={`text-[10px] px-2 py-0.5 rounded ${fairColors[t.fairness] || ""}`}>{t.fairness.toUpperCase()}</span>
              {t.winner !== "Even" && <span className="text-xs text-zinc-400">Winner: <span className="text-green-400">{t.winner}</span></span>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {t.grades.map(g => (
              <div key={g.team_name} className="p-3 bg-zinc-900/50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">{g.team_name}</span>
                  <span className={`text-xl font-bold ${gradeColors[g.letter_grade] || "text-zinc-400"}`}>{g.letter_grade}</span>
                </div>
                <div className="text-xs space-y-1 text-zinc-400">
                  {g.players_out.length > 0 && <div>Out: <span className="text-red-300">{g.players_out.join(", ")}</span></div>}
                  {g.players_in.length > 0 && <div>In: <span className="text-green-300">{g.players_in.join(", ")}</span></div>}
                  {(g.picks_in > 0 || g.picks_out > 0) && <div>Picks: +{g.picks_in} / -{g.picks_out}</div>}
                  <div>Z-change: <span className={g.z_change > 0 ? "text-green-400" : "text-red-400"}>{g.z_change > 0 ? "+" : ""}{g.z_change.toFixed(1)}</span></div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function ExpendablesTab() {
  const [data, setData] = useState<Tradeable[]>([]);
  useEffect(() => { fetchJ<Tradeable[]>("/trade-intel/tradeable-players").then(setData).catch(() => {}); }, []);

  return (
    <Card>
      <CardTitle>Players Likely on the Trade Block</CardTitle>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
            <th className="text-left py-2">Player</th>
            <th className="text-left py-2">Team</th>
            <th className="text-right py-2">$</th>
            <th className="text-right py-2">Z</th>
            <th className="text-right py-2">Age</th>
            <th className="text-right py-2">Score</th>
            <th className="text-left py-2 pl-3">Reasons</th>
            <th className="text-left py-2">Best Fit</th>
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 30).map(p => (
            <tr key={`${p.name}-${p.team}`} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
              <td className="py-2 font-medium">{p.name}</td>
              <td className="py-2 text-zinc-400 text-xs">{p.team}</td>
              <td className="py-2 text-right text-zinc-400">${p.salary}</td>
              <td className={`py-2 text-right font-mono ${p.z_total > 0 ? "text-green-400" : "text-red-400"}`}>{p.z_total > 0 ? "+" : ""}{p.z_total.toFixed(1)}</td>
              <td className="py-2 text-right text-zinc-400">{p.age || "-"}</td>
              <td className="py-2 text-right font-mono text-yellow-400">{p.trade_block_score.toFixed(1)}</td>
              <td className="py-2 pl-3 text-xs text-zinc-500">{p.reasons.join(", ").replace(/_/g, " ")}</td>
              <td className="py-2 text-xs text-blue-400">{p.best_fit_teams.slice(0, 2).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function MatrixTab() {
  const [data, setData] = useState<MatrixEntry[]>([]);
  useEffect(() => { fetchJ<MatrixEntry[]>("/trade-intel/trade-matrix?top=30").then(setData).catch(() => {}); }, []);

  return (
    <Card>
      <CardTitle>Trade Probability Matrix — Most Likely Trade Partners</CardTitle>
      <div className="space-y-2">
        {data.map((m, i) => (
          <div key={i} className="flex items-center gap-3 p-3 border border-zinc-800 rounded-lg">
            <span className="text-zinc-500 text-xs w-6">#{i + 1}</span>
            <span className="text-sm font-medium w-40">{m.team_a}</span>
            <ArrowRight size={14} className="text-zinc-600" />
            <span className="text-sm font-medium w-40">{m.team_b}</span>
            <div className="flex-1">
              <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${m.probability * 100}%` }} />
              </div>
            </div>
            <span className="text-xs font-mono text-blue-400 w-12">{(m.probability * 100).toFixed(0)}%</span>
            {m.historical_trades > 0 && <span className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-400 rounded">{m.historical_trades} past</span>}
          </div>
        ))}
      </div>
    </Card>
  );
}

function EvaluateTab() {
  const [giveInput, setGiveInput] = useState("");
  const [receiveInput, setReceiveInput] = useState("");
  const [givePicks, setGivePicks] = useState<string[]>([]);
  const [receivePicks, setReceivePicks] = useState<string[]>([]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function evaluate() {
    const give = giveInput.split(",").map(s => s.trim()).filter(Boolean);
    const receive = receiveInput.split(",").map(s => s.trim()).filter(Boolean);
    if (!give.length && !givePicks.length) { setError("Enter at least one player or pick to give"); return; }
    if (!receive.length && !receivePicks.length) { setError("Enter at least one player or pick to receive"); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const body: Record<string, unknown> = { give, receive };
      if (givePicks.length) body.give_picks = givePicks;
      if (receivePicks.length) body.receive_picks = receivePicks;
      const r = await fetch(`${BASE}/trades/evaluate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await r.text());
      setResult(await r.json());
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }

  const verdictColors: Record<string, string> = {
    strong_accept: "bg-green-500/20 text-green-400", accept: "bg-green-500/20 text-green-400",
    slight_accept: "bg-green-500/10 text-green-300", slight_decline: "bg-red-500/10 text-red-300",
    decline: "bg-red-500/20 text-red-400", strong_decline: "bg-red-500/20 text-red-400",
  };

  return (
    <Card>
      <CardTitle>Evaluate a Trade</CardTitle>
      <div className="space-y-3">
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">You give — players (your roster)</label>
            <PlayerInput value={giveInput} onChange={setGiveInput} placeholder="LeBron James, Kyle Kuzma" pool="my" />
          </div>
          <ArrowRight size={20} className="text-zinc-500 mb-2" />
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">You receive — players (other teams)</label>
            <PlayerInput value={receiveInput} onChange={setReceiveInput} placeholder="Luka Doncic, Jrue Holiday" pool="other" />
          </div>
        </div>
        <div className="flex gap-4 items-start">
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">You give — picks (optional)</label>
            <PickSelector selected={givePicks} onChange={setGivePicks} pool="my" placeholder="Click to add your picks..." />
          </div>
          <div className="w-5" />
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">You receive — picks (optional)</label>
            <PickSelector selected={receivePicks} onChange={setReceivePicks} pool="other" placeholder="Click to add their picks..." />
          </div>
        </div>
        <button onClick={evaluate} disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50">
          {loading ? "..." : "Evaluate Trade"}
        </button>
      </div>
      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
      {result && (
        <div className="mt-4">
          <div className={`inline-block px-3 py-1.5 rounded-lg text-sm font-bold ${verdictColors[result.verdict as string] || "bg-zinc-800 text-zinc-400"}`}>
            {(result.verdict as string || "").replace(/_/g, " ").toUpperCase()} (score: {(result.combined_score as number || 0).toFixed(1)})
          </div>
          <pre className="mt-3 text-xs text-zinc-400 whitespace-pre-wrap">{result.explanation as string}</pre>
        </div>
      )}
    </Card>
  );
}

function SimulatorTab() {
  const [playerName, setPlayerName] = useState("");
  const [mode, setMode] = useState<"acquire" | "sell">("acquire");
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(false);

  async function search() {
    if (!playerName.trim()) return;
    setLoading(true); setResults([]);
    try {
      const r = await fetch(`${BASE}/offseason/trade-simulator`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_name: playerName, mode }),
      });
      setResults(await r.json());
    } catch {}
    finally { setLoading(false); }
  }

  return (
    <>
      <Card>
        <CardTitle>Trade Simulator</CardTitle>
        <p className="text-xs text-zinc-500 mb-3">Search for a player to acquire or sell across all 12 teams.</p>
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <PlayerInput value={playerName} onChange={setPlayerName} placeholder="e.g. Jrue Holiday"
              onKeyDown={e => e.key === "Enter" && search()} pool={mode === "acquire" ? "other" : "my"} />
          </div>
          <div className="flex rounded-lg border border-zinc-700 overflow-hidden">
            {(["acquire", "sell"] as const).map(m => (
              <button key={m} onClick={() => setMode(m)}
                className={`px-3 py-2 text-sm ${mode === m ? "bg-blue-600 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}>
                {m === "acquire" ? "Get" : "Sell"}
              </button>
            ))}
          </div>
          <button onClick={search} disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50">
            {loading ? "..." : "Find"}
          </button>
        </div>
      </Card>
      {results.length > 0 && (
        <Card>
          <CardTitle>Packages ({results.length})</CardTitle>
          <div className="space-y-2">
            {results.map((p, i) => (
              <div key={i} className="p-3 border border-zinc-800 rounded-lg flex items-center gap-3 text-sm">
                <span className="text-zinc-500">#{i + 1}</span>
                <span className="text-red-300">Give: {(p.i_give as string[]).join(", ")}</span>
                <ArrowRight size={14} className="text-zinc-600" />
                <span className="text-green-300">Get: {(p.i_receive as string[]).join(", ")}</span>
                <span className="text-xs text-zinc-500 ml-auto">{p.opponent_team as string}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
