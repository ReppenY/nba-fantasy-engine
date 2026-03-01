"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardTitle } from "@/components/Card";
import { ArrowRight } from "lucide-react";

const CAT_LABELS: Record<string, string> = {
  pts: "PTS", reb: "REB", ast: "AST", stl: "STL", blk: "BLK",
  tpm: "3PM", fg_pct: "FG%", ft_pct: "FT%", tov: "TO",
};

interface WaiverData {
  best_available: Array<{ name: string; z_total: number; need_weighted_z: number; salary: number; helps_cats: string[] }>;
  drop_candidates: Array<{ name: string; z_total: number; z_per_dollar: number; salary: number; droppability_score: number; reason: string }>;
  best_swaps: Array<{ drop: string; add: string; net_z_change: number; net_need_z_change: number; salary_change: number }>;
}

export default function WaiverPage() {
  const [data, setData] = useState<WaiverData | null>(null);

  useEffect(() => {
    api.getRoster().then(() => {
      fetch("http://localhost:8000/waiver/analysis?top=10")
        .then(r => r.json())
        .then(setData)
        .catch(() => {});
    });
  }, []);

  if (!data) return <div className="text-zinc-500">Loading...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Waiver Wire</h1>

      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardTitle>Best Available (by team need)</CardTitle>
          <div className="space-y-2">
            {data.best_available.map((a, i) => (
              <div key={a.name} className="flex items-center justify-between p-2 rounded-lg hover:bg-white/[0.02]">
                <div>
                  <span className="text-zinc-500 text-xs mr-2">#{i + 1}</span>
                  <span className="font-medium text-sm">{a.name}</span>
                  <span className="text-xs text-zinc-500 ml-2">${a.salary}</span>
                </div>
                <div className="flex items-center gap-3">
                  {a.helps_cats.length > 0 && (
                    <span className="text-xs text-green-400">{a.helps_cats.map(c => CAT_LABELS[c] || c).join(", ")}</span>
                  )}
                  <span className={`text-xs font-mono ${a.need_weighted_z > 0 ? "text-green-400" : "text-red-400"}`}>
                    {a.need_weighted_z > 0 ? "+" : ""}{a.need_weighted_z.toFixed(1)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardTitle>Drop Candidates</CardTitle>
          <div className="space-y-2">
            {data.drop_candidates.map((d, i) => (
              <div key={d.name} className="flex items-center justify-between p-2 rounded-lg hover:bg-white/[0.02]">
                <div>
                  <span className="text-zinc-500 text-xs mr-2">#{i + 1}</span>
                  <span className="font-medium text-sm">{d.name}</span>
                  <span className="text-xs text-zinc-500 ml-2">${d.salary}</span>
                </div>
                <div className="text-right">
                  <span className="text-xs text-red-400 font-mono">z: {d.z_total.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <CardTitle>Best Swaps</CardTitle>
        <div className="space-y-2">
          {data.best_swaps.map((s, i) => (
            <div key={i} className="flex items-center gap-4 p-3 rounded-lg border border-zinc-800 hover:border-zinc-700">
              <span className="text-zinc-500 text-sm w-6">#{i + 1}</span>
              <span className="text-red-300 text-sm flex-1">Drop {s.drop}</span>
              <ArrowRight size={14} className="text-zinc-600" />
              <span className="text-green-300 text-sm flex-1">Add {s.add}</span>
              <span className={`text-xs font-mono ${s.net_z_change > 0 ? "text-green-400" : "text-red-400"}`}>
                {s.net_z_change > 0 ? "+" : ""}{s.net_z_change.toFixed(1)} z
              </span>
              <span className="text-xs text-zinc-500">
                {s.salary_change > 0 ? "+" : ""}${s.salary_change.toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
