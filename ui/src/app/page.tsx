"use client";
import { useEffect, useState } from "react";
import { api, TeamProfile, Alert, PlayerZScores, Injury } from "@/lib/api";
import { Card, CardTitle, StatBadge } from "@/components/Card";
import { AlertTriangle, HeartPulse } from "lucide-react";

const CATS = ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "tov"];
const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

export default function Dashboard() {
  const [profile, setProfile] = useState<TeamProfile | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [topPlayers, setTopPlayers] = useState<PlayerZScores[]>([]);
  const [injuries, setInjuries] = useState<Injury[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.getTeamProfile().then(setProfile).catch(() => {}),
      api.getAlerts().then(setAlerts).catch(() => setAlerts([])),
      api.getRankings(10).then(setTopPlayers).catch(() => {}),
      api.getInjuries().then(setInjuries).catch(() => setInjuries([])),
    ]).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Card className="max-w-md text-center">
          <p className="text-red-400 mb-2">Could not connect to the API</p>
          <p className="text-sm text-zinc-500">Make sure the backend is running:</p>
          <code className="text-xs text-blue-400 block mt-2">
            cd ~/nba-fantasy-engine && source .venv/bin/activate && uvicorn fantasy_engine.api.app:app --reload
          </code>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {profile && (
        <div className="grid grid-cols-4 gap-4">
          <StatBadge label="Total Z-Score" value={profile.total_z.toFixed(1)} color={profile.total_z > 0 ? "green" : "red"} />
          <StatBadge label="Strongest" value={profile.strongest_cats.map(c => CAT_LABELS[c] || c).join(", ")} color="green" />
          <StatBadge label="Weakest" value={profile.weakest_cats.map(c => CAT_LABELS[c] || c).join(", ")} color="red" />
          <StatBadge label="Suggested Punt" value={profile.suggested_punts.length > 0 ? profile.suggested_punts.map(c => CAT_LABELS[c] || c).join(", ") : "None"} color="yellow" />
        </div>
      )}

      {/* Injuries */}
      {injuries.length > 0 && (
        <Card>
          <CardTitle>
            <span className="flex items-center gap-2"><HeartPulse size={14} className="text-red-400" /> Roster Injuries ({injuries.length})</span>
          </CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                  <th className="text-left py-1.5">Player</th>
                  <th className="text-left py-1.5">Team</th>
                  <th className="text-left py-1.5">Status</th>
                  <th className="text-left py-1.5">Return</th>
                  <th className="text-right py-1.5">Days</th>
                  <th className="text-left py-1.5 pl-3">Injury</th>
                </tr>
              </thead>
              <tbody>
                {injuries.map((inj) => (
                  <tr key={inj.player} className="border-b border-zinc-800/50">
                    <td className="py-1.5 font-medium">{inj.player}</td>
                    <td className="py-1.5 text-zinc-400 text-xs">{inj.team}</td>
                    <td className="py-1.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        inj.status === "Out" ? "bg-red-500/10 text-red-400" :
                        inj.status === "Day-To-Day" ? "bg-yellow-500/10 text-yellow-400" :
                        "bg-zinc-500/10 text-zinc-400"}`}>
                        {inj.status}
                      </span>
                    </td>
                    <td className="py-1.5 text-zinc-400 text-xs">{inj.return_date}</td>
                    <td className={`py-1.5 text-right text-xs font-mono ${
                      inj.days_until_return !== null && inj.days_until_return > 30 ? "text-red-400" :
                      inj.days_until_return !== null && inj.days_until_return > 7 ? "text-yellow-400" :
                      "text-green-400"
                    }`}>
                      {inj.days_until_return !== null ? inj.days_until_return : "?"}
                    </td>
                    <td className="py-1.5 pl-3 text-xs text-zinc-500 max-w-xs truncate">{inj.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-3 gap-6">
        {profile && (
          <Card className="col-span-2">
            <CardTitle>Category Profile</CardTitle>
            <div className="space-y-2.5">
              {CATS.map((cat) => {
                const c = profile.categories[cat];
                if (!c) return null;
                const pct = Math.min(100, Math.max(3, ((c.z_sum + 10) / 20) * 100));
                return (
                  <div key={cat} className="flex items-center gap-3">
                    <span className="w-10 text-xs text-zinc-400 text-right font-mono">{CAT_LABELS[cat]}</span>
                    <div className="flex-1 h-5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${c.strength === "strong" ? "bg-green-500" : c.strength === "weak" ? "bg-red-500" : "bg-blue-500"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className={`w-12 text-xs font-mono text-right ${c.z_sum > 0 ? "text-green-400" : c.z_sum < -1 ? "text-red-400" : "text-zinc-500"}`}>
                      {c.z_sum > 0 ? "+" : ""}{c.z_sum.toFixed(1)}
                    </span>
                    <span className={`text-[10px] w-16 text-center px-1.5 py-0.5 rounded ${
                      c.strength === "strong" ? "bg-green-500/10 text-green-400" : c.strength === "weak" ? "bg-red-500/10 text-red-400" : "bg-zinc-500/10 text-zinc-400"}`}>
                      {c.strength}
                    </span>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        <Card>
          <CardTitle>Alerts</CardTitle>
          {alerts.length === 0 ? (
            <p className="text-zinc-500 text-sm">No alerts</p>
          ) : (
            <div className="space-y-2.5 max-h-80 overflow-y-auto">
              {alerts.slice(0, 8).map((alert, i) => (
                <div key={i} className={`text-sm p-2.5 rounded-lg border ${
                  alert.priority === "high" ? "border-red-500/30 bg-red-500/5" :
                  alert.priority === "medium" ? "border-yellow-500/30 bg-yellow-500/5" : "border-zinc-700 bg-zinc-800/30"}`}>
                  <div className="font-medium text-zinc-200 flex items-center gap-1.5">
                    {alert.priority === "high" && <AlertTriangle size={13} className="text-red-400" />}
                    {alert.title}
                  </div>
                  {alert.action && <div className="text-xs text-blue-400 mt-1">{alert.action}</div>}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {topPlayers.length > 0 && (
        <Card>
          <CardTitle>Top Players</CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                  <th className="text-left py-2 px-2">#</th>
                  <th className="text-left py-2">Player</th>
                  <th className="text-left py-2">Team</th>
                  <th className="text-right py-2">$</th>
                  {CATS.map((c) => <th key={c} className="text-right py-2 px-1">{CAT_LABELS[c]}</th>)}
                  <th className="text-right py-2 px-2 font-bold">TOTAL</th>
                </tr>
              </thead>
              <tbody>
                {topPlayers.map((p, i) => (
                  <tr key={p.name} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
                    <td className="py-2 px-2 text-zinc-500">{i + 1}</td>
                    <td className="py-2 font-medium">{p.name}</td>
                    <td className="py-2 text-zinc-400">{p.nba_team}</td>
                    <td className="py-2 text-right text-zinc-400">${p.salary}</td>
                    {CATS.map((cat) => {
                      const val = (p as unknown as Record<string, number>)[`z_${cat}`] || 0;
                      return (
                        <td key={cat} className={`py-2 px-1 text-right font-mono text-xs ${val > 1 ? "text-green-400" : val < -1 ? "text-red-400" : "text-zinc-500"}`}>
                          {val > 0 ? "+" : ""}{val.toFixed(1)}
                        </td>
                      );
                    })}
                    <td className={`py-2 px-2 text-right font-bold font-mono ${p.z_total > 0 ? "text-green-400" : "text-red-400"}`}>
                      {p.z_total > 0 ? "+" : ""}{p.z_total.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
