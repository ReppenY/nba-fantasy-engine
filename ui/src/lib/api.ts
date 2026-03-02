const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// Types
export interface PlayerZScores {
  name: string;
  nba_team: string;
  salary: number;
  age: number;
  positions: string;
  games_played: number;
  z_pts: number;
  z_reb: number;
  z_ast: number;
  z_stl: number;
  z_blk: number;
  z_tpm: number;
  z_fg_pct: number;
  z_ft_pct: number;
  z_tov: number;
  z_total: number;
  pos_scarcity_bonus?: number;
  scarcest_position?: string;
  status?: string;
}

export interface TeamProfile {
  categories: Record<string, { z_sum: number; rank: number; strength: string }>;
  strongest_cats: string[];
  weakest_cats: string[];
  suggested_punts: string[];
  total_z: number;
}

export interface TradeResponse {
  verdict: string;
  combined_score: number;
  z_diff: number;
  salary_impact: number;
  cap_room_after: number;
  dynasty_diff: number;
  cat_impact: Record<string, number>;
  improves: string[];
  hurts: string[];
  explanation: string;
  give: { players: string[]; total_salary: number; total_z: number; z_per_cat: Record<string, number>; dynasty_value: number };
  receive: { players: string[]; total_salary: number; total_z: number; z_per_cat: Record<string, number>; dynasty_value: number };
}

export interface LineupSlot {
  slot: string;
  player_name: string;
  positions: string;
  games_this_week: number;
  weekly_z: number;
}

export interface LineupResponse {
  active: LineupSlot[];
  bench: string[];
  total_weekly_z: number;
  category_projections: Record<string, number>;
}

export interface Alert {
  type: string;
  priority: string;
  title: string;
  detail: string;
  player: string;
  action: string;
}

export interface TeamSummary {
  team_id: string;
  name: string;
  player_count: number;
  total_z: number;
  strongest: string[];
  weakest: string[];
}

export interface TradeProposal {
  opponent_team: string;
  give: string[];
  receive: string[];
  my_score: number;
  their_score: number;
  mutual_score: number;
  salary_diff: number;
  z_diff: number;
  improves_me: string[];
  improves_them: string[];
}

export interface Valuation {
  name: string;
  salary: number;
  age: number;
  years_remaining: number;
  z_total: number;
  z_per_dollar: number;
  surplus_value: number;
  dynasty_value: number;
  age_factor: number;
}

export interface OffseasonContract {
  name: string;
  salary: number;
  contract: string;
  years_remaining: number;
  is_expiring: boolean;
  z_total: number;
  z_per_dollar: number;
  age: number;
  recommendation: string;
  reason: string;
}

export interface OffseasonResponse {
  cap_projection: {
    current_salary_total: number;
    salary_cap: number;
    cap_room: number;
    expiring_salary: number;
    committed_salary: number;
    projected_cap_room: number;
    num_expiring: number;
    num_kept: number;
  };
  must_keep: OffseasonContract[];
  keep: OffseasonContract[];
  tradeable: OffseasonContract[];
  drop_candidates: OffseasonContract[];
  expiring: OffseasonContract[];
}

export interface FreeAgent {
  name: string;
  nba_team: string;
  z_total: number;
  pts: number;
  reb: number;
  ast: number;
  games_played: number;
}

export interface Injury {
  player: string;
  team: string;
  status: string;
  description: string;
  return_date: string;
  days_until_return: number | null;
  long_description: string;
}

export interface ChatResponse {
  response: string;
  conversation_length: number;
}

// API functions
export const api = {
  getRankings: (top = 30, punt = "") =>
    fetchJSON<PlayerZScores[]>(`/players/rankings?top=${top}&punt=${punt}`),

  getPlayerZScores: (name: string) =>
    fetchJSON<PlayerZScores>(`/players/${encodeURIComponent(name)}/zscores`),

  getValuations: (top = 30, sortBy = "dynasty_value") =>
    fetchJSON<Valuation[]>(`/players/valuations?top=${top}&sort_by=${sortBy}`),

  getTeamProfile: (activeOnly = false) =>
    fetchJSON<TeamProfile>(`/teams/my/profile?active_only=${activeOnly}`),

  getRoster: (status = "") =>
    fetchJSON<PlayerZScores[]>(`/teams/my/roster?status=${status}`),

  evaluateTrade: (give: string[], receive: string[], puntCats: string[] = []) =>
    fetchJSON<TradeResponse>("/trades/evaluate", {
      method: "POST",
      body: JSON.stringify({ give, receive, punt_cats: puntCats }),
    }),

  getLineup: (punt = "", injured = "") =>
    fetchJSON<LineupResponse>(`/lineup/optimize?punt=${punt}&injured=${injured}`),

  getAlerts: () => fetchJSON<Alert[]>("/league/alerts"),
  getInjuries: (rosterOnly = true) =>
    fetchJSON<Injury[]>(`/league/injuries?roster_only=${rosterOnly}`),
  getLeagueTeams: () => fetchJSON<TeamSummary[]>("/league/teams"),
  getFreeAgents: (top = 30) => fetchJSON<FreeAgent[]>(`/league/free-agents?top=${top}`),
  getTradeProposals: (top = 15, punt = "") =>
    fetchJSON<TradeProposal[]>(`/league/trade-finder?top=${top}&punt=${punt}`),

  getOffseason: () => fetchJSON<OffseasonResponse>("/offseason/contracts"),

  getAuctionValues: (top = 50) =>
    fetchJSON<Array<{name: string; nba_team: string; z_total: number; z_above_replacement: number; auction_value: number; current_salary: number; value_diff: number; tier: string; age: number}>>(`/offseason/auction-values?top=${top}`),

  getKeeperPlan: () =>
    fetchJSON<{keeps: Array<{name: string; salary: number; auction_value: number; surplus: number; z_total: number; age: number; contract: string; is_injured: boolean; injury_return: string; decision: string; reason: string; priority: number}>; lets_walk: Array<{name: string; salary: number; auction_value: number; surplus: number; z_total: number; age: number; contract: string; is_injured: boolean; injury_return: string; decision: string; reason: string; priority: number}>; total_kept_salary: number; cap_room_after: number; roster_spots_opened: number}>("/offseason/keeper-plan"),

  tradeSimulator: (playerName: string, mode: "acquire" | "sell" = "acquire") =>
    fetchJSON<Array<{opponent_team: string; i_give: string[]; i_receive: string[]; my_need_score: number; their_need_score: number; salary_diff: number; feasibility: string; my_cat_changes: Record<string, number>}>>("/offseason/trade-simulator", {
      method: "POST",
      body: JSON.stringify({ player_name: playerName, mode }),
    }),

  chat: (message: string, provider = "openai", reset = false) =>
    fetchJSON<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, provider, reset }),
    }),

  resetChat: () => fetchJSON("/chat/reset", { method: "POST" }),

  getStatus: () => fetchJSON<{ status: string; players_loaded: number; active_count: number; reserve_count: number }>("/admin/status"),
};
