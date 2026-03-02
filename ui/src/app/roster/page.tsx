"use client";
import { useEffect, useState } from "react";
import { api, PlayerZScores } from "@/lib/api";
import { Card, CardTitle } from "@/components/Card";

const CATS = ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "tov"];
const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

export default function RosterPage() {
  const [roster, setRoster] = useState<PlayerZScores[]>([]);
  const [filter, setFilter] = useState("");
  const [sortCol, setSortCol] = useState("z_total");
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    api.getRoster(filter).then(setRoster).catch(() => {});
  }, [filter]);

  const sorted = [...roster].sort((a, b) => {
    const av = (a as unknown as Record<string, number>)[sortCol] || 0;
    const bv = (b as unknown as Record<string, number>)[sortCol] || 0;
    return sortAsc ? av - bv : bv - av;
  });

  function toggleSort(col: string) {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(false); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Roster</h1>
        <div className="flex gap-2">
          {[
            { label: "All", value: "" },
            { label: "Active", value: "Act" },
            { label: "Reserve", value: "Res" },
          ].map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-sm rounded-lg border ${
                filter === f.value ? "border-blue-500 bg-blue-500/10 text-blue-400" : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                <th className="text-left py-2 px-2">#</th>
                <th className="text-left py-2 cursor-pointer hover:text-zinc-300" onClick={() => toggleSort("name")}>Player</th>
                <th className="text-left py-2">Team</th>
                <th className="text-left py-2">Pos</th>
                <th className="text-center py-2">Status</th>
                <th className="text-right py-2 cursor-pointer hover:text-zinc-300" onClick={() => toggleSort("salary")}>$</th>
                <th className="text-right py-2">GP</th>
                {CATS.map((c) => (
                  <th key={c} className="text-right py-2 px-1 cursor-pointer hover:text-zinc-300" onClick={() => toggleSort(`z_${c}`)}>
                    {CAT_LABELS[c]}{sortCol === `z_${c}` ? (sortAsc ? " ^" : " v") : ""}
                  </th>
                ))}
                <th className="text-right py-2 px-2 cursor-pointer hover:text-zinc-300 font-bold" onClick={() => toggleSort("z_total")}>
                  TOTAL{sortCol === "z_total" ? (sortAsc ? " ^" : " v") : ""}
                </th>
                <th className="text-right py-2 px-2 cursor-pointer hover:text-zinc-300" onClick={() => toggleSort("pos_scarcity_bonus")}>
                  Pos+{sortCol === "pos_scarcity_bonus" ? (sortAsc ? " ^" : " v") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p, i) => (
                <tr key={p.name} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
                  <td className="py-2 px-2 text-zinc-600">{i + 1}</td>
                  <td className="py-2 font-medium">{p.name}</td>
                  <td className="py-2 text-zinc-400 text-xs">{p.nba_team}</td>
                  <td className="py-2 text-zinc-500 text-xs">{p.positions}</td>
                  <td className="py-2 text-center">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      p.status === "Act" ? "bg-green-500/10 text-green-400" : "bg-zinc-500/10 text-zinc-500"}`}>
                      {p.status === "Act" ? "ACT" : "RES"}
                    </span>
                  </td>
                  <td className="py-2 text-right text-zinc-400">${p.salary}</td>
                  <td className="py-2 text-right text-zinc-500">{p.games_played}</td>
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
                  <td className={`py-2 px-2 text-right font-mono text-xs ${(p.pos_scarcity_bonus ?? 0) > 0.3 ? "text-amber-400" : (p.pos_scarcity_bonus ?? 0) < -0.3 ? "text-zinc-600" : "text-zinc-500"}`}>
                    {(p.pos_scarcity_bonus ?? 0) > 0 ? "+" : ""}{(p.pos_scarcity_bonus ?? 0).toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
