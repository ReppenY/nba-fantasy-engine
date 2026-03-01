"""
Trade finder: auto-scan all teams for mutually beneficial trades.

For each opposing team, finds 1-for-1 and 2-for-1 trades where:
- My team improves in categories I need
- Their team improves in categories they need
- Salary is reasonably balanced
"""
import pandas as pd
from dataclasses import dataclass, field
from itertools import combinations

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights
from fantasy_engine.analytics.valuation import age_curve_multiplier


@dataclass
class TradeProposal:
    opponent_team: str
    give: list[str]
    receive: list[str]
    my_score: float        # How much this helps me (need-weighted)
    their_score: float     # How much this helps them (need-weighted)
    mutual_score: float    # min(my_score, their_score) — both sides benefit
    salary_diff: float     # Salary imbalance
    z_diff: float          # Raw z-score change for me
    improves_me: list[str] = field(default_factory=list)
    improves_them: list[str] = field(default_factory=list)


def find_trades(
    my_roster_z: pd.DataFrame,
    all_teams: dict,  # team_id -> {"name": str, "roster_z": DataFrame}
    my_team_id: str,
    punt_cats: list[str] | None = None,
    max_give: int = 1,
    max_receive: int = 1,
    min_mutual_score: float = 0.5,
    salary_tolerance: float = 15.0,
    top_n: int = 20,
) -> list[TradeProposal]:
    """
    Scan all teams for mutually beneficial trades.

    Args:
        my_roster_z: My roster with z-scores.
        all_teams: All teams' data from league_loader.
        my_team_id: My team ID.
        punt_cats: Categories I'm punting.
        max_give: Max players to give in one trade (1 or 2).
        max_receive: Max players to receive (1 or 2).
        min_mutual_score: Minimum benefit for both sides.
        salary_tolerance: Max salary imbalance allowed.
        top_n: Return top N proposals.
    """
    if punt_cats is None:
        punt_cats = []

    # My team profile and needs
    my_profile = analyze_team(my_roster_z)
    my_weights = get_need_weights(my_profile, punt_cats)

    proposals = []

    for team_id, team_data in all_teams.items():
        if team_id == my_team_id:
            continue

        opp_name = team_data["name"]
        opp_z = team_data.get("roster_z")
        if opp_z is None or opp_z.empty:
            continue

        # Opponent's profile and needs
        opp_profile = analyze_team(opp_z)
        opp_weights = get_need_weights(opp_profile)

        # Get tradeable players (skip very low value or injured)
        my_tradeable = my_roster_z[my_roster_z["games_played"] > 0].copy()
        opp_tradeable = opp_z[opp_z["games_played"] > 0].copy()

        if my_tradeable.empty or opp_tradeable.empty:
            continue

        # Try 1-for-1 trades
        for _, my_player in my_tradeable.iterrows():
            for _, opp_player in opp_tradeable.iterrows():
                proposal = _evaluate_proposal(
                    give=[my_player],
                    receive=[opp_player],
                    my_weights=my_weights,
                    opp_weights=opp_weights,
                    punt_cats=punt_cats,
                    opp_name=opp_name,
                    salary_tolerance=salary_tolerance,
                )
                if proposal and proposal.mutual_score >= min_mutual_score:
                    proposals.append(proposal)

        # Try 2-for-1 if requested (much more combos, limit scope)
        if max_give >= 2 and max_receive >= 1:
            # Only try with my bottom-half players as give candidates
            my_sorted = my_tradeable.sort_values("z_total")
            my_bottom = my_sorted.head(min(8, len(my_sorted)))
            opp_top = opp_tradeable.nlargest(min(10, len(opp_tradeable)), "z_total")

            for (_, p1), (_, p2) in combinations(my_bottom.iterrows(), 2):
                for _, opp_player in opp_top.iterrows():
                    proposal = _evaluate_proposal(
                        give=[p1, p2],
                        receive=[opp_player],
                        my_weights=my_weights,
                        opp_weights=opp_weights,
                        punt_cats=punt_cats,
                        opp_name=opp_name,
                        salary_tolerance=salary_tolerance,
                    )
                    if proposal and proposal.mutual_score >= min_mutual_score:
                        proposals.append(proposal)

    # Sort by mutual benefit
    proposals.sort(key=lambda p: p.mutual_score, reverse=True)
    return proposals[:top_n]


def _evaluate_proposal(
    give: list,
    receive: list,
    my_weights: dict,
    opp_weights: dict,
    punt_cats: list[str],
    opp_name: str,
    salary_tolerance: float,
) -> TradeProposal | None:
    """Evaluate a single trade proposal from both sides."""
    give_salary = sum(p.get("salary", 0) for p in give)
    recv_salary = sum(p.get("salary", 0) for p in receive)

    if abs(give_salary - recv_salary) > salary_tolerance:
        return None

    my_score = 0.0
    their_score = 0.0
    improves_me = []
    improves_them = []
    z_diff = 0.0

    for cat in ALL_CATS:
        z_col = f"z_{cat}"

        give_z = sum(p.get(z_col, 0) for p in give)
        recv_z = sum(p.get(z_col, 0) for p in receive)
        delta = recv_z - give_z

        # My perspective: gaining delta in this category
        my_w = my_weights.get(cat, 1.0)
        my_score += delta * my_w
        if delta > 0.2 and cat not in punt_cats:
            improves_me.append(cat)

        # Their perspective: gaining -delta (they get what I give, lose what I receive)
        opp_w = opp_weights.get(cat, 1.0)
        their_score += (-delta) * opp_w
        if -delta > 0.2:
            improves_them.append(cat)

        z_diff += delta

    # Schedule bonus: prefer receiving players with more games remaining
    sched_bonus = 0.0
    for p in receive:
        sched_bonus += p.get("schedule_adjusted_z", p.get("z_total", 0)) - p.get("z_total", 0)
    for p in give:
        sched_bonus -= p.get("schedule_adjusted_z", p.get("z_total", 0)) - p.get("z_total", 0)
    my_score += sched_bonus * 0.2

    # Both sides must benefit
    if my_score <= 0 or their_score <= 0:
        return None

    return TradeProposal(
        opponent_team=opp_name,
        give=[p.get("name", "?") for p in give],
        receive=[p.get("name", "?") for p in receive],
        my_score=round(my_score, 2),
        their_score=round(their_score, 2),
        mutual_score=round(min(my_score, their_score), 2),
        salary_diff=round(recv_salary - give_salary, 2),
        z_diff=round(z_diff, 2),
        improves_me=improves_me,
        improves_them=improves_them,
    )


def format_trade_finder_report(proposals: list[TradeProposal], top_n: int = 15) -> str:
    """Format trade proposals as a readable report."""
    lines = []
    lines.append("=" * 100)
    lines.append("TRADE FINDER — Mutually Beneficial Trade Proposals")
    lines.append("=" * 100)

    if not proposals:
        lines.append("  No mutually beneficial trades found.")
        return "\n".join(lines)

    for i, p in enumerate(proposals[:top_n], 1):
        give_str = " + ".join(p.give)
        recv_str = " + ".join(p.receive)
        lines.append(
            f"\n  #{i:2d}  {p.opponent_team}"
        )
        lines.append(
            f"      Give: {give_str}  -->  Receive: {recv_str}"
        )
        lines.append(
            f"      My benefit: {p.my_score:+.2f}  |  Their benefit: {p.their_score:+.2f}  "
            f"|  Mutual: {p.mutual_score:.2f}  |  Salary: {p.salary_diff:+.1f}"
        )
        if p.improves_me:
            lines.append(f"      Helps me in: {', '.join(p.improves_me)}")
        if p.improves_them:
            lines.append(f"      Helps them in: {', '.join(p.improves_them)}")

    return "\n".join(lines)
