"""
Punt strategy optimizer.

Brute-forces all possible punt combinations (up to max_punt_cats)
and ranks them by how much they improve the team's competitive position.

For 9 cats, punting up to 2:
  C(9,0) + C(9,1) + C(9,2) = 1 + 9 + 36 = 46 combinations. Very fast.
"""
from itertools import combinations

import pandas as pd

from fantasy_engine.analytics.zscores import ALL_CATS, compute_punt_zscores, ZScoreConfig


def find_optimal_punt(
    stats_df: pd.DataFrame,
    team_player_indices: list[int],
    max_punt_cats: int = 2,
    config: ZScoreConfig | None = None,
) -> list[dict]:
    """
    Evaluate all punt strategies for a given team.

    Args:
        stats_df: Full league stats DataFrame (all players on roster).
        team_player_indices: DataFrame indices of players on the team.
        max_punt_cats: Maximum number of categories to punt (1 or 2).

    Returns:
        List of punt strategies sorted by expected competitive advantage,
        each with: punted cats, active cats, team z-total, expected cats won.
    """
    results = []

    for n_punt in range(0, max_punt_cats + 1):
        for punt_combo in combinations(ALL_CATS, n_punt):
            punt_list = list(punt_combo)
            z_df = compute_punt_zscores(stats_df, punt_list, config)

            # Get team z-scores
            team_z = z_df.iloc[team_player_indices]
            active_cats = [c for c in ALL_CATS if c not in punt_list]

            # Sum z-scores for active categories only
            team_total = sum(team_z[f"z_{c}"].sum() for c in active_cats)

            # Estimate expected cats won per matchup
            # Assume average opponent; a positive z-sum in a category means >50% win rate
            # Rough estimate: P(win cat) ≈ sigmoid(team_z_sum_cat / scale)
            expected_wins = _estimate_expected_wins(team_z, active_cats)

            results.append({
                "punted": punt_list,
                "active_cats": active_cats,
                "n_competing": len(active_cats),
                "team_z_total": round(team_total, 2),
                "expected_cats_won": round(expected_wins, 2),
                "avg_z_per_cat": round(team_total / max(len(active_cats), 1), 2),
            })

    return sorted(results, key=lambda x: x["expected_cats_won"], reverse=True)


def _estimate_expected_wins(team_z: pd.DataFrame, active_cats: list[str]) -> float:
    """
    Estimate expected category wins per matchup.

    Uses a simple model: for each active category, if the team's summed
    z-score is positive, they're likely to win that category.

    P(win cat) ≈ 0.5 + 0.1 * team_z_sum (clamped to [0.1, 0.9])
    This is a rough sigmoid approximation.
    """
    expected = 0.0
    for cat in active_cats:
        z_sum = team_z[f"z_{cat}"].sum()
        # Scale: each z-point ≈ 10% win probability shift
        p_win = min(0.9, max(0.1, 0.5 + 0.1 * z_sum))
        expected += p_win
    return expected


def format_punt_report(results: list[dict], top_n: int = 15) -> str:
    """Format punt analysis results as a readable report."""
    lines = []
    lines.append("=" * 100)
    lines.append("PUNT STRATEGY ANALYSIS")
    lines.append("=" * 100)
    lines.append(
        f"  {'#':>3s}  {'Punted':30s}  {'Cats':>4s}  "
        f"{'Team Z':>7s}  {'Avg Z/Cat':>9s}  {'Exp Wins':>8s}"
    )
    lines.append("-" * 100)

    for i, r in enumerate(results[:top_n], 1):
        punt_str = ", ".join(r["punted"]) if r["punted"] else "(none)"
        lines.append(
            f"  {i:3d}  {punt_str:30s}  {r['n_competing']:4d}  "
            f"{r['team_z_total']:+7.2f}  {r['avg_z_per_cat']:+9.2f}  "
            f"{r['expected_cats_won']:8.2f}"
        )

    return "\n".join(lines)
