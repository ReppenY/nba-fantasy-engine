"use client";
import { useState, useEffect } from "react";

const BASE = "http://localhost:8000";

interface PickSelectorProps {
  selected: string[];
  onChange: (picks: string[]) => void;
  pool: "my" | "other";
  placeholder?: string;
}

export default function PickSelector({ selected, onChange, pool, placeholder }: PickSelectorProps) {
  const [availablePicks, setAvailablePicks] = useState<string[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);

  useEffect(() => {
    const url = pool === "my" ? "/trades/my-picks" : "/trades/other-picks";
    fetch(`${BASE}${url}`).then(r => r.json()).then(setAvailablePicks).catch(() => {});
  }, [pool]);

  function togglePick(pick: string) {
    if (selected.includes(pick)) {
      onChange(selected.filter(p => p !== pick));
    } else {
      onChange([...selected, pick]);
    }
  }

  const unselected = availablePicks.filter(p => !selected.includes(p));

  return (
    <div className="relative">
      {/* Selected picks */}
      <div
        className="min-h-[38px] bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm cursor-pointer flex flex-wrap gap-1 items-center"
        onClick={() => setShowDropdown(!showDropdown)}
      >
        {selected.length === 0 && (
          <span className="text-zinc-600">{placeholder || "Click to add picks..."}</span>
        )}
        {selected.map(pick => (
          <span key={pick} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded text-xs">
            {pick}
            <button
              onClick={e => { e.stopPropagation(); onChange(selected.filter(p => p !== pick)); }}
              className="text-blue-300 hover:text-white"
            >
              ×
            </button>
          </span>
        ))}
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[#1a1b23] border border-[#2a2b35] rounded-lg shadow-xl max-h-60 overflow-y-auto">
          {unselected.length === 0 && (
            <div className="px-3 py-2 text-xs text-zinc-500">No more picks available</div>
          )}
          {unselected.map(pick => (
            <button
              key={pick}
              onMouseDown={() => { togglePick(pick); }}
              className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-blue-500/10"
            >
              {pick}
            </button>
          ))}
          <button
            onMouseDown={() => setShowDropdown(false)}
            className="w-full text-center px-3 py-1.5 text-xs text-zinc-500 border-t border-zinc-800 hover:bg-zinc-800"
          >
            Done
          </button>
        </div>
      )}
    </div>
  );
}
