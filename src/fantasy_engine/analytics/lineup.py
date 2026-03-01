"""
Weekly lineup optimizer for H2H 9-Cat leagues.

Solves the assignment problem: which players should be active
to maximize category competitiveness for the week?

Considers:
- Position eligibility (each player fits certain slots)
- Games this week per player (schedule-dependent)
- Injuries (skip injured players)
- Category needs (weight z-scores by team needs)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from scipy.optimize import linear_sum_assignment

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights


# Default position slots for a typical Fantrax 9-cat league
DEFAULT_SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "Flx", "Flx", "Flx"]

# Position eligibility mapping: which positions can fill which slots
SLOT_ELIGIBILITY = {
    "PG": ["PG"],
    "SG": ["SG"],
    "SF": ["SF"],
    "PF": ["PF"],
    "C": ["C"],
    "G": ["PG", "SG"],
    "F": ["SF", "PF"],
    "Flx": ["PG", "SG", "SF", "PF", "C"],
}


@dataclass
class LineupSlot:
    slot: str
    player_name: str
    positions: str
    games_this_week: int
    weekly_z: float


@dataclass
class LineupRecommendation:
    active: list[LineupSlot] = field(default_factory=list)
    bench: list[str] = field(default_factory=list)
    total_weekly_z: float = 0.0
    games_by_player: dict[str, int] = field(default_factory=dict)
    category_projections: dict[str, float] = field(default_factory=dict)


def optimize_lineup(
    roster_z_df: pd.DataFrame,
    slots: list[str] | None = None,
    games_map: dict[str, int] | None = None,
    injured_players: list[str] | None = None,
    punt_cats: list[str] | None = None,
) -> LineupRecommendation:
    """
    Optimize weekly lineup via linear assignment.

    Args:
        roster_z_df: Full roster DataFrame with z-scores, name, positions.
        slots: Position slots to fill. Defaults to standard 10-slot lineup.
        games_map: Player name -> games this week. Defaults to 4 for all.
        injured_players: Player names to exclude.
        punt_cats: Categories being punted (excluded from z-score weighting).

    Returns:
        LineupRecommendation with optimal active lineup and bench.
    """
    if slots is None:
        slots = DEFAULT_SLOTS
    if injured_players is None:
        injured_players = []
    if punt_cats is None:
        punt_cats = []
    default_games = 4

    # Filter out injured players
    available = roster_z_df[~roster_z_df["name"].isin(injured_players)].copy()

    if len(available) == 0:
        return LineupRecommendation()

    # Compute need-weighted z-score for each player
    profile = analyze_team(available)
    weights = get_need_weights(profile, punt_cats)

    # Weighted z per game, incorporating consistency
    available = available.copy()
    weighted_z = np.zeros(len(available))
    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col in available.columns:
            w = weights.get(cat, 1.0)
            weighted_z += available[z_col].values * w

    # Apply consistency factor: reliable players get a bonus
    if "consistency_rating" in available.columns:
        consistency_factor = 0.7 + 0.3 * available["consistency_rating"].fillna(0.5).values
        weighted_z = weighted_z * consistency_factor

    # Minutes trend bonus: players gaining minutes are more valuable
    if "minutes_trend" in available.columns:
        min_trend = available["minutes_trend"].fillna(0).values
        # +3 min trend = +10% bonus, -3 min trend = -10% penalty
        trend_factor = 1.0 + (min_trend / 30)
        weighted_z = weighted_z * trend_factor.clip(0.8, 1.2)

    available["weighted_z"] = weighted_z

    # Scale by games this week — use real schedule if available
    if games_map:
        available["games_week"] = available["name"].apply(lambda n: games_map.get(n, default_games))
    elif "games_this_week" in available.columns:
        available["games_week"] = available["games_this_week"].fillna(default_games).astype(int)
    else:
        available["games_week"] = default_games
    available["weekly_z"] = available["weighted_z"] * available["games_week"] / default_games

    # Build cost matrix for linear assignment
    n_players = len(available)
    n_slots = len(slots)

    # Cost = negative weekly_z (since linear_sum_assignment minimizes)
    # Set high cost (1000) for ineligible slot assignments
    cost_matrix = np.full((n_players, n_slots), 1000.0)

    player_positions = available["positions"].fillna("").values
    player_names = available["name"].values
    weekly_z_values = available["weekly_z"].values

    for i in range(n_players):
        player_pos_list = [p.strip() for p in str(player_positions[i]).split(",")]
        for j, slot in enumerate(slots):
            eligible_pos = SLOT_ELIGIBILITY.get(slot, [slot])
            if any(p in eligible_pos for p in player_pos_list):
                cost_matrix[i, j] = -weekly_z_values[i]

    # Solve assignment (need n_players >= n_slots)
    if n_players >= n_slots:
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
    else:
        # Fewer players than slots — fill what we can
        row_ind, col_ind = linear_sum_assignment(cost_matrix[:, :n_players].T)
        row_ind, col_ind = col_ind, row_ind

    # Build result
    active_set = set()
    active_slots = []
    total_z = 0.0

    for r, c in zip(row_ind, col_ind):
        if cost_matrix[r, c] >= 999:
            continue  # Ineligible assignment
        name = player_names[r]
        active_set.add(name)
        wz = weekly_z_values[r]
        games = int(available.iloc[r]["games_week"])
        total_z += wz

        active_slots.append(LineupSlot(
            slot=slots[c],
            player_name=name,
            positions=str(player_positions[r]),
            games_this_week=games,
            weekly_z=round(wz, 2),
        ))

    # Sort active by slot order
    slot_order = {s: i for i, s in enumerate(slots)}
    active_slots.sort(key=lambda x: slot_order.get(x.slot, 99))

    bench = [n for n in player_names if n not in active_set]

    # Category projections for active lineup
    active_df = available[available["name"].isin(active_set)]
    cat_proj = {}
    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col in active_df.columns:
            cat_proj[cat] = round(active_df[z_col].sum(), 2)

    games_by_player = {
        row["name"]: int(row["games_week"])
        for _, row in available[available["name"].isin(active_set)].iterrows()
    }

    return LineupRecommendation(
        active=active_slots,
        bench=bench,
        total_weekly_z=round(total_z, 2),
        games_by_player=games_by_player,
        category_projections=cat_proj,
    )


def format_lineup_report(rec: LineupRecommendation) -> str:
    """Format lineup recommendation as a readable report."""
    lines = []
    lines.append("=" * 90)
    lines.append("LINEUP RECOMMENDATION")
    lines.append("=" * 90)
    lines.append("")
    lines.append(
        f"  {'Slot':>4s}  {'Player':25s}  {'Positions':15s}  "
        f"{'Games':>5s}  {'Weekly Z':>8s}"
    )
    lines.append("  " + "-" * 70)

    for slot in rec.active:
        lines.append(
            f"  {slot.slot:>4s}  {slot.player_name:25s}  {slot.positions:15s}  "
            f"{slot.games_this_week:5d}  {slot.weekly_z:+8.2f}"
        )

    lines.append("  " + "-" * 70)
    lines.append(f"  Total weekly z-score: {rec.total_weekly_z:+.2f}")

    if rec.bench:
        lines.append(f"\n  Bench: {', '.join(rec.bench[:15])}")
        if len(rec.bench) > 15:
            lines.append(f"         ... and {len(rec.bench) - 15} more")

    if rec.category_projections:
        lines.append(f"\n  Category Z-Scores (active lineup):")
        for cat in ALL_CATS:
            z = rec.category_projections.get(cat, 0)
            lines.append(f"    {cat:>8s}: {z:+.2f}")

    return "\n".join(lines)
