"""
Team category strength analysis.

Analyzes a team's roster to determine which categories are strong, average,
or weak, and suggests punt strategies based on the profile.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS

# Module-level scarcity cache — set by deps.py after computing scarcity
_scarcity_cache: list | None = None


def set_scarcity_cache(scarcity: list):
    """Set the global scarcity data so get_need_weights uses it automatically."""
    global _scarcity_cache
    _scarcity_cache = scarcity


@dataclass
class CategoryProfile:
    """Per-category analysis for a team."""
    z_sum: float
    rank: int = 0
    strength: str = "average"  # "strong", "average", "weak"


@dataclass
class TeamProfile:
    """Full team category analysis."""
    categories: dict[str, CategoryProfile] = field(default_factory=dict)
    strongest_cats: list[str] = field(default_factory=list)
    weakest_cats: list[str] = field(default_factory=list)
    suggested_punts: list[str] = field(default_factory=list)
    total_z: float = 0.0


def analyze_team(
    team_z_df: pd.DataFrame,
    all_teams_z: pd.DataFrame | None = None,
) -> TeamProfile:
    """
    Analyze a team's category strengths and weaknesses.

    Args:
        team_z_df: DataFrame of z-scores for players on this team.
                   Must have z_<cat> columns.
        all_teams_z: Optional. If provided, ranks are computed relative
                     to other teams. Otherwise, ranks are within the team's
                     own categories.

    Returns:
        TeamProfile with per-category analysis and suggestions.
    """
    profile = TeamProfile()
    cat_data = {}

    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col in team_z_df.columns:
            z_sum = team_z_df[z_col].sum()
        else:
            z_sum = 0.0
        cat_data[cat] = z_sum

    # Rank categories relative to each other
    sorted_cats = sorted(cat_data.items(), key=lambda x: x[1], reverse=True)

    for rank, (cat, z_sum) in enumerate(sorted_cats, 1):
        if rank <= 3:
            strength = "strong"
        elif rank <= 6:
            strength = "average"
        else:
            strength = "weak"

        profile.categories[cat] = CategoryProfile(
            z_sum=round(z_sum, 2),
            rank=rank,
            strength=strength,
        )

    profile.strongest_cats = [cat for cat, _ in sorted_cats[:3]]
    profile.weakest_cats = [cat for cat, _ in sorted_cats[-3:]]
    profile.total_z = sum(cat_data.values())

    # Punt suggestion: categories significantly below the team's own mean
    z_values = list(cat_data.values())
    mean_z = np.mean(z_values)
    std_z = np.std(z_values) if len(z_values) > 1 else 0
    if std_z > 0:
        profile.suggested_punts = [
            cat for cat, z in cat_data.items()
            if z < mean_z - 1.2 * std_z
        ]

    return profile


def get_need_weights(
    profile: TeamProfile,
    punt_cats: list[str] | None = None,
    scarcity: list | None = None,
) -> dict[str, float]:
    """
    Get category need weights for trade/add-drop evaluation.

    Combines three factors:
    - Team need: weak categories get 1.5x, strong get 0.7x
    - Scarcity: scarce categories (BLK 1.13x, AST 1.16x) get boosted
    - Punted categories get 0 weight

    This function is called by trade_eval, trade_finder, trade_simulator,
    add_drop, lineup, matchup, and trade_intelligence — so scarcity
    propagates to every module automatically.
    """
    if punt_cats is None:
        punt_cats = []

    # Build scarcity lookup — use passed value or fall back to cache
    effective_scarcity = scarcity if scarcity is not None else _scarcity_cache
    scarcity_map = {}
    if effective_scarcity:
        for s in effective_scarcity:
            cat = s.category if hasattr(s, "category") else s.get("category", "")
            idx = s.scarcity_index if hasattr(s, "scarcity_index") else s.get("scarcity_index", 1.0)
            scarcity_map[cat] = idx

    weights = {}
    for cat in ALL_CATS:
        if cat in punt_cats:
            weights[cat] = 0.0
            continue

        # Team need weight
        cp = profile.categories.get(cat)
        if cp is None:
            need_w = 1.0
        elif cp.strength == "weak":
            need_w = 1.5
        elif cp.strength == "strong":
            need_w = 0.7
        else:
            need_w = 1.0

        # Scarcity multiplier
        scarcity_w = scarcity_map.get(cat, 1.0)

        weights[cat] = round(need_w * scarcity_w, 3)

    return weights


def format_team_profile(profile: TeamProfile, team_name: str = "My Team") -> str:
    """Format a team profile as a readable report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"TEAM CATEGORY PROFILE: {team_name}")
    lines.append("=" * 80)

    sorted_cats = sorted(
        profile.categories.items(),
        key=lambda x: x[1].rank,
    )

    for cat, cp in sorted_cats:
        bar_len = max(0, int(abs(cp.z_sum) * 3))
        bar_char = "+" if cp.z_sum >= 0 else "-"
        bar = bar_char * bar_len
        strength_label = f"[{cp.strength.upper():>7s}]"
        lines.append(
            f"  #{cp.rank}  {cat:>6s}: {cp.z_sum:+6.2f}  {strength_label}  {bar}"
        )

    lines.append(f"\n  Total Z: {profile.total_z:+.2f}")
    lines.append(f"  Strongest: {', '.join(profile.strongest_cats)}")
    lines.append(f"  Weakest:   {', '.join(profile.weakest_cats)}")
    if profile.suggested_punts:
        lines.append(f"  Suggested punts: {', '.join(profile.suggested_punts)}")

    return "\n".join(lines)
