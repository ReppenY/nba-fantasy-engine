"""
Trade simulator: explore trades across all 12 teams.

Given a player you want to acquire (or sell), scans every team
to find realistic trade packages that balance z-score, salary,
and category needs for both sides.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from itertools import combinations

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights
from fantasy_engine.analytics.valuation import age_curve_multiplier


@dataclass
class TradePackage:
    opponent_team: str
    opponent_team_id: str
    i_give: list[str]
    i_receive: list[str]
    my_z_change: float
    their_z_change: float
    my_need_score: float
    their_need_score: float
    salary_out: float
    salary_in: float
    salary_diff: float
    my_cat_changes: dict[str, float] = field(default_factory=dict)
    feasibility: str = ""  # "highly_feasible", "feasible", "stretch"


def simulate_acquire(
    target_name: str,
    my_roster_z: pd.DataFrame,
    all_teams: dict,
    my_team_id: str,
    punt_cats: list[str] | None = None,
    max_give: int = 2,
    salary_tolerance: float = 20.0,
) -> list[TradePackage]:
    """
    Find trade packages to acquire a specific player.

    Scans all teams to find who owns the target, then generates
    trade packages using my players that the other team would want.
    """
    if punt_cats is None:
        punt_cats = []

    # Find who owns the target
    target_team_id = None
    target_row = None
    for team_id, team_data in all_teams.items():
        if team_id == my_team_id:
            continue
        roster_z = team_data.get("roster_z")
        if roster_z is None:
            continue
        match = roster_z[roster_z["name"].str.lower().str.contains(target_name.lower())]
        if not match.empty:
            target_team_id = team_id
            target_row = match.iloc[0]
            break

    if target_team_id is None:
        return []

    opp_data = all_teams[target_team_id]
    opp_name = opp_data["name"]
    opp_z = opp_data["roster_z"]

    # Their needs
    opp_profile = analyze_team(opp_z)
    opp_weights = get_need_weights(opp_profile)

    # My needs
    my_profile = analyze_team(my_roster_z)
    my_weights = get_need_weights(my_profile, punt_cats)

    target_salary = target_row.get("salary", 0)
    target_z = target_row.get("z_total", 0)

    # Generate packages: which of my players could I offer?
    my_tradeable = my_roster_z[
        (my_roster_z["games_played"] > 0) &
        (my_roster_z["z_total"] > -5)  # Don't offer complete duds
    ].copy()

    packages = []

    # 1-for-1 trades
    for _, my_player in my_tradeable.iterrows():
        pkg = _build_package(
            give_players=[my_player],
            receive_players=[target_row],
            my_weights=my_weights,
            opp_weights=opp_weights,
            opp_name=opp_name,
            opp_team_id=target_team_id,
            salary_tolerance=salary_tolerance,
            punt_cats=punt_cats,
        )
        if pkg:
            packages.append(pkg)

    # 2-for-1 trades
    if max_give >= 2:
        for (_, p1), (_, p2) in combinations(my_tradeable.iterrows(), 2):
            combined_salary = p1.get("salary", 0) + p2.get("salary", 0)
            if abs(combined_salary - target_salary) > salary_tolerance:
                continue
            pkg = _build_package(
                give_players=[p1, p2],
                receive_players=[target_row],
                my_weights=my_weights,
                opp_weights=opp_weights,
                opp_name=opp_name,
                opp_team_id=target_team_id,
                salary_tolerance=salary_tolerance,
                punt_cats=punt_cats,
            )
            if pkg:
                packages.append(pkg)

    # Sort by feasibility (both sides benefit)
    packages.sort(key=lambda p: min(p.my_need_score, p.their_need_score), reverse=True)
    return packages[:20]


def simulate_sell(
    sell_name: str,
    my_roster_z: pd.DataFrame,
    all_teams: dict,
    my_team_id: str,
    punt_cats: list[str] | None = None,
    salary_tolerance: float = 20.0,
) -> list[TradePackage]:
    """
    Find trade packages to sell a specific player from my roster.

    Scans all teams to find who would want this player based on
    their category needs, then generates return packages.
    """
    if punt_cats is None:
        punt_cats = []

    sell_row = my_roster_z[my_roster_z["name"].str.lower().str.contains(sell_name.lower())]
    if sell_row.empty:
        return []
    sell_row = sell_row.iloc[0]

    my_profile = analyze_team(my_roster_z)
    my_weights = get_need_weights(my_profile, punt_cats)

    sell_salary = sell_row.get("salary", 0)

    packages = []

    for team_id, team_data in all_teams.items():
        if team_id == my_team_id:
            continue

        opp_z = team_data.get("roster_z")
        if opp_z is None or opp_z.empty:
            continue

        opp_name = team_data["name"]
        opp_profile = analyze_team(opp_z)
        opp_weights = get_need_weights(opp_profile)

        # Find their players I might want
        opp_tradeable = opp_z[opp_z["games_played"] > 0]

        for _, opp_player in opp_tradeable.iterrows():
            if abs(opp_player.get("salary", 0) - sell_salary) > salary_tolerance:
                continue

            pkg = _build_package(
                give_players=[sell_row],
                receive_players=[opp_player],
                my_weights=my_weights,
                opp_weights=opp_weights,
                opp_name=opp_name,
                opp_team_id=team_id,
                salary_tolerance=salary_tolerance,
                punt_cats=punt_cats,
            )
            if pkg and pkg.their_need_score > 0:
                packages.append(pkg)

    packages.sort(key=lambda p: p.my_need_score, reverse=True)
    return packages[:20]


def _build_package(
    give_players, receive_players,
    my_weights, opp_weights,
    opp_name, opp_team_id,
    salary_tolerance, punt_cats,
) -> TradePackage | None:
    """Build and score a trade package."""
    salary_out = sum(p.get("salary", 0) for p in give_players)
    salary_in = sum(p.get("salary", 0) for p in receive_players)

    if abs(salary_out - salary_in) > salary_tolerance:
        return None

    my_score = 0.0
    their_score = 0.0
    my_z_change = 0.0
    their_z_change = 0.0
    cat_changes = {}

    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        give_z = sum(p.get(z_col, 0) for p in give_players)
        recv_z = sum(p.get(z_col, 0) for p in receive_players)
        delta = recv_z - give_z

        cat_changes[cat] = round(delta, 2)
        my_score += delta * my_weights.get(cat, 1.0)
        their_score += (-delta) * opp_weights.get(cat, 1.0)
        my_z_change += delta
        their_z_change -= delta

    # Consistency bonus: prefer receiving consistent players
    give_cons = np.mean([p.get("consistency_rating", 0.5) for p in give_players])
    recv_cons = np.mean([p.get("consistency_rating", 0.5) for p in receive_players])
    if recv_cons > give_cons:
        my_score += (recv_cons - give_cons) * 1.5  # Consistency premium

    # Schedule bonus
    give_sched = sum(p.get("schedule_adjusted_z", p.get("z_total", 0)) for p in give_players)
    recv_sched = sum(p.get("schedule_adjusted_z", p.get("z_total", 0)) for p in receive_players)
    give_raw = sum(p.get("z_total", 0) for p in give_players)
    recv_raw = sum(p.get("z_total", 0) for p in receive_players)
    sched_bonus = (recv_sched - recv_raw) - (give_sched - give_raw)
    my_score += sched_bonus * 0.2

    if my_score <= 0 and their_score <= 0:
        return None

    # Feasibility
    if my_score > 1 and their_score > 1:
        feasibility = "highly_feasible"
    elif my_score > 0 and their_score > 0:
        feasibility = "feasible"
    else:
        feasibility = "stretch"

    return TradePackage(
        opponent_team=opp_name,
        opponent_team_id=opp_team_id,
        i_give=[p.get("name", "?") for p in give_players],
        i_receive=[p.get("name", "?") for p in receive_players],
        my_z_change=round(my_z_change, 2),
        their_z_change=round(their_z_change, 2),
        my_need_score=round(my_score, 2),
        their_need_score=round(their_score, 2),
        salary_out=round(salary_out, 1),
        salary_in=round(salary_in, 1),
        salary_diff=round(salary_in - salary_out, 1),
        my_cat_changes=cat_changes,
        feasibility=feasibility,
    )
