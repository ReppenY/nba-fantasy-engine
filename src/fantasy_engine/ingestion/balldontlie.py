"""
Ball Don't Lie API client.

Primary use: injury reports and as a backup stats source.
Free tier: limited requests per minute.
Docs: https://docs.balldontlie.io/
"""
import httpx
from dataclasses import dataclass


@dataclass
class InjuryReport:
    player_name: str
    team: str
    status: str        # "Out", "Day-To-Day", "Questionable", "Probable"
    description: str
    return_date: str | None = None


class BDLClient:
    BASE_URL = "https://api.balldontlie.io/v1"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = api_key

    def get_injuries(self) -> list[InjuryReport]:
        """Get all current NBA player injuries."""
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self.BASE_URL}/player_injuries",
                    headers=self.headers,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])

                injuries = []
                for item in data:
                    player = item.get("player", {})
                    injuries.append(InjuryReport(
                        player_name=f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
                        team=item.get("team", {}).get("abbreviation", ""),
                        status=item.get("status", "Unknown"),
                        description=item.get("comment", ""),
                        return_date=item.get("return_date"),
                    ))
                return injuries
        except httpx.HTTPError:
            return []

    def get_season_averages(
        self, season: int = 2025, player_ids: list[int] | None = None
    ) -> list[dict]:
        """Get season averages. Optional filter by player IDs."""
        try:
            params: dict = {"season": season}
            if player_ids:
                params["player_ids[]"] = player_ids

            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self.BASE_URL}/season_averages",
                    headers=self.headers,
                    params=params,
                )
                resp.raise_for_status()
                return resp.json().get("data", [])
        except httpx.HTTPError:
            return []


def build_injury_dict(injuries: list[InjuryReport]) -> dict[str, InjuryReport]:
    """Build a lookup dict from player name -> injury report."""
    return {inj.player_name: inj for inj in injuries}


def format_injuries_report(injuries: list[InjuryReport], roster_names: list[str] | None = None) -> str:
    """Format injury report, optionally filtered to roster players."""
    if roster_names:
        # Fuzzy match: check if any roster name is contained in injury name or vice versa
        filtered = []
        for inj in injuries:
            for name in roster_names:
                # Match on last name at minimum
                inj_parts = inj.player_name.lower().split()
                name_parts = name.lower().split()
                if any(p in inj_parts for p in name_parts if len(p) > 2):
                    filtered.append(inj)
                    break
        injuries = filtered

    if not injuries:
        return "  No injuries found for roster players."

    lines = []
    lines.append(f"  {'Player':25s}  {'Team':>4s}  {'Status':15s}  Description")
    lines.append("  " + "-" * 80)
    for inj in sorted(injuries, key=lambda x: x.status):
        lines.append(
            f"  {inj.player_name:25s}  {inj.team:>4s}  {inj.status:15s}  {inj.description[:50]}"
        )
    return "\n".join(lines)
