"use client";
import { useEffect, useState } from "react";
import { api, LineupResponse } from "@/lib/api";
import { Card, CardTitle, StatBadge } from "@/components/Card";

const CATS = ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "tov"];
const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

type Tab = "lineup" | "matchup" | "schedule" | "scouting";

interface CatMatchup { category: string; my_z: number; opp_z: number; diff: number; win_prob: number; recommendation: string }
interface MatchupPred { period: number; opponent_name: string; expected_wins: number; win_probability: number; target_cats: string[]; concede_cats: string[]; swing_cats: string[]; my_total_z: number; opp_total_z: number; categories: CatMatchup[] }
interface ScheduleEntry { period: number; opponent_name: string; opponent_id: string; home_away: string }
interface Scout { team_name: string; team_id: string; period: number | null; team_total_z: number; strategy: string; target_cats: string[]; concede_cats: string[]; swing_cats: string[]; my_advantages: number; my_disadvantages: number; categories: CatMatchup[] }

const BASE = "http://localhost:8000";
const fetchJ = <T,>(url: string): Promise<T> => fetch(`${BASE}${url}`).then(r => r.json());

export default function LineupPage() {
  const [tab, setTab] = useState<Tab>("matchup");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Matchups & Lineup</h1>
      <div className="flex gap-2">
        {([["matchup", "Current Matchup"], ["scouting", "Scout All Teams"], ["lineup", "Lineup Optimizer"], ["schedule", "Schedule"]] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm rounded-lg border ${tab === t ? "border-blue-500 bg-blue-500/10 text-blue-400" : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === "matchup" && <MatchupTab />}
      {tab === "scouting" && <ScoutingTab />}
      {tab === "lineup" && <LineupTab />}
      {tab === "schedule" && <ScheduleTab />}
    </div>
  );
}

function MatchupTab() {
  const [pred, setPred] = useState<MatchupPred | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetchJ<MatchupPred>("/matchups/current").then(setPred).catch(e => setError(e.message || "Load full league mode"));
  }, []);

  if (error) return <Card><p className="text-zinc-500 text-sm">{error}. Start with FANTASY_FULL=1 to enable matchup predictions.</p></Card>;
  if (!pred) return <div className="text-zinc-500">Loading...</div>;

  return (
    <>
      <div className="grid grid-cols-4 gap-4">
        <StatBadge label="Opponent" value={pred.opponent_name} color="blue" />
        <StatBadge label="Expected Cats Won" value={`${pred.expected_wins} / 9`} color={pred.expected_wins >= 5 ? "green" : "red"} />
        <StatBadge label="Win Probability" value={`${(pred.win_probability * 100).toFixed(0)}%`} color={pred.win_probability > 0.5 ? "green" : "red"} />
        <StatBadge label="Period" value={pred.period} color="zinc" />
      </div>
      <Card>
        <CardTitle>Category Breakdown vs {pred.opponent_name}</CardTitle>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 text-xs border-b border-zinc-800">
              <th className="text-left py-2">Category</th>
              <th className="text-right py-2">My Z</th>
              <th className="text-right py-2">Opp Z</th>
              <th className="text-right py-2">Diff</th>
              <th className="text-right py-2">Win %</th>
              <th className="text-center py-2">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {pred.categories.map(c => {
              const color = c.recommendation === "target" ? "text-green-400" : c.recommendation === "concede" ? "text-red-400" : "text-yellow-400";
              const bg = c.recommendation === "target" ? "bg-green-500/10" : c.recommendation === "concede" ? "bg-red-500/10" : "bg-yellow-500/10";
              return (
                <tr key={c.category} className="border-b border-zinc-800/50">
                  <td className="py-2 font-medium">{CAT_LABELS[c.category] || c.category}</td>
                  <td className="py-2 text-right font-mono text-zinc-300">{c.my_z > 0 ? "+" : ""}{c.my_z.toFixed(1)}</td>
                  <td className="py-2 text-right font-mono text-zinc-400">{c.opp_z > 0 ? "+" : ""}{c.opp_z.toFixed(1)}</td>
                  <td className={`py-2 text-right font-mono ${c.diff > 0 ? "text-green-400" : "text-red-400"}`}>{c.diff > 0 ? "+" : ""}{c.diff.toFixed(1)}</td>
                  <td className={`py-2 text-right font-mono ${c.win_prob > 0.6 ? "text-green-400" : c.win_prob < 0.4 ? "text-red-400" : "text-yellow-400"}`}>{(c.win_prob * 100).toFixed(0)}%</td>
                  <td className="py-2 text-center">
                    <span className={`text-[10px] px-2 py-0.5 rounded ${bg} ${color}`}>{c.recommendation.toUpperCase()}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardTitle>Target (likely wins)</CardTitle>
          <div className="flex flex-wrap gap-2">
            {pred.target_cats.map(c => <span key={c} className="px-2 py-1 bg-green-500/10 text-green-400 rounded text-sm">{CAT_LABELS[c] || c}</span>)}
            {pred.target_cats.length === 0 && <span className="text-zinc-500 text-sm">None</span>}
          </div>
        </Card>
        <Card>
          <CardTitle>Swing (toss-up)</CardTitle>
          <div className="flex flex-wrap gap-2">
            {pred.swing_cats.map(c => <span key={c} className="px-2 py-1 bg-yellow-500/10 text-yellow-400 rounded text-sm">{CAT_LABELS[c] || c}</span>)}
          </div>
        </Card>
        <Card>
          <CardTitle>Concede (likely losses)</CardTitle>
          <div className="flex flex-wrap gap-2">
            {pred.concede_cats.map(c => <span key={c} className="px-2 py-1 bg-red-500/10 text-red-400 rounded text-sm">{CAT_LABELS[c] || c}</span>)}
          </div>
        </Card>
      </div>
    </>
  );
}

function ScoutingTab() {
  const [scouts, setScouts] = useState<Scout[]>([]);
  const [selected, setSelected] = useState<Scout | null>(null);
  useEffect(() => { fetchJ<Scout[]>("/matchups/scout").then(setScouts).catch(() => {}); }, []);

  return (
    <>
      <Card>
        <CardTitle>Opponent Scouting — Category Focus Analysis</CardTitle>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 text-xs border-b border-zinc-800">
              <th className="text-left py-2">Team</th>
              <th className="text-right py-2">Total Z</th>
              <th className="text-center py-2">Adv</th>
              <th className="text-center py-2">Disadv</th>
              <th className="text-left py-2 pl-3">Target</th>
              <th className="text-left py-2">Concede</th>
              <th className="text-left py-2">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {scouts.map(s => (
              <tr key={s.team_id} className="border-b border-zinc-800/50 hover:bg-white/[0.02] cursor-pointer" onClick={() => setSelected(s)}>
                <td className="py-2 font-medium">{s.team_name} {s.period ? <span className="text-xs text-zinc-500">(P{s.period})</span> : ""}</td>
                <td className={`py-2 text-right font-mono ${s.team_total_z > 0 ? "text-green-400" : "text-red-400"}`}>{s.team_total_z > 0 ? "+" : ""}{s.team_total_z.toFixed(0)}</td>
                <td className="py-2 text-center text-green-400">{s.my_advantages}</td>
                <td className="py-2 text-center text-red-400">{s.my_disadvantages}</td>
                <td className="py-2 pl-3 text-xs text-green-400">{s.target_cats.map(c => CAT_LABELS[c] || c).join(", ")}</td>
                <td className="py-2 text-xs text-red-400">{s.concede_cats.map(c => CAT_LABELS[c] || c).join(", ")}</td>
                <td className="py-2 text-xs text-zinc-500">{s.strategy.slice(0, 50)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {selected && (
        <Card>
          <CardTitle>Detail: vs {selected.team_name}</CardTitle>
          <p className="text-sm text-zinc-400 mb-3">{selected.strategy}</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                <th className="text-left py-2">Cat</th>
                <th className="text-right py-2">My Z</th>
                <th className="text-right py-2">Their Z</th>
                <th className="text-right py-2">Diff</th>
                <th className="text-right py-2">Win %</th>
                <th className="text-center py-2">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {selected.categories.map(c => (
                <tr key={c.category} className="border-b border-zinc-800/50">
                  <td className="py-2">{CAT_LABELS[c.category] || c.category}</td>
                  <td className="py-2 text-right font-mono">{c.my_z > 0 ? "+" : ""}{c.my_z.toFixed(1)}</td>
                  <td className="py-2 text-right font-mono text-zinc-400">{c.opp_z > 0 ? "+" : ""}{c.opp_z.toFixed(1)}</td>
                  <td className={`py-2 text-right font-mono ${c.diff > 0 ? "text-green-400" : "text-red-400"}`}>{c.diff > 0 ? "+" : ""}{c.diff.toFixed(1)}</td>
                  <td className={`py-2 text-right ${c.win_prob > 0.6 ? "text-green-400" : c.win_prob < 0.4 ? "text-red-400" : "text-yellow-400"}`}>{(c.win_prob * 100).toFixed(0)}%</td>
                  <td className="py-2 text-center">
                    <span className={`text-[10px] px-2 py-0.5 rounded ${
                      c.recommendation === "target" ? "bg-green-500/10 text-green-400" : c.recommendation === "concede" ? "bg-red-500/10 text-red-400" : "bg-yellow-500/10 text-yellow-400"
                    }`}>{c.recommendation.toUpperCase()}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

function LineupTab() {
  const [lineup, setLineup] = useState<LineupResponse | null>(null);
  const [puntInput, setPuntInput] = useState("");
  useEffect(() => { load(); }, []);
  function load() { api.getLineup(puntInput).then(setLineup).catch(() => {}); }

  return lineup ? (
    <>
      <div className="flex gap-2 items-center mb-4">
        <input value={puntInput} onChange={(e) => setPuntInput(e.target.value)} placeholder="Punt cats (e.g. ft_pct,tov)"
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm w-56 outline-none focus:border-blue-500" />
        <button onClick={load} className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-500">Optimize</button>
      </div>
      <Card>
        <CardTitle>Optimal Lineup</CardTitle>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 text-xs border-b border-zinc-800">
              <th className="text-left py-2 w-16">Slot</th>
              <th className="text-left py-2">Player</th>
              <th className="text-left py-2">Positions</th>
              <th className="text-right py-2">Games</th>
              <th className="text-right py-2">Weekly Z</th>
            </tr>
          </thead>
          <tbody>
            {lineup.active.map((s, i) => (
              <tr key={i} className="border-b border-zinc-800/50">
                <td className="py-2 text-blue-400 font-bold">{s.slot}</td>
                <td className="py-2 font-medium">{s.player_name}</td>
                <td className="py-2 text-zinc-500 text-xs">{s.positions}</td>
                <td className="py-2 text-right text-zinc-400">{s.games_this_week}</td>
                <td className={`py-2 text-right font-mono font-bold ${s.weekly_z > 0 ? "text-green-400" : "text-red-400"}`}>{s.weekly_z > 0 ? "+" : ""}{s.weekly_z.toFixed(1)}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-zinc-700"><td colSpan={4} className="py-2 font-bold text-right">Total</td>
              <td className="py-2 text-right font-bold font-mono text-green-400">+{lineup.total_weekly_z.toFixed(1)}</td></tr>
          </tbody>
        </table>
      </Card>
      <Card>
        <CardTitle>Bench ({lineup.bench.length})</CardTitle>
        <div className="text-sm text-zinc-500 flex flex-wrap gap-2">{lineup.bench.map(n => <span key={n} className="px-2 py-1 bg-zinc-800 rounded">{n}</span>)}</div>
      </Card>
    </>
  ) : <div className="text-zinc-500">Loading...</div>;
}

function ScheduleTab() {
  const [schedule, setSchedule] = useState<ScheduleEntry[]>([]);
  useEffect(() => { fetchJ<ScheduleEntry[]>("/matchups/schedule").then(setSchedule).catch(() => {}); }, []);

  return (
    <Card>
      <CardTitle>Your Season Schedule</CardTitle>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
            <th className="text-left py-2">Period</th>
            <th className="text-left py-2">Opponent</th>
            <th className="text-center py-2">Home/Away</th>
          </tr>
        </thead>
        <tbody>
          {schedule.map(s => (
            <tr key={s.period} className="border-b border-zinc-800/50">
              <td className="py-2 font-mono">Period {s.period}</td>
              <td className="py-2 font-medium">{s.opponent_name}</td>
              <td className="py-2 text-center text-zinc-400">{s.home_away === "home" ? "HOME" : "AWAY"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
