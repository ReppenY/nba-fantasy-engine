"use client";
import { useEffect, useState } from "react";
import { api, TeamSummary, FreeAgent } from "@/lib/api";
import { Card, CardTitle } from "@/components/Card";

const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

export default function LeaguePage() {
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [freeAgents, setFreeAgents] = useState<FreeAgent[]>([]);

  useEffect(() => {
    api.getLeagueTeams().then(setTeams).catch(() => {});
    api.getFreeAgents(20).then(setFreeAgents).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">League Overview</h1>

      {teams.length === 0 ? (
        <Card><p className="text-zinc-500 text-sm">Load full league mode (FANTASY_FULL=1) to see all teams.</p></Card>
      ) : (
        <Card>
          <CardTitle>Team Rankings</CardTitle>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                <th className="text-left py-2 px-2">#</th>
                <th className="text-left py-2">Team</th>
                <th className="text-right py-2">Players</th>
                <th className="text-right py-2">Total Z</th>
                <th className="text-left py-2 pl-4">Strongest</th>
                <th className="text-left py-2">Weakest</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((t, i) => (
                <tr key={t.team_id} className={`border-b border-zinc-800/50 ${t.name === "He Who Remains" ? "bg-blue-500/5" : "hover:bg-white/[0.02]"}`}>
                  <td className="py-2 px-2 text-zinc-500">{i + 1}</td>
                  <td className="py-2 font-medium">
                    {t.name}
                    {t.name === "He Who Remains" && <span className="ml-2 text-xs text-blue-400">(you)</span>}
                  </td>
                  <td className="py-2 text-right text-zinc-400">{t.player_count}</td>
                  <td className={`py-2 text-right font-mono font-bold ${t.total_z > 0 ? "text-green-400" : "text-red-400"}`}>
                    {t.total_z > 0 ? "+" : ""}{t.total_z.toFixed(1)}
                  </td>
                  <td className="py-2 pl-4 text-green-400 text-xs">{t.strongest.map(c => CAT_LABELS[c] || c).join(", ")}</td>
                  <td className="py-2 text-red-400 text-xs">{t.weakest.map(c => CAT_LABELS[c] || c).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {freeAgents.length > 0 && (
        <Card>
          <CardTitle>Top Free Agents</CardTitle>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                <th className="text-left py-2 px-2">#</th>
                <th className="text-left py-2">Player</th>
                <th className="text-left py-2">Team</th>
                <th className="text-right py-2">Z-Score</th>
                <th className="text-right py-2">PTS</th>
                <th className="text-right py-2">REB</th>
                <th className="text-right py-2">AST</th>
                <th className="text-right py-2">GP</th>
              </tr>
            </thead>
            <tbody>
              {freeAgents.map((fa, i) => (
                <tr key={fa.name} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
                  <td className="py-2 px-2 text-zinc-500">{i + 1}</td>
                  <td className="py-2 font-medium">{fa.name}</td>
                  <td className="py-2 text-zinc-400">{fa.nba_team}</td>
                  <td className={`py-2 text-right font-mono ${fa.z_total > 2 ? "text-green-400" : "text-zinc-400"}`}>
                    {fa.z_total > 0 ? "+" : ""}{fa.z_total.toFixed(1)}
                  </td>
                  <td className="py-2 text-right text-zinc-400">{fa.pts}</td>
                  <td className="py-2 text-right text-zinc-400">{fa.reb}</td>
                  <td className="py-2 text-right text-zinc-400">{fa.ast}</td>
                  <td className="py-2 text-right text-zinc-500">{fa.games_played}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
