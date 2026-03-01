"use client";
import { useEffect, useState } from "react";
import { api, OffseasonResponse } from "@/lib/api";
import { Card, CardTitle, StatBadge } from "@/components/Card";
import { ArrowRight, Search } from "lucide-react";
import PlayerInput from "@/components/PlayerInput";

type Tab = "contracts" | "keepers" | "auction" | "simulator";

export default function OffseasonPage() {
  const [tab, setTab] = useState<Tab>("contracts");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Off-Season Planning</h1>
      <div className="flex gap-2">
        {([
          ["contracts", "Contracts"],
          ["keepers", "Keeper Plan"],
          ["auction", "Auction Values"],
          ["simulator", "Trade Simulator"],
        ] as const).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm rounded-lg border ${
              tab === t ? "border-blue-500 bg-blue-500/10 text-blue-400" : "border-zinc-700 text-zinc-400 hover:bg-zinc-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "contracts" && <ContractsTab />}
      {tab === "keepers" && <KeepersTab />}
      {tab === "auction" && <AuctionTab />}
      {tab === "simulator" && <SimulatorTab />}
    </div>
  );
}

function ContractsTab() {
  const [data, setData] = useState<OffseasonResponse | null>(null);
  useEffect(() => { api.getOffseason().then(setData).catch(() => {}); }, []);
  if (!data) return <div className="text-zinc-500">Loading...</div>;
  const cap = data.cap_projection;

  return (
    <>
      <div className="grid grid-cols-4 gap-4">
        <StatBadge label="Current Salary" value={`$${cap.current_salary_total.toFixed(0)}/${cap.salary_cap}`} color="blue" />
        <StatBadge label="Cap Room" value={`$${cap.cap_room.toFixed(0)}`} color={cap.cap_room > 30 ? "green" : "yellow"} />
        <StatBadge label="Expiring" value={`$${cap.expiring_salary.toFixed(0)} (${cap.num_expiring} players)`} color="yellow" />
        <StatBadge label="Projected Room" value={`$${cap.projected_cap_room.toFixed(0)}`} color="green" />
      </div>
      {[
        { title: "Must Keep", list: data.must_keep },
        { title: "Keep", list: data.keep },
        { title: "Tradeable", list: data.tradeable },
        { title: "Drop Candidates", list: data.drop_candidates },
      ].map(({ title, list }) => list.length > 0 && (
        <Card key={title}>
          <CardTitle>{title} ({list.length})</CardTitle>
          <ContractTable list={list} />
        </Card>
      ))}
    </>
  );
}

function ContractTable({ list }: { list: OffseasonResponse["must_keep"] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-zinc-500 text-xs border-b border-zinc-800">
          <th className="text-left py-2">Player</th>
          <th className="text-right py-2">$</th>
          <th className="text-right py-2">Age</th>
          <th className="text-right py-2">Contract</th>
          <th className="text-right py-2">Z-Score</th>
          <th className="text-right py-2">Z/$</th>
          <th className="text-left py-2 pl-4">Reason</th>
        </tr>
      </thead>
      <tbody>
        {list.map((c) => (
          <tr key={c.name} className={`border-b border-zinc-800/50 ${c.is_expiring ? "bg-yellow-500/[0.03]" : ""}`}>
            <td className="py-2 font-medium">
              {c.name}
              {c.is_expiring && <span className="ml-2 text-[10px] px-1.5 py-0.5 bg-yellow-500/10 text-yellow-400 rounded">EXP</span>}
            </td>
            <td className="py-2 text-right text-zinc-400">${c.salary}</td>
            <td className="py-2 text-right text-zinc-400">{c.age || "-"}</td>
            <td className="py-2 text-right text-zinc-400">{c.contract} ({c.years_remaining}yr)</td>
            <td className={`py-2 text-right font-mono ${c.z_total > 0 ? "text-green-400" : "text-red-400"}`}>
              {c.z_total > 0 ? "+" : ""}{c.z_total.toFixed(1)}
            </td>
            <td className={`py-2 text-right font-mono ${c.z_per_dollar > 1 ? "text-green-400" : "text-zinc-400"}`}>
              {c.z_per_dollar.toFixed(1)}
            </td>
            <td className="py-2 pl-4 text-xs text-zinc-500">{c.reason.slice(0, 60)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function KeepersTab() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.getKeeperPlan>> | null>(null);
  useEffect(() => { api.getKeeperPlan().then(setData).catch(() => {}); }, []);
  if (!data) return <div className="text-zinc-500">Loading...</div>;

  return (
    <>
      <div className="grid grid-cols-3 gap-4">
        <StatBadge label="Salary After Keepers" value={`$${data.total_kept_salary.toFixed(0)}`} color="blue" />
        <StatBadge label="Cap Room" value={`$${data.cap_room_after.toFixed(0)}`} color="green" />
        <StatBadge label="Roster Spots Opened" value={data.roster_spots_opened} color="yellow" />
      </div>

      <Card>
        <CardTitle>Keep ({data.keeps.length})</CardTitle>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 text-xs border-b border-zinc-800">
              <th className="text-left py-2">Player</th>
              <th className="text-right py-2">Salary</th>
              <th className="text-right py-2">Auction Value</th>
              <th className="text-right py-2">Surplus</th>
              <th className="text-right py-2">Z-Score</th>
              <th className="text-left py-2 pl-4">Reason</th>
            </tr>
          </thead>
          <tbody>
            {data.keeps.map((k) => (
              <tr key={k.name} className="border-b border-zinc-800/50">
                <td className="py-2 font-medium">
                  {k.name}
                  {k.is_injured && <span className="ml-2 text-[10px] px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded">INJ</span>}
                </td>
                <td className="py-2 text-right text-zinc-400">${k.salary}</td>
                <td className="py-2 text-right text-green-400">${k.auction_value}</td>
                <td className="py-2 text-right font-mono text-green-400">+${k.surplus.toFixed(0)}</td>
                <td className={`py-2 text-right font-mono ${k.z_total > 0 ? "text-green-400" : "text-red-400"}`}>
                  {k.z_total > 0 ? "+" : ""}{k.z_total.toFixed(1)}
                </td>
                <td className="py-2 pl-4 text-xs text-zinc-500">{k.reason.slice(0, 50)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card>
        <CardTitle>Let Walk ({data.lets_walk.length})</CardTitle>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500 text-xs border-b border-zinc-800">
              <th className="text-left py-2">Player</th>
              <th className="text-right py-2">Salary</th>
              <th className="text-right py-2">Z-Score</th>
              <th className="text-left py-2 pl-4">Reason</th>
            </tr>
          </thead>
          <tbody>
            {data.lets_walk.map((k) => (
              <tr key={k.name} className="border-b border-zinc-800/50">
                <td className="py-2 font-medium">
                  {k.name}
                  {k.is_injured && <span className="ml-2 text-[10px] px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded">INJ</span>}
                </td>
                <td className="py-2 text-right text-zinc-400">${k.salary}</td>
                <td className={`py-2 text-right font-mono ${k.z_total > 0 ? "text-green-400" : "text-red-400"}`}>
                  {k.z_total > 0 ? "+" : ""}{k.z_total.toFixed(1)}
                </td>
                <td className="py-2 pl-4 text-xs text-zinc-500">{k.reason.slice(0, 55)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function AuctionTab() {
  const [values, setValues] = useState<Awaited<ReturnType<typeof api.getAuctionValues>> | null>(null);
  useEffect(() => { api.getAuctionValues(40).then(setValues).catch(() => {}); }, []);
  if (!values) return <div className="text-zinc-500">Loading...</div>;

  const tierColors: Record<string, string> = {
    elite: "bg-purple-500/10 text-purple-400",
    starter: "bg-blue-500/10 text-blue-400",
    bench: "bg-zinc-500/10 text-zinc-400",
    replacement: "bg-zinc-800 text-zinc-600",
  };

  return (
    <Card>
      <CardTitle>Auction/Draft Values (League-Wide)</CardTitle>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
            <th className="text-left py-2 px-2">#</th>
            <th className="text-left py-2">Player</th>
            <th className="text-left py-2">Team</th>
            <th className="text-center py-2">Tier</th>
            <th className="text-right py-2">Auction $</th>
            <th className="text-right py-2">Current $</th>
            <th className="text-right py-2">Diff</th>
            <th className="text-right py-2">Z-Score</th>
          </tr>
        </thead>
        <tbody>
          {values.map((v, i) => (
            <tr key={v.name} className="border-b border-zinc-800/50 hover:bg-white/[0.02]">
              <td className="py-2 px-2 text-zinc-500">{i + 1}</td>
              <td className="py-2 font-medium">{v.name}</td>
              <td className="py-2 text-zinc-400 text-xs">{v.nba_team}</td>
              <td className="py-2 text-center">
                <span className={`text-[10px] px-2 py-0.5 rounded ${tierColors[v.tier] || ""}`}>{v.tier}</span>
              </td>
              <td className="py-2 text-right font-mono text-green-400">${v.auction_value.toFixed(0)}</td>
              <td className="py-2 text-right text-zinc-400">${v.current_salary.toFixed(0)}</td>
              <td className={`py-2 text-right font-mono text-xs ${v.value_diff > 2 ? "text-green-400" : v.value_diff < -2 ? "text-red-400" : "text-zinc-500"}`}>
                {v.value_diff > 0 ? "+" : ""}{v.value_diff.toFixed(0)}
              </td>
              <td className={`py-2 text-right font-mono ${v.z_total > 0 ? "text-green-400" : "text-red-400"}`}>
                {v.z_total > 0 ? "+" : ""}{v.z_total.toFixed(1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function SimulatorTab() {
  const [playerName, setPlayerName] = useState("");
  const [mode, setMode] = useState<"acquire" | "sell">("acquire");
  const [results, setResults] = useState<Awaited<ReturnType<typeof api.tradeSimulator>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search() {
    if (!playerName.trim()) return;
    setLoading(true);
    setError("");
    setResults(null);
    try {
      const res = await api.tradeSimulator(playerName.trim(), mode);
      setResults(res);
      if (res.length === 0) setError(`No trade packages found for "${playerName}"`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Card>
        <CardTitle>Trade Simulator</CardTitle>
        <p className="text-sm text-zinc-500 mb-4">Search for a player to acquire or sell. Scans all 12 teams for realistic trade packages.</p>
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-xs text-zinc-500 mb-1 block">Player name</label>
            <PlayerInput
              value={playerName}
              onChange={setPlayerName}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="e.g. Jrue Holiday, Nikola Jokic..."
              pool={mode === "acquire" ? "other" : "my"}
            />
          </div>
          <div className="flex rounded-lg border border-zinc-700 overflow-hidden">
            {(["acquire", "sell"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-2 text-sm ${mode === m ? "bg-blue-600 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}
              >
                {m === "acquire" ? "I want to get" : "I want to sell"}
              </button>
            ))}
          </div>
          <button
            onClick={search}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 flex items-center gap-2"
          >
            <Search size={16} /> {loading ? "Searching..." : "Find Trades"}
          </button>
        </div>
        {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
      </Card>

      {results && results.length > 0 && (
        <Card>
          <CardTitle>Trade Packages ({results.length})</CardTitle>
          <div className="space-y-3">
            {results.map((p, i) => {
              const feasColors: Record<string, string> = {
                highly_feasible: "bg-green-500/10 text-green-400",
                feasible: "bg-blue-500/10 text-blue-400",
                stretch: "bg-yellow-500/10 text-yellow-400",
              };
              return (
                <div key={i} className="p-4 border border-zinc-800 rounded-lg hover:border-zinc-700">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm">
                      <span className="text-zinc-500">vs</span>{" "}
                      <span className="font-medium">{p.opponent_team}</span>
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded ${feasColors[p.feasibility] || ""}`}>
                      {p.feasibility.replace("_", " ")}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <div className="text-red-300">Give: {p.i_give.join(", ")}</div>
                    <ArrowRight size={14} className="text-zinc-600" />
                    <div className="text-green-300">Get: {p.i_receive.join(", ")}</div>
                  </div>
                  <div className="flex gap-4 mt-2 text-xs text-zinc-500">
                    <span>My gain: <span className="text-green-400">{p.my_need_score.toFixed(1)}</span></span>
                    <span>Their gain: <span className="text-blue-400">{p.their_need_score.toFixed(1)}</span></span>
                    <span>Salary: {p.salary_diff > 0 ? "+" : ""}${p.salary_diff.toFixed(0)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </>
  );
}
