"""
Trade evaluator for H2H 9-Cat dynasty salary cap leagues.

Evaluates trades by:
1. Per-category z-score delta
2. Need-weighted scoring (weak categories matter more)
3. Salary cap impact
4. Dynasty value overlay (age + contract)
5. Combined verdict
"""
from dataclasses import dataclass, field

import pandas as pd

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import (
    analyze_team,
    get_need_weights,
)
from fantasy_engine.analytics.valuation import age_curve_multiplier


@dataclass
class TradeSide:
    players: list[str]
    total_salary: float
    total_z: float
    z_per_cat: dict[str, float] = field(default_factory=dict)
    dynasty_value: float = 0.0


@dataclass
class TradeEvaluation:
    give: TradeSide
    receive: TradeSide
    z_diff: float                    # Net z-score change (positive = good)
    weighted_score: float            # Need-weighted score
    cat_impact: dict[str, float] = field(default_factory=dict)
    salary_impact: float = 0.0       # Net salary change
    cap_room_after: float = 0.0
    improves_cats: list[str] = field(default_factory=list)
    hurts_cats: list[str] = field(default_factory=list)
    dynasty_diff: float = 0.0
    combined_score: float = 0.0
    verdict: str = "neutral"
    explanation: str = ""


def evaluate_trade(
    give_names: list[str],
    receive_names: list[str],
    roster_z_df: pd.DataFrame,
    salary_cap: float = 200.0,
    punt_cats: list[str] | None = None,
    dynasty_weight: float = 0.3,
) -> TradeEvaluation:
    """
    Evaluate a trade proposal.

    Args:
        give_names: Player names I'm giving away.
        receive_names: Player names I'm receiving.
        roster_z_df: DataFrame with z-scores, salary, age, years_remaining
                     for all relevant players (my roster + trade targets).
        salary_cap: League salary cap.
        punt_cats: Categories being punted (excluded from evaluation).
        dynasty_weight: How much to weight dynasty value (0-1). 0.3 = 30%.

    Returns:
        TradeEvaluation with full breakdown and verdict.
    """
    if punt_cats is None:
        punt_cats = []

    # Look up players (case-insensitive)
    names_lower = roster_z_df["name"].str.lower()
    give_lower = [n.lower().strip() for n in give_names]
    recv_lower = [n.lower().strip() for n in receive_names]

    give_df = roster_z_df[names_lower.isin(give_lower)]
    recv_df = roster_z_df[names_lower.isin(recv_lower)]

    # Try partial matching for unmatched names
    if len(give_df) < len(give_names):
        for gn in give_lower:
            if not names_lower.isin([gn]).any():
                partial = roster_z_df[names_lower.str.contains(gn, na=False)]
                if not partial.empty:
                    give_df = pd.concat([give_df, partial.head(1)])

    if len(recv_df) < len(receive_names):
        for rn in recv_lower:
            if not names_lower.isin([rn]).any():
                partial = roster_z_df[names_lower.str.contains(rn, na=False)]
                if not partial.empty:
                    recv_df = pd.concat([recv_df, partial.head(1)])

    if len(give_df) == 0:
        raise ValueError(f"Players not found in roster: {give_names}")
    if len(recv_df) == 0:
        raise ValueError(f"Players not found: {receive_names}")

    # Resolve actual names for downstream use
    give_names = give_df["name"].tolist()
    receive_names = recv_df["name"].tolist()

    # Build team profile (excluding players being traded away)
    remaining_roster = roster_z_df[~names_lower.isin(give_lower)]
    team_profile = analyze_team(remaining_roster)
    need_weights = get_need_weights(team_profile, punt_cats)

    # Per-category impact
    cat_impact = {}
    weighted_score = 0.0
    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col not in roster_z_df.columns:
            continue
        delta = recv_df[z_col].sum() - give_df[z_col].sum()
        cat_impact[cat] = round(delta, 3)
        weighted_score += delta * need_weights.get(cat, 1.0)

    # Salary analysis
    give_salary = give_df["salary"].sum()
    recv_salary = recv_df["salary"].sum()
    salary_impact = recv_salary - give_salary
    current_total_salary = roster_z_df["salary"].sum()
    cap_after = salary_cap - (current_total_salary + salary_impact)

    # Dynasty value
    give_dynasty = _compute_dynasty_total(give_df)
    recv_dynasty = _compute_dynasty_total(recv_df)
    dynasty_diff = recv_dynasty - give_dynasty

    # Z-score diff
    z_diff = recv_df["z_total"].sum() - give_df["z_total"].sum()

    # Schedule bonus: if receiving players have better schedule
    schedule_bonus = 0.0
    for col in ["schedule_adjusted_z", "games_remaining", "playoff_games"]:
        if col in roster_z_df.columns:
            give_val = give_df[col].sum() if col in give_df.columns else 0
            recv_val = recv_df[col].sum() if col in recv_df.columns else 0
            if col == "schedule_adjusted_z":
                schedule_bonus += (recv_val - give_val) * 0.2
            elif col == "playoff_games":
                schedule_bonus += (recv_val - give_val) * 0.1

    # Combined score
    current_weight = 1.0 - dynasty_weight
    combined = current_weight * weighted_score + dynasty_weight * dynasty_diff + schedule_bonus

    # Verdict
    if combined > 3.0:
        verdict = "strong_accept"
    elif combined > 1.0:
        verdict = "accept"
    elif combined > 0.0:
        verdict = "slight_accept"
    elif combined > -1.0:
        verdict = "slight_decline"
    elif combined > -3.0:
        verdict = "decline"
    else:
        verdict = "strong_decline"

    # Build sides
    give_side = TradeSide(
        players=give_names,
        total_salary=round(give_salary, 2),
        total_z=round(give_df["z_total"].sum(), 2),
        z_per_cat={cat: round(give_df[f"z_{cat}"].sum(), 2) for cat in ALL_CATS if f"z_{cat}" in give_df.columns},
        dynasty_value=round(give_dynasty, 2),
    )
    recv_side = TradeSide(
        players=receive_names,
        total_salary=round(recv_salary, 2),
        total_z=round(recv_df["z_total"].sum(), 2),
        z_per_cat={cat: round(recv_df[f"z_{cat}"].sum(), 2) for cat in ALL_CATS if f"z_{cat}" in recv_df.columns},
        dynasty_value=round(recv_dynasty, 2),
    )

    improves = [c for c, d in cat_impact.items() if d > 0.1 and c not in punt_cats]
    hurts = [c for c, d in cat_impact.items() if d < -0.1 and c not in punt_cats]

    # Position feasibility check
    position_warning = ""
    try:
        from fantasy_engine.analytics.position_feasibility import check_trade_feasibility
        # Build receive positions from the data
        recv_positions = {}
        for _, row in recv_df.iterrows():
            recv_positions[row.get("name", "")] = row.get("positions", "")
        feasibility = check_trade_feasibility(roster_z_df, give_names, receive_names, recv_positions)
        if not feasibility.is_feasible:
            position_warning = "WARNING: This trade leaves you unable to fill all position slots!"
            combined -= 3.0  # Heavy penalty
        elif feasibility.warnings:
            position_warning = feasibility.warnings[0]
            combined -= 0.5  # Mild penalty
    except Exception:
        pass

    # Schedule context for explanation
    sched_ctx = {}
    for label, df_side in [("give", give_df), ("receive", recv_df)]:
        for col in ["games_remaining", "playoff_games", "consistency_rating"]:
            if col in df_side.columns:
                sched_ctx[f"{label}_{col}"] = df_side[col].mean()

    explanation = _build_explanation(
        give_names, receive_names, z_diff, cat_impact,
        salary_impact, dynasty_diff, improves, hurts, verdict, punt_cats,
        sched_ctx,
    )
    if position_warning:
        explanation = position_warning + "\n\n" + explanation

    return TradeEvaluation(
        give=give_side,
        receive=recv_side,
        z_diff=round(z_diff, 3),
        weighted_score=round(weighted_score, 3),
        cat_impact=cat_impact,
        salary_impact=round(salary_impact, 2),
        cap_room_after=round(cap_after, 2),
        improves_cats=improves,
        hurts_cats=hurts,
        dynasty_diff=round(dynasty_diff, 3),
        combined_score=round(combined, 3),
        verdict=verdict,
        explanation=explanation,
    )


def _compute_dynasty_total(df: pd.DataFrame) -> float:
    """Compute total dynasty value for a set of players."""
    total = 0.0
    for _, row in df.iterrows():
        age = int(row.get("age", 28))
        yrs = int(row.get("years_remaining", 1))
        z = row.get("z_total", 0.0)
        af = age_curve_multiplier(age)
        contract_factor = min(1.5, yrs / 3.0)
        total += z * af * contract_factor
    return total


def _build_explanation(
    give_names, receive_names, z_diff, cat_impact,
    salary_impact, dynasty_diff, improves, hurts, verdict, punt_cats,
    sched_ctx=None,
) -> str:
    """Build a human-readable trade explanation."""
    lines = []

    give_str = " + ".join(give_names)
    recv_str = " + ".join(receive_names)
    lines.append(f"Trade: {give_str}  -->  {recv_str}")
    lines.append("")

    # Verdict headline
    verdict_labels = {
        "strong_accept": "STRONG ACCEPT - This trade significantly helps your team",
        "accept": "ACCEPT - This trade is clearly in your favor",
        "slight_accept": "SLIGHT ACCEPT - Marginal improvement, worth considering",
        "slight_decline": "SLIGHT DECLINE - Marginal downgrade, but close",
        "decline": "DECLINE - This trade hurts your team",
        "strong_decline": "STRONG DECLINE - This trade significantly hurts your team",
    }
    lines.append(f"Verdict: {verdict_labels.get(verdict, verdict)}")
    lines.append("")

    # Z-score impact
    direction = "gain" if z_diff > 0 else "lose"
    lines.append(f"Overall Z-score: {direction} {abs(z_diff):.2f} total value")

    # Category impact
    if improves:
        lines.append(f"Improves: {', '.join(improves)}")
    if hurts:
        lines.append(f"Hurts: {', '.join(hurts)}")
    if punt_cats:
        lines.append(f"(Ignoring punted cats: {', '.join(punt_cats)})")

    # Salary
    if salary_impact > 0:
        lines.append(f"Salary: +${salary_impact:.1f} (costs more cap)")
    elif salary_impact < 0:
        lines.append(f"Salary: -${abs(salary_impact):.1f} (saves cap)")

    # Dynasty
    if dynasty_diff > 1:
        lines.append(f"Dynasty: +{dynasty_diff:.1f} (better long-term value)")
    elif dynasty_diff < -1:
        lines.append(f"Dynasty: {dynasty_diff:.1f} (worse long-term value)")

    # Schedule context
    if sched_ctx:
        give_games = sched_ctx.get("give_games_remaining", 0)
        recv_games = sched_ctx.get("receive_games_remaining", 0)
        give_playoff = sched_ctx.get("give_playoff_games", 0)
        recv_playoff = sched_ctx.get("receive_playoff_games", 0)
        give_cons = sched_ctx.get("give_consistency_rating", 0)
        recv_cons = sched_ctx.get("receive_consistency_rating", 0)

        if recv_games > give_games + 2:
            lines.append(f"Schedule: +{recv_games - give_games:.0f} more games remaining")
        elif give_games > recv_games + 2:
            lines.append(f"Schedule: {recv_games - give_games:.0f} fewer games remaining")

        if recv_playoff > give_playoff + 1:
            lines.append(f"Playoff schedule: +{recv_playoff - give_playoff:.0f} more playoff games")

        if recv_cons > give_cons + 0.15:
            lines.append(f"Consistency: receiving more consistent players")
        elif give_cons > recv_cons + 0.15:
            lines.append(f"Consistency: receiving more volatile players")

    return "\n".join(lines)


def format_trade_report(evaluation: TradeEvaluation) -> str:
    """Format a full trade evaluation report."""
    lines = []
    lines.append("=" * 90)
    lines.append("TRADE EVALUATION")
    lines.append("=" * 90)
    lines.append("")
    lines.append(evaluation.explanation)
    lines.append("")

    # Side-by-side category comparison
    lines.append("-" * 90)
    lines.append(
        f"  {'Category':>8s}  {'Give':>8s}  {'Receive':>8s}  {'Delta':>8s}  {'Impact':10s}"
    )
    lines.append("-" * 90)

    for cat in ALL_CATS:
        give_z = evaluation.give.z_per_cat.get(cat, 0)
        recv_z = evaluation.receive.z_per_cat.get(cat, 0)
        delta = evaluation.cat_impact.get(cat, 0)

        if delta > 0.1:
            impact = "++ BETTER"
        elif delta < -0.1:
            impact = "-- WORSE"
        else:
            impact = "   ~same"

        lines.append(
            f"  {cat:>8s}  {give_z:+8.2f}  {recv_z:+8.2f}  {delta:+8.2f}  {impact}"
        )

    lines.append("-" * 90)
    lines.append(
        f"  {'TOTAL':>8s}  {evaluation.give.total_z:+8.2f}  "
        f"{evaluation.receive.total_z:+8.2f}  {evaluation.z_diff:+8.2f}"
    )

    lines.append("")
    lines.append(f"  Salary: ${evaluation.give.total_salary:.1f} out, "
                 f"${evaluation.receive.total_salary:.1f} in "
                 f"(net: {evaluation.salary_impact:+.1f})")
    lines.append(f"  Cap room after: ${evaluation.cap_room_after:.1f}")
    lines.append(f"  Dynasty value: {evaluation.give.dynasty_value:+.2f} out, "
                 f"{evaluation.receive.dynasty_value:+.2f} in "
                 f"(net: {evaluation.dynasty_diff:+.2f})")
    lines.append(f"  Combined score: {evaluation.combined_score:+.2f}")
    lines.append(f"  Verdict: {evaluation.verdict.upper()}")

    return "\n".join(lines)
