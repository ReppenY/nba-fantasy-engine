"""
Rotation change detection.

Detects when a player's minutes are shifting significantly,
indicating a role change before it becomes obvious.

Signals:
- Minutes trending up (gaining role) → pickup candidate
- Minutes trending down (losing role) → sell/drop candidate
- Sudden spike (new starter) → urgent pickup
- Teammate injury effect on minutes
"""
from dataclasses import dataclass, field


@dataclass
class RotationAlert:
    """An alert about a significant rotation change."""
    player_name: str
    nba_team: str
    fantasy_team: str
    alert_type: str     # "minutes_surge", "minutes_drop", "new_starter", "losing_role", "opportunity"
    severity: str       # "high", "medium", "low"
    minutes_season: float
    minutes_recent: float
    minutes_change: float
    minutes_change_pct: float
    games_played: int
    description: str
    actionable: str     # What to do about it


def detect_rotation_changes(
    player_trends: dict,
    team_contexts: dict | None = None,
    threshold_pct: float = 15.0,
    threshold_abs: float = 3.0,
) -> list[RotationAlert]:
    """
    Detect significant rotation changes from player trends.

    Args:
        player_trends: dict of name -> PlayerTrend (from trends.py)
        team_contexts: dict of team -> NBATeamContext (for injury correlation)
        threshold_pct: Minimum % change to flag (default 15%)
        threshold_abs: Minimum absolute minutes change (default 3 min)
    """
    alerts = []

    for name, trend in player_trends.items():
        if trend.games_total < 10:
            continue

        season_min = trend.minutes_season
        recent_min = trend.minutes_recent
        if season_min <= 0:
            continue

        change = recent_min - season_min
        change_pct = (change / season_min) * 100

        # Check if significant
        if abs(change) < threshold_abs and abs(change_pct) < threshold_pct:
            continue

        # Determine alert type
        if change > 5 and change_pct > 25:
            alert_type = "new_starter"
            severity = "high"
            description = f"Minutes surged from {season_min:.0f} to {recent_min:.0f} ({change_pct:+.0f}%). Likely new starter."
            actionable = f"BUY/ADD {name} immediately — expanded role"
        elif change > threshold_abs:
            alert_type = "minutes_surge"
            severity = "medium"
            description = f"Minutes up from {season_min:.0f} to {recent_min:.0f} ({change_pct:+.0f}%)."
            actionable = f"Monitor {name} — role is growing"
        elif change < -5 and change_pct < -25:
            alert_type = "losing_role"
            severity = "high"
            description = f"Minutes dropped from {season_min:.0f} to {recent_min:.0f} ({change_pct:+.0f}%). May be losing starter role."
            actionable = f"SELL/DROP {name} — role shrinking fast"
        elif change < -threshold_abs:
            alert_type = "minutes_drop"
            severity = "medium"
            description = f"Minutes down from {season_min:.0f} to {recent_min:.0f} ({change_pct:+.0f}%)."
            actionable = f"Watch {name} — could be temporary or trend"
        else:
            continue

        # Check if correlated with teammate injury
        if team_contexts:
            # Look up player's NBA team from trend data
            nba_team = ""
            for ctx_team, ctx in team_contexts.items():
                if ctx.total_minutes_out > 10 and name in ctx.beneficiaries:
                    nba_team = ctx_team
                    if change > 0:
                        alert_type = "opportunity"
                        description += f" Benefiting from teammate injuries ({ctx.total_minutes_out:.0f} min freed)."
                        actionable = f"HOLD {name} — upside while teammates are out"
                    break

        alerts.append(RotationAlert(
            player_name=name,
            nba_team=nba_team,
            fantasy_team="",
            alert_type=alert_type,
            severity=severity,
            minutes_season=round(season_min, 1),
            minutes_recent=round(recent_min, 1),
            minutes_change=round(change, 1),
            minutes_change_pct=round(change_pct, 1),
            games_played=trend.games_total,
            description=description,
            actionable=actionable,
        ))

    # Sort by severity then absolute change
    severity_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 3), -abs(a.minutes_change)))
    return alerts
