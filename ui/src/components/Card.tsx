export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-[#1a1b23] border border-[#2a2b35] rounded-xl p-5 ${className}`}>
      {children}
    </div>
  );
}

export function CardTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-3">{children}</h2>;
}

export function StatBadge({ label, value, color = "blue" }: { label: string; value: string | number; color?: string }) {
  const colors: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-400",
    green: "bg-green-500/10 text-green-400",
    red: "bg-red-500/10 text-red-400",
    yellow: "bg-yellow-500/10 text-yellow-400",
    zinc: "bg-zinc-500/10 text-zinc-400",
  };
  return (
    <div className={`rounded-lg px-3 py-2 ${colors[color] || colors.blue}`}>
      <div className="text-xs opacity-70">{label}</div>
      <div className="text-lg font-bold">{value}</div>
    </div>
  );
}

export function ZScoreBar({ value, max = 5 }: { value: number; max?: number }) {
  const pct = Math.min(100, Math.max(0, ((value + max) / (2 * max)) * 100));
  const color = value > 0.5 ? "bg-green-500" : value < -0.5 ? "bg-red-500" : "bg-zinc-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-mono ${value > 0 ? "text-green-400" : value < 0 ? "text-red-400" : "text-zinc-500"}`}>
        {value > 0 ? "+" : ""}{value.toFixed(2)}
      </span>
    </div>
  );
}
