"""
Keeper optimizer for dynasty salary cap leagues.

Decides which expiring players to re-sign given:
- Their z-score production
- Their salary vs auction value (are they a bargain?)
- Age trajectory (dynasty lens)
- Injury status (season-ending = risky to keep at full salary)
- Cap room constraints
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class KeeperDecision:
    name: str
    salary: float
    auction_value: float       # What they'd cost at auction
    surplus: float             # auction_value - salary (+ = bargain to keep)
    z_total: float
    age: int
    years_remaining: int
    contract: str
    is_injured: bool
    injury_return: str
    decision: str              # "definitely_keep", "keep", "let_walk", "trade_before_expiry"
    reason: str
    priority: int              # 1 = highest priority keep


@dataclass
class KeeperPlan:
    keeps: list[KeeperDecision]
    lets_walk: list[KeeperDecision]
    total_kept_salary: float
    cap_room_after: float
    roster_spots_opened: int


def optimize_keepers(
    roster_z_df: pd.DataFrame,
    auction_values: dict[str, float],
    injuries: list | None = None,
    salary_cap: float = 200.0,
    max_roster: int = 36,
) -> KeeperPlan:
    """
    Optimize keeper decisions for expiring contracts.

    For each expiring player, compute:
    - Surplus = auction_value - salary (positive = bargain)
    - Adjusted for injury risk
    - Adjusted for age trajectory

    Then greedily keep players with highest surplus until cap is full.
    """
    from fantasy_engine.analytics.valuation import age_curve_multiplier

    # Build injury lookup
    injury_map: dict[str, dict] = {}
    if injuries:
        for inj in injuries:
            name = inj.player_name if hasattr(inj, 'player_name') else inj.get("player", "")
            ret = inj.return_date if hasattr(inj, 'return_date') else inj.get("return_date", "")
            status = inj.status if hasattr(inj, 'status') else inj.get("status", "")
            injury_map[name.lower()] = {"return_date": ret, "status": status}

    # Split expiring vs committed
    expiring_decisions = []
    committed_salary = 0.0

    for _, row in roster_z_df.iterrows():
        name = row.get("name", "")
        salary = row.get("salary", 0)
        yrs = int(row.get("years_remaining", 1))
        # Use schedule-adjusted z if available, otherwise raw
        z_total = row.get("schedule_adjusted_z", row.get("z_total", 0))
        if z_total == 0:
            z_total = row.get("z_total", 0)
        age = int(row.get("age", 0))
        contract = row.get("contract", "")
        consistency = row.get("consistency_rating", 0.5)

        if yrs > 1:
            committed_salary += salary
            continue

        # This player is expiring
        av = auction_values.get(name, 1.0)
        surplus = av - salary

        # Position scarcity: scarce-position players are harder to replace
        try:
            from fantasy_engine.analytics.positional_scarcity import get_pos_scarcity_bonus
            surplus += get_pos_scarcity_bonus(name) * 2.0
        except Exception:
            pass

        # Check injury
        inj_info = injury_map.get(name.lower(), {})
        is_injured = bool(inj_info)
        injury_return = inj_info.get("return_date", "")

        # Season-ending injury = big risk
        if injury_return and "10-01" in injury_return:
            surplus *= 0.3  # Heavily discount season-ending injuries
            is_injured = True

        # Age adjustment
        if age > 0:
            af = age_curve_multiplier(age)
            if af < 0.6:
                surplus *= 0.5  # Old players less worth keeping

        # Minutes trend adjustment
        min_trend = row.get("minutes_trend", 0)
        if min_trend and not pd.isna(min_trend) and min_trend > 3:
            surplus *= 1.2  # Gaining minutes = more valuable
        elif min_trend and not pd.isna(min_trend) and min_trend < -3:
            surplus *= 0.8  # Losing minutes = less valuable

        # Decision
        if surplus > 5 and z_total > 3:
            decision = "definitely_keep"
            reason = f"Elite bargain: worth ${av:.0f} at auction, paying ${salary:.0f}"
        elif surplus > 2 and z_total > 0:
            decision = "keep"
            reason = f"Good value: auction ${av:.0f} vs salary ${salary:.0f}"
        elif surplus > 0 and z_total > 0 and salary <= 2:
            decision = "keep"
            reason = f"Cheap positive contributor"
        elif z_total < -2:
            decision = "let_walk"
            reason = f"Negative production (z:{z_total:+.1f})"
        elif is_injured and "10-01" in injury_return:
            decision = "let_walk"
            reason = f"Season-ending injury, too risky at ${salary:.0f}"
        elif surplus < -3:
            decision = "trade_before_expiry"
            reason = f"Overpaid: worth ${av:.0f} but paying ${salary:.0f}"
        else:
            decision = "let_walk"
            reason = f"Marginal value (z:{z_total:+.1f}, surplus:{surplus:+.1f})"

        expiring_decisions.append(KeeperDecision(
            name=name,
            salary=salary,
            auction_value=round(av, 1),
            surplus=round(surplus, 1),
            z_total=round(z_total, 2),
            age=age,
            years_remaining=yrs,
            contract=contract,
            is_injured=is_injured,
            injury_return=injury_return[:10] if injury_return else "",
            decision=decision,
            reason=reason,
            priority=0,
        ))

    # Sort by surplus (best keeps first)
    expiring_decisions.sort(key=lambda d: d.surplus, reverse=True)

    # Assign priorities
    for i, d in enumerate(expiring_decisions):
        d.priority = i + 1

    # Split keeps vs walks
    keeps = [d for d in expiring_decisions if d.decision in ("definitely_keep", "keep")]
    lets_walk = [d for d in expiring_decisions if d.decision in ("let_walk", "trade_before_expiry")]

    # Check cap feasibility
    kept_salary = sum(d.salary for d in keeps)
    total_salary = committed_salary + kept_salary
    cap_room = salary_cap - total_salary
    roster_spots = len(lets_walk)

    # If over cap, drop lowest-surplus keeps
    while cap_room < 0 and keeps:
        dropped = keeps.pop()
        dropped.decision = "let_walk"
        dropped.reason += " (cap casualty)"
        lets_walk.insert(0, dropped)
        kept_salary -= dropped.salary
        total_salary -= dropped.salary
        cap_room = salary_cap - total_salary
        roster_spots += 1

    return KeeperPlan(
        keeps=keeps,
        lets_walk=lets_walk,
        total_kept_salary=round(committed_salary + kept_salary, 1),
        cap_room_after=round(cap_room, 1),
        roster_spots_opened=roster_spots,
    )
