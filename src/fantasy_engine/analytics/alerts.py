"""
Alerts system: detect actionable events.

Surfaces:
- Injured players on your roster
- Good free agents available
- Players trending up/down
- Trade opportunities from the trade finder
"""
from dataclasses import dataclass, field

import pandas as pd

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import analyze_team


@dataclass
class Alert:
    type: str       # "injury", "hot_fa", "trending_up", "trending_down", "trade_opportunity", "lineup"
    priority: str   # "high", "medium", "low"
    title: str
    detail: str
    player: str = ""
    action: str = ""  # Suggested action


def generate_alerts(
    my_roster_z: pd.DataFrame,
    free_agents_z: pd.DataFrame | None = None,
    injuries: list | None = None,
    trade_proposals: list | None = None,
) -> list[Alert]:
    """Generate all alerts based on current league state."""
    alerts = []

    # 1. Injury alerts
    if injuries:
        roster_names = set(my_roster_z["name"].str.lower())
        for inj in injuries:
            if inj.player_name.lower() in roster_names or any(
                inj.player_name.lower() in n for n in roster_names
            ):
                priority = "high" if inj.status in ("Out", "OFS") else "medium"
                alerts.append(Alert(
                    type="injury",
                    priority=priority,
                    title=f"{inj.player_name} is {inj.status}",
                    detail=inj.description or "No details",
                    player=inj.player_name,
                    action=f"Consider benching or finding a replacement",
                ))

    # 2. Lineup alerts — top players on bench
    active = my_roster_z[my_roster_z["status"] == "Act"]
    reserve = my_roster_z[my_roster_z["status"] == "Res"]
    if not active.empty and not reserve.empty:
        worst_active = active.nsmallest(1, "z_total").iloc[0]
        best_reserve = reserve.nlargest(1, "z_total").iloc[0]
        if best_reserve["z_total"] > worst_active["z_total"] + 1.0:
            alerts.append(Alert(
                type="lineup",
                priority="high",
                title=f"Better player on bench: {best_reserve['name']}",
                detail=(
                    f"{best_reserve['name']} (z:{best_reserve['z_total']:+.2f}) is on the bench "
                    f"while {worst_active['name']} (z:{worst_active['z_total']:+.2f}) is starting"
                ),
                player=best_reserve["name"],
                action=f"Start {best_reserve['name']}, bench {worst_active['name']}",
            ))

    # 3. Hot free agents
    if free_agents_z is not None and not free_agents_z.empty:
        profile = analyze_team(my_roster_z)
        weak_cats = [c for c, cp in profile.categories.items() if cp.strength == "weak"]

        hot_fas = free_agents_z[free_agents_z["z_total"] > 2.0].nlargest(5, "z_total")
        for _, fa in hot_fas.iterrows():
            # Check if they help weak categories
            helps = []
            for cat in weak_cats:
                if fa.get(f"z_{cat}", 0) > 0.3:
                    helps.append(cat)
            if helps:
                alerts.append(Alert(
                    type="hot_fa",
                    priority="medium",
                    title=f"FA {fa['name']} helps your weak cats",
                    detail=f"z:{fa['z_total']:+.2f}, helps: {', '.join(helps)}",
                    player=fa["name"],
                    action=f"Consider adding {fa['name']}",
                ))

    # 4. Trade opportunities
    if trade_proposals:
        for prop in trade_proposals[:3]:
            alerts.append(Alert(
                type="trade_opportunity",
                priority="medium",
                title=f"Trade with {prop.opponent_team}",
                detail=(
                    f"Give {' + '.join(prop.give)} for {' + '.join(prop.receive)}. "
                    f"Mutual benefit: {prop.mutual_score:.1f}"
                ),
                action=f"Propose trade to {prop.opponent_team}",
            ))

    # 5. Overpaid players
    for _, row in my_roster_z.iterrows():
        salary = row.get("salary", 0)
        z = row.get("z_total", 0)
        if salary >= 10 and z < 0:
            alerts.append(Alert(
                type="overpaid",
                priority="low",
                title=f"{row['name']} is overpaid",
                detail=f"${salary:.0f} salary but z:{z:+.2f}. Consider trading.",
                player=row["name"],
                action=f"Look for trade partners for {row['name']}",
            ))

    # 6. Rotation change alerts (from trends)
    try:
        from fantasy_engine.analytics.rotation_alerts import detect_rotation_changes
        # Need to pass trends — check if available from the calling context
        # This will be populated if state has player_trends
    except Exception:
        pass

    # 7. Strategy fit alerts
    try:
        from fantasy_engine.analytics.category_analysis import _strategy_punt_cache
        if _strategy_punt_cache and free_agents_z is not None and not free_agents_z.empty:
            target_cats = [c for c in ALL_CATS if c not in _strategy_punt_cache]
            for _, fa in free_agents_z.nlargest(3, "z_total").iterrows():
                fa_fits = [c for c in target_cats if fa.get(f"z_{c}", 0) > 1.0]
                if len(fa_fits) >= 2:
                    alerts.append(Alert(
                        type="strategy_fit",
                        priority="medium",
                        title=f"FA {fa['name']} fits your build ({', '.join(fa_fits)})",
                        detail=f"z:{fa.get('z_total', 0):+.1f}. Matches your target categories.",
                        player=fa.get("name", ""),
                        action=f"Target {fa['name']} in FA auction",
                    ))
    except Exception:
        pass

    # 8. Minutes trend alerts for roster players
    for _, row in my_roster_z.iterrows():
        min_trend = row.get("minutes_trend", 0)
        if min_trend and not pd.isna(min_trend):
            name = row.get("name", "")
            if min_trend > 4:
                alerts.append(Alert(
                    type="minutes_up",
                    priority="medium",
                    title=f"{name} gaining {min_trend:.0f} min/game recently",
                    detail=f"Minutes trending up — role expanding. Production should follow.",
                    player=name,
                    action=f"Hold/start {name} — rising value",
                ))
            elif min_trend < -4:
                alerts.append(Alert(
                    type="minutes_down",
                    priority="medium",
                    title=f"{name} losing {abs(min_trend):.0f} min/game recently",
                    detail=f"Minutes trending down — role shrinking.",
                    player=name,
                    action=f"Monitor {name} — consider benching or trading",
                ))

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: priority_order.get(a.priority, 3))
    return alerts
