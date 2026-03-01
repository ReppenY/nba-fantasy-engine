"""
NBA injury tracking via ESPN's free public API.

Pulls current injuries for all NBA teams including:
- Player name, team, status (Out/Day-To-Day/Questionable)
- Injury description and details
- Expected return date
"""
import requests
from dataclasses import dataclass
from datetime import date

ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

# ESPN team ID -> abbreviation mapping (for teams not in response)
ESPN_TEAM_ABBREVS = {
    "1": "ATL", "2": "BOS", "3": "BKN", "4": "CHA", "5": "CHI",
    "6": "CLE", "7": "DAL", "8": "DEN", "9": "DET", "10": "GS",
    "11": "HOU", "12": "IND", "13": "LAC", "14": "LAL", "15": "MEM",
    "16": "MIA", "17": "MIL", "18": "MIN", "19": "NO", "20": "NY",
    "21": "OKC", "22": "ORL", "23": "PHI", "24": "PHX", "25": "POR",
    "26": "SAC", "27": "SA", "28": "TOR", "29": "UTA", "30": "WAS",
}


@dataclass
class InjuryReport:
    player_name: str
    team: str
    status: str           # "Out", "Day-To-Day", "Questionable", "Probable"
    description: str       # Short injury description
    long_description: str  # Detailed comment
    return_date: str       # Expected return date (ISO format or empty)
    injury_date: str       # When injury was reported


def fetch_all_injuries() -> list[InjuryReport]:
    """Fetch all current NBA injuries from ESPN."""
    try:
        r = requests.get(ESPN_INJURIES_URL, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ESPN injuries fetch failed: {e}")
        return []

    injuries = []
    for team_entry in data.get("injuries", []):
        team_id = team_entry.get("id", "")
        team_name = team_entry.get("displayName", "")

        # Get team abbreviation
        team_abbr = ESPN_TEAM_ABBREVS.get(team_id, "")
        if not team_abbr and team_name:
            # Try to extract from display name
            team_abbr = _guess_abbrev(team_name)

        for injury in team_entry.get("injuries", []):
            athlete = injury.get("athlete", {})
            name = athlete.get("displayName", "Unknown")

            # Parse return date from the details or longComment
            return_date = ""
            details = injury.get("details", {})
            if isinstance(details, dict):
                return_date = details.get("returnDate", "")

            # Also check the type for return info
            if not return_date:
                type_info = injury.get("type", {})
                if isinstance(type_info, dict):
                    return_date = type_info.get("returnDate", "")

            injuries.append(InjuryReport(
                player_name=name,
                team=team_abbr,
                status=injury.get("status", "Unknown"),
                description=injury.get("shortComment", ""),
                long_description=injury.get("longComment", ""),
                return_date=return_date,
                injury_date=injury.get("date", ""),
            ))

    return injuries


def filter_roster_injuries(
    all_injuries: list[InjuryReport],
    roster_names: list[str],
) -> list[InjuryReport]:
    """Filter injuries to only players on the given roster. Uses strict matching."""
    from fantasy_engine.ingestion.fantrax_api import _normalize_name
    roster_normalized = {_normalize_name(n) for n in roster_names}
    matched = []
    for inj in all_injuries:
        inj_normalized = _normalize_name(inj.player_name)
        if inj_normalized in roster_normalized:
            matched.append(inj)
    return matched


def get_return_timeline(injuries: list[InjuryReport]) -> list[dict]:
    """
    Sort injuries by expected return date.
    Returns list of dicts with player, status, return_date, days_until_return.
    """
    today = date.today()
    timeline = []

    for inj in injuries:
        days_until = None
        if inj.return_date:
            try:
                ret = date.fromisoformat(inj.return_date[:10])
                days_until = (ret - today).days
            except ValueError:
                pass

        timeline.append({
            "player": inj.player_name,
            "team": inj.team,
            "status": inj.status,
            "description": inj.description,
            "return_date": inj.return_date[:10] if inj.return_date else "Unknown",
            "days_until_return": days_until,
            "long_description": inj.long_description,
        })

    # Sort: known return dates first (soonest), then unknowns
    timeline.sort(key=lambda x: (
        x["days_until_return"] is None,
        x["days_until_return"] or 999,
    ))
    return timeline


def _guess_abbrev(team_name: str) -> str:
    """Guess team abbreviation from display name."""
    name_map = {
        "hawks": "ATL", "celtics": "BOS", "nets": "BKN", "hornets": "CHA",
        "bulls": "CHI", "cavaliers": "CLE", "mavericks": "DAL", "nuggets": "DEN",
        "pistons": "DET", "warriors": "GS", "rockets": "HOU", "pacers": "IND",
        "clippers": "LAC", "lakers": "LAL", "grizzlies": "MEM", "heat": "MIA",
        "bucks": "MIL", "timberwolves": "MIN", "pelicans": "NO", "knicks": "NY",
        "thunder": "OKC", "magic": "ORL", "76ers": "PHI", "suns": "PHX",
        "trail blazers": "POR", "kings": "SAC", "spurs": "SA", "raptors": "TOR",
        "jazz": "UTA", "wizards": "WAS",
    }
    lower = team_name.lower()
    for key, abbr in name_map.items():
        if key in lower:
            return abbr
    return ""
