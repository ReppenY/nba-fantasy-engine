"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Users, ArrowLeftRight, Calendar,
  Trophy, UserPlus, TrendingUp, Settings, MessageCircle, Brain, Gavel,
} from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/roster", label: "Roster", icon: Users },
  { href: "/trade-intel", label: "Trade Center", icon: ArrowLeftRight },
  { href: "/lineup", label: "Matchups", icon: Calendar },
  { href: "/league", label: "League", icon: Trophy },
  { href: "/waiver", label: "Waiver Wire", icon: UserPlus },
  { href: "/dynasty", label: "Dynasty", icon: TrendingUp },
  { href: "/offseason", label: "Off-Season", icon: Settings },
  { href: "/draft", label: "Draft Room", icon: Gavel },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 h-screen bg-[#1a1b23] border-r border-[#2a2b35] flex flex-col fixed left-0 top-0 z-10">
      <div className="p-4 border-b border-[#2a2b35]">
        <h1 className="text-lg font-bold text-blue-400">Fantasy Engine</h1>
        <p className="text-xs text-zinc-500 mt-0.5">He Who Remains</p>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-blue-500/10 text-blue-400 border-r-2 border-blue-400"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
              }`}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-[#2a2b35]">
        <Link
          href="/chat"
          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
            pathname === "/chat"
              ? "bg-blue-500/20 text-blue-400"
              : "bg-blue-500/10 text-blue-400 hover:bg-blue-500/20"
          }`}
        >
          <MessageCircle size={18} />
          AI Coach
        </Link>
      </div>
    </aside>
  );
}
