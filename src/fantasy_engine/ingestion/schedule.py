"""
NBA schedule integration.

Pulls the current season schedule from nba_api and computes
games per team for any given week/date range.
"""
import time
from datetime import date, timedelta

import pandas as pd


def get_weekly_games(
    start_date: date | None = None,
    end_date: date | None = None,
    season: str = "2025-26",
) -> dict[str, int]:
    """
    Get number of games per NBA team for a given week.

    Args:
        start_date: Week start. Defaults to next Monday.
        end_date: Week end. Defaults to Sunday after start_date.
        season: NBA season string.

    Returns dict of team_abbreviation -> games_this_week.
    """
    from nba_api.stats.endpoints import LeagueGameLog

    if start_date is None:
        today = date.today()
        # Next Monday
        start_date = today + timedelta(days=(7 - today.weekday()) % 7)
    if end_date is None:
        end_date = start_date + timedelta(days=6)

    # Get all games for the season
    try:
        log = LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
        )
        time.sleep(0.6)
        df = log.get_data_frames()[0]
    except Exception:
        # Fallback: return default 4 games for all teams
        return _default_games()

    if df.empty:
        return _default_games()

    # Parse game dates
    df["GAME_DATE_PARSED"] = pd.to_datetime(df["GAME_DATE"]).dt.date

    # Filter to the target week
    week_games = df[
        (df["GAME_DATE_PARSED"] >= start_date)
        & (df["GAME_DATE_PARSED"] <= end_date)
    ]

    if week_games.empty:
        return _default_games()

    # Count games per team (each game appears twice — one per team)
    team_games = week_games.groupby("TEAM_ABBREVIATION").size().to_dict()
    return team_games


def get_player_games_map(
    roster_df: pd.DataFrame,
    team_games: dict[str, int],
) -> dict[str, int]:
    """
    Map player names to their games this week based on their NBA team.

    Args:
        roster_df: Roster with 'name' and 'nba_team' columns.
        team_games: Output of get_weekly_games().

    Returns dict of player_name -> games_this_week.
    """
    games_map = {}
    for _, row in roster_df.iterrows():
        name = row.get("name", "")
        team = row.get("nba_team", "")
        games_map[name] = team_games.get(team, 3)  # Default 3 if team not found
    return games_map


# nba_api uses different abbreviations than Fantrax
NBA_TO_FANTRAX_ABBREV = {
    "SAS": "SA", "GSW": "GS", "NOP": "NO", "NYK": "NY", "PHX": "PHX",
    "BKN": "BKN", "WAS": "WAS", "OKC": "OKC", "UTA": "UTA",
    "POR": "POR", "SAC": "SAC", "ATL": "ATL", "BOS": "BOS",
    "CHA": "CHA", "CHI": "CHI", "CLE": "CLE", "DAL": "DAL",
    "DEN": "DEN", "DET": "DET", "HOU": "HOU", "IND": "IND",
    "LAC": "LAC", "LAL": "LAL", "MEM": "MEM", "MIA": "MIA",
    "MIL": "MIL", "MIN": "MIN", "ORL": "ORL", "PHI": "PHI",
    "TOR": "TOR",
}


def get_daily_schedule(
    start_date: date | None = None,
    end_date: date | None = None,
    season: str = "2025-26",
) -> dict[str, set[str]]:
    """
    Get per-day NBA schedule: which teams play on each day.

    Returns dict of date_iso_string -> set of team abbreviations.
    Example: {"2026-03-02": {"LAL", "BOS", "MIL"}, "2026-03-03": {"HOU", "DAL"}}
    """
    from nba_api.stats.endpoints import LeagueGameLog

    if start_date is None:
        today = date.today()
        start_date = today
    if end_date is None:
        end_date = start_date + timedelta(days=6)

    try:
        log = LeagueGameLog(season=season, season_type_all_star="Regular Season")
        time.sleep(0.6)
        df = log.get_data_frames()[0]
    except Exception:
        return _default_daily(start_date, end_date)

    if df.empty:
        return _default_daily(start_date, end_date)

    df["GAME_DATE_PARSED"] = pd.to_datetime(df["GAME_DATE"]).dt.date

    week_games = df[
        (df["GAME_DATE_PARSED"] >= start_date)
        & (df["GAME_DATE_PARSED"] <= end_date)
    ]

    daily: dict[str, set[str]] = {}
    for _, row in week_games.iterrows():
        day_str = row["GAME_DATE_PARSED"].isoformat()
        nba_team = str(row["TEAM_ABBREVIATION"])
        # Map to Fantrax abbreviation
        fantrax_team = NBA_TO_FANTRAX_ABBREV.get(nba_team, nba_team)
        if day_str not in daily:
            daily[day_str] = set()
        daily[day_str].add(fantrax_team)
        daily[day_str].add(nba_team)  # Keep both for compatibility

    return daily


def get_player_daily_schedule(
    roster_df: pd.DataFrame,
    daily_schedule: dict[str, set[str]],
) -> dict[str, dict[str, bool]]:
    """
    Map each player to which days they play.

    Returns: dict[player_name][date_str] = True/False
    """
    result = {}
    for _, row in roster_df.iterrows():
        name = row.get("name", "")
        team = row.get("nba_team", "")
        player_days = {}
        for day_str, teams in sorted(daily_schedule.items()):
            player_days[day_str] = team in teams
        result[name] = player_days
    return result


def _default_daily(start: date, end: date) -> dict[str, set[str]]:
    """Fallback: assume all teams play every other day."""
    nba_teams = [
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN",
        "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
        "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX",
        "POR", "SAC", "SA", "TOR", "UTA", "WAS",
    ]
    daily = {}
    current = start
    i = 0
    while current <= end:
        # Alternate halves of teams each day
        if i % 2 == 0:
            daily[current.isoformat()] = set(nba_teams[:15])
        else:
            daily[current.isoformat()] = set(nba_teams[15:])
        current += timedelta(days=1)
        i += 1
    return daily


def _default_games() -> dict[str, int]:
    """Return default 3-4 games per team as fallback."""
    nba_teams = [
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN",
        "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
        "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX",
        "POR", "SAC", "SA", "TOR", "UTA", "WAS",
    ]
    return {t: 4 for t in nba_teams}
