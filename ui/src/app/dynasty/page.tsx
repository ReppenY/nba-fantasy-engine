"use client";
import { useEffect, useState } from "react";
import { api, Valuation } from "@/lib/api";
import { Card, CardTitle } from "@/components/Card";

export default function DynastyPage() {
  const [players, setPlayers] = useState<Valuation[]>([]);
  const [sortCol, setSortCol] = useState("dynasty_value");

  useEffect(() => {
    api.getValuations(35, sortCol).then(setPlayers).catch(() => {});
  }, [sortCol]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dynasty Rankings</h1>
        <div className="flex gap-2">
          {[
            { label: "Dynasty Value", col: "dynasty_value" },
            { label: "Z per $", col: "z_per_dollar" },
            { label: "Surplus", col: "surplus_value" },
            { label: "Z-Score", col: "z_total" },
          ].map((s) => (
            <button
              key={s.col}
              onClick={() => setSortCol(s.col)}
              className={`px-3 py-1.5 text-xs rounded-lg border ${
                sortCol === s.col ? "border-blue-500 bg-blue-500/10 text-blue-400" : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 text-xs border-b border-zinc-800">
              <th className="text-left py-2 px-2">#</th>
              <th className="text-left py-2">Player</th>
              <th className="text-right py-2">$</th>
              <th className="text-right py-2">Age</th>
              <th className="text-right py-2">Years</th>
              <th className="text-right py-2">Age Factor</th>
              <th className="text-right py-2">Z-Score</th>
              <th className="text-right py-2">Z per $</th>
              <th className="text-right py-2">Surplus</th>
              <th className="text-right py-2 font-bold">Dynasty</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => (
              <tr key={p.name} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
                <td className="py-2 px-2 text-zinc-500">{i + 1}</td>
                <td className="py-2 font-medium">{p.name}</td>
                <td className="py-2 text-right text-zinc-400">${p.salary}</td>
                <td className="py-2 text-right text-zinc-400">{p.age || "-"}</td>
                <td className="py-2 text-right text-zinc-400">{p.years_remaining}yr</td>
                <td className={`py-2 text-right text-xs ${p.age_factor > 1 ? "text-green-400" : p.age_factor < 0.7 ? "text-red-400" : "text-zinc-400"}`}>
                  {p.age_factor.toFixed(2)}x
                </td>
                <td className={`py-2 text-right font-mono ${p.z_total > 0 ? "text-green-400" : "text-red-400"}`}>
                  {p.z_total > 0 ? "+" : ""}{p.z_total.toFixed(1)}
                </td>
                <td className={`py-2 text-right font-mono ${p.z_per_dollar > 1 ? "text-green-400" : "text-zinc-400"}`}>
                  {p.z_per_dollar > 0 ? "+" : ""}{p.z_per_dollar.toFixed(1)}
                </td>
                <td className={`py-2 text-right font-mono ${p.surplus_value > 0 ? "text-green-400" : "text-red-400"}`}>
                  {p.surplus_value > 0 ? "+" : ""}{p.surplus_value.toFixed(1)}
                </td>
                <td className={`py-2 text-right font-bold font-mono ${p.dynasty_value > 0 ? "text-green-400" : "text-red-400"}`}>
                  {p.dynasty_value > 0 ? "+" : ""}{p.dynasty_value.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
