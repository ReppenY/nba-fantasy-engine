"""
League rules and matchup schedule from Fantrax API.

Parses:
- Matchup schedule (who plays who each period)
- Roster constraints (position slots, max active/total)
- Multi-position eligibility per player
- Season dates
"""
import requests
from dataclasses import dataclass, field

BETA_API_BASE = "https://www.fantrax.com/fxea/general"


@dataclass
class MatchupInfo:
    period: int
    away_id: str
    away_name: str
    home_id: str
    home_name: str


@dataclass
class LeagueRules:
    league_name: str = ""
    season_year: int = 2025
    start_date: str = ""
    end_date: str = ""
    draft_type: str = ""
    num_teams: int = 12
    max_total_players: int = 38
    max_active_players: int = 10
    position_slots: dict[str, int] = field(default_factory=dict)
    scoring_categories: list[str] = field(default_factory=list)
    matchup_schedule: list[MatchupInfo] = field(default_factory=list)
    player_eligibility: dict[str, str] = field(default_factory=dict)  # fantrax_id -> eligible positions
    team_names: dict[str, str] = field(default_factory=dict)  # team_id -> name


def load_league_rules(league_id: str) -> LeagueRules:
    """Load all league rules and schedule from Fantrax API."""
    r = requests.get(
        f"{BETA_API_BASE}/getLeagueInfo",
        params={"leagueId": league_id},
        timeout=15,
    )
    r.raise_for_status()
    info = r.json()

    rules = LeagueRules()
    rules.league_name = info.get("leagueName", "")
    rules.season_year = info.get("seasonYear", 2025)
    rules.start_date = info.get("startDate", "")
    rules.end_date = info.get("endDate", "")
    rules.draft_type = info.get("draftType", "")

    # Team names
    team_info = info.get("teamInfo", {})
    rules.team_names = {tid: t.get("name", tid) for tid, t in team_info.items()}
    rules.num_teams = len(rules.team_names)

    # Roster constraints
    roster_info = info.get("rosterInfo", {})
    rules.max_total_players = roster_info.get("maxTotalPlayers", 38)
    rules.max_active_players = roster_info.get("maxTotalActivePlayers", 10)

    pos_constraints = roster_info.get("positionConstraints", {})
    rules.position_slots = {
        pos: settings.get("maxActive", 1)
        for pos, settings in pos_constraints.items()
    }

    # Scoring categories
    scoring = info.get("scoringSystem", {})
    cats = scoring.get("scoringCategories", {}).get("PLAYER", {})
    rules.scoring_categories = list(cats.keys())

    # Matchup schedule
    matchups_raw = info.get("matchups", [])
    for period_data in matchups_raw:
        period_num = period_data.get("period", 0)
        for m in period_data.get("matchupList", []):
            away = m.get("away", {})
            home = m.get("home", {})
            if away.get("TBD") or home.get("TBD"):
                continue
            rules.matchup_schedule.append(MatchupInfo(
                period=period_num,
                away_id=away.get("id", ""),
                away_name=away.get("name", ""),
                home_id=home.get("id", ""),
                home_name=home.get("name", ""),
            ))

    # Player position eligibility
    player_info = info.get("playerInfo", {})
    for pid, pdata in player_info.items():
        if isinstance(pdata, dict) and "eligiblePos" in pdata:
            rules.player_eligibility[pid] = pdata["eligiblePos"]

    return rules


def get_my_matchups(rules: LeagueRules, my_team_id: str) -> list[dict]:
    """Get all my matchups with opponent details."""
    matchups = []
    for m in rules.matchup_schedule:
        if m.away_id == my_team_id:
            matchups.append({
                "period": m.period,
                "opponent_id": m.home_id,
                "opponent_name": m.home_name,
                "home_away": "away",
            })
        elif m.home_id == my_team_id:
            matchups.append({
                "period": m.period,
                "opponent_id": m.away_id,
                "opponent_name": m.away_name,
                "home_away": "home",
            })
    return matchups


def get_current_matchup(rules: LeagueRules, my_team_id: str, current_period: int) -> dict | None:
    """Get my matchup for the current period."""
    my_matchups = get_my_matchups(rules, my_team_id)
    for m in my_matchups:
        if m["period"] == current_period:
            return m
    return None


def get_opponent_for_period(rules: LeagueRules, my_team_id: str, period: int) -> str | None:
    """Get opponent team ID for a given period."""
    m = get_current_matchup(rules, my_team_id, period)
    return m["opponent_id"] if m else None
