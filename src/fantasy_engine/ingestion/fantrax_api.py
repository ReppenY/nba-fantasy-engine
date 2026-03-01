"""
Fantrax Beta API client.

Uses the unauthenticated Beta API endpoints at:
    https://www.fantrax.com/fxea/general/<method>

Provides rosters (salaries, contracts, positions, status) for all teams.
Stats come from nba_api and are merged by player name.
"""
import time

import pandas as pd
import requests

BETA_API_BASE = "https://www.fantrax.com/fxea/general"

# Map contract "name" to years remaining
CONTRACT_YEARS = {"1st": 3, "2nd": 2, "3rd": 1}


class FantraxAPIClient:
    def __init__(self, league_id: str):
        self.league_id = league_id
        self.timeout = 15
        self._player_lookup: dict | None = None

    # -- raw API calls --

    def get_league_info(self) -> dict:
        r = requests.get(
            f"{BETA_API_BASE}/getLeagueInfo",
            params={"leagueId": self.league_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_team_rosters_raw(self, period: int | None = None) -> dict:
        params = {"leagueId": self.league_id}
        if period is not None:
            params["period"] = period
        r = requests.get(
            f"{BETA_API_BASE}/getTeamRosters",
            params=params,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_standings(self) -> dict:
        r = requests.get(
            f"{BETA_API_BASE}/getStandings",
            params={"leagueId": self.league_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_draft_picks(self) -> list:
        r = requests.get(
            f"{BETA_API_BASE}/getDraftPicks",
            params={"leagueId": self.league_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_adp(self) -> list:
        r = requests.get(
            f"{BETA_API_BASE}/getAdp",
            params={"sport": "NBA"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    # -- player lookup --

    def _get_player_lookup(self) -> dict:
        """Fetch and cache the fantrax_id -> player info mapping."""
        if self._player_lookup is None:
            r = requests.get(
                f"{BETA_API_BASE}/getPlayerIds",
                params={"sport": "NBA"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            self._player_lookup = r.json()
        return self._player_lookup

    def _resolve_name(self, fantrax_id: str) -> tuple[str, str, str]:
        """Resolve fantrax_id to (display_name, nba_team, eligible_positions)."""
        lookup = self._get_player_lookup()
        info = lookup.get(fantrax_id, {})
        if not info:
            return "Unknown", "", ""
        # Name is "Last, First" -> convert to "First Last"
        raw_name = info.get("name", "Unknown")
        if "," in raw_name:
            parts = raw_name.split(",", 1)
            display = f"{parts[1].strip()} {parts[0].strip()}"
        else:
            display = raw_name
        team = info.get("team", "")
        if team == "(N/A)":
            team = ""
        pos = info.get("position", "")
        return display, team, pos

    # -- high-level methods --

    def find_my_team_id(self, known_player_ids: list[str] | None = None) -> str | None:
        """
        Find your team ID. If known_player_ids is given, match by those.
        Otherwise, return None (you'll need to set it in config).
        """
        if not known_player_ids:
            return None
        rosters = self.get_team_rosters_raw().get("rosters", {})
        for team_id, team in rosters.items():
            roster_ids = {item["id"] for item in team.get("rosterItems", [])}
            if roster_ids & set(known_player_ids):
                return team_id
        return None

    def get_team_roster_df(self, team_id: str) -> pd.DataFrame:
        """
        Build a roster DataFrame for one team from the API.

        Returns DataFrame with columns matching the CSV parser output:
            fantrax_id, name, nba_team, positions, roster_slot, status,
            salary, contract, years_remaining, is_expiring, age
            (age will be 0 — not available from API, filled by nba_api later)
        """
        raw = self.get_team_rosters_raw()
        rosters = raw.get("rosters", {})
        team = rosters.get(team_id)
        if team is None:
            raise ValueError(f"Team {team_id} not found. Available: {list(rosters.keys())}")

        rows = []
        for item in team.get("rosterItems", []):
            fid = item["id"]
            display_name, nba_team, pos = self._resolve_name(fid)
            contract_name = item.get("contract", {}).get("name", "1st")
            years = CONTRACT_YEARS.get(contract_name)
            if years is None:
                try:
                    years = max(1, int(contract_name) - 2025)
                except (ValueError, TypeError):
                    years = 1

            rows.append({
                "fantrax_id": fid,
                "name": display_name,
                "nba_team": nba_team,
                "positions": pos,
                "roster_slot": item.get("position", ""),
                "status": "Act" if item.get("status") == "ACTIVE" else "Res",
                "salary": item.get("salary", 1.0),
                "contract": contract_name,
                "years_remaining": years,
                "is_expiring": years <= 1,
                "age": 0,
            })

        return pd.DataFrame(rows)

    def get_all_rosters(self) -> dict[str, pd.DataFrame]:
        """Get roster DataFrames for all teams."""
        raw = self.get_team_rosters_raw()
        rosters = raw.get("rosters", {})
        result = {}
        for team_id in rosters:
            result[team_id] = self.get_team_roster_df(team_id)
        return result

    def get_team_names(self) -> dict[str, str]:
        """Get team_id -> team_name mapping."""
        info = self.get_league_info()
        team_info = info.get("teamInfo", {})
        return {tid: t.get("name", tid) for tid, t in team_info.items()}


def _normalize_name(name: str) -> str:
    """
    Normalize a player name for matching.

    Handles:
    - Diacritics: Bogdanović -> bogdanovic, Jović -> jovic, Jakučionis -> jakucionis
    - Apostrophes: De'Aaron -> deaaron
    - Suffixes: Jr., Sr., III, II
    - Case
    """
    import unicodedata
    # Decompose unicode and strip diacritics
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase, strip punctuation
    result = ascii_name.lower().replace("'", "").replace("'", "").replace(".", "").strip()
    # Remove common suffixes
    for suffix in [" jr", " sr", " iii", " ii", " iv"]:
        if result.endswith(suffix):
            result = result[: -len(suffix)].strip()
    return result


def merge_with_nba_stats(
    roster_df: pd.DataFrame,
    nba_stats_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge Fantrax roster data with NBA stats by fuzzy name matching.

    Handles diacritics, apostrophes, Jr./Sr. suffixes, and first-name variants.
    """
    roster = roster_df.copy()
    stats = nba_stats_df.copy()

    roster["_match"] = roster["name"].apply(_normalize_name)
    stats["_match"] = stats["name"].apply(_normalize_name)

    # Build a lookup from normalized name -> stats row index
    stats_lookup = {}
    for idx, row in stats.iterrows():
        stats_lookup[row["_match"]] = idx

    # Also build last-name lookup for fallback
    last_name_lookup: dict[str, list[int]] = {}
    for idx, row in stats.iterrows():
        parts = row["_match"].split()
        if parts:
            last = parts[-1]
            last_name_lookup.setdefault(last, []).append(idx)

    # Match each roster player
    stat_cols = [
        "games_played", "minutes", "pts", "reb", "ast", "stl", "blk",
        "tpm", "fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct", "tov",
    ]
    # Initialize stat columns
    for col in stat_cols:
        if col not in roster.columns:
            roster[col] = 0.0

    matched = 0
    for i, row in roster.iterrows():
        norm = row["_match"]

        # Try exact match
        si = stats_lookup.get(norm)

        # Try last-name + first-initial match
        if si is None:
            parts = norm.split()
            if len(parts) >= 2:
                last = parts[-1]
                first_char = parts[0][0] if parts[0] else ""
                candidates = last_name_lookup.get(last, [])
                for ci in candidates:
                    cname = stats.at[ci, "_match"]
                    cparts = cname.split()
                    if cparts and cparts[0] and cparts[0][0] == first_char:
                        si = ci
                        break

        if si is not None:
            matched += 1
            for col in stat_cols:
                if col in stats.columns:
                    roster.at[i, col] = stats.at[si, col]
            # Update nba_team from stats if roster's is empty
            if not roster.at[i, "nba_team"] and "nba_team" in stats.columns:
                roster.at[i, "nba_team"] = stats.at[si, "nba_team"]
            # Update age from stats
            if "age" in stats.columns and stats.at[si, "age"]:
                roster.at[i, "age"] = int(stats.at[si, "age"])
            # Carry nba_api_id for game log fetching
            if "nba_api_id" in stats.columns:
                roster.at[i, "nba_api_id"] = int(stats.at[si, "nba_api_id"])

    roster = roster.drop(columns=["_match"])
    return roster
