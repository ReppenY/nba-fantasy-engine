"use client";
import { useState, useEffect, useRef } from "react";

const BASE = "http://localhost:8000";

// Separate caches for give (my players) and receive (other teams)
let _myPlayersCache: string[] | null = null;
let _otherPlayersCache: string[] | null = null;
let _allPlayersCache: string[] | null = null;

async function fetchMyPlayers(): Promise<string[]> {
  if (_myPlayersCache) return _myPlayersCache;
  try {
    const r = await fetch(`${BASE}/trades/my-players`);
    _myPlayersCache = await r.json();
    return _myPlayersCache || [];
  } catch { return []; }
}

async function fetchOtherPlayers(): Promise<string[]> {
  if (_otherPlayersCache) return _otherPlayersCache;
  try {
    const r = await fetch(`${BASE}/trades/other-players`);
    _otherPlayersCache = await r.json();
    return _otherPlayersCache || [];
  } catch { return []; }
}

async function fetchAllPlayers(): Promise<string[]> {
  if (_allPlayersCache) return _allPlayersCache;
  const [my, other] = await Promise.all([fetchMyPlayers(), fetchOtherPlayers()]);
  _allPlayersCache = [...new Set([...my, ...other])].sort();
  return _allPlayersCache;
}

interface PlayerInputProps {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  className?: string;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  pool?: "my" | "other" | "all";  // Which player pool to search
}

export default function PlayerInput({ value, onChange, placeholder, className, onKeyDown, pool = "all" }: PlayerInputProps) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [allPlayers, setAllPlayers] = useState<string[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const loader = pool === "my" ? fetchMyPlayers : pool === "other" ? fetchOtherPlayers : fetchAllPlayers;
    loader().then(setAllPlayers);
  }, [pool]);

  useEffect(() => {
    if (!value.trim() || value.trim().length < 2) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }

    const parts = value.split(",");
    const current = parts[parts.length - 1].trim().toLowerCase();

    if (current.length < 2) {
      setSuggestions([]); setShowDropdown(false); return;
    }

    const filtered = allPlayers
      .filter(name => name.toLowerCase().includes(current))
      .slice(0, 8);

    setSuggestions(filtered);
    setShowDropdown(filtered.length > 0);
    setSelectedIdx(-1);
  }, [value, allPlayers]);

  function selectSuggestion(name: string) {
    const parts = value.split(",");
    parts[parts.length - 1] = (parts.length > 1 ? " " : "") + name;
    onChange(parts.join(","));
    setShowDropdown(false);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (showDropdown) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIdx(prev => Math.min(prev + 1, suggestions.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIdx(prev => Math.max(prev - 1, -1));
      } else if (e.key === "Enter" && selectedIdx >= 0) {
        e.preventDefault();
        selectSuggestion(suggestions[selectedIdx]);
        return;
      } else if (e.key === "Tab" && suggestions.length > 0) {
        e.preventDefault();
        selectSuggestion(suggestions[selectedIdx >= 0 ? selectedIdx : 0]);
        return;
      } else if (e.key === "Escape") {
        setShowDropdown(false);
      }
    }
    onKeyDown?.(e);
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
        onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
        placeholder={placeholder}
        className={className || "w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500"}
      />
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[#1a1b23] border border-[#2a2b35] rounded-lg shadow-xl max-h-48 overflow-y-auto">
          {suggestions.map((name, i) => (
            <button
              key={name}
              onMouseDown={() => selectSuggestion(name)}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-500/10 ${
                i === selectedIdx ? "bg-blue-500/10 text-blue-400" : "text-zinc-300"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
