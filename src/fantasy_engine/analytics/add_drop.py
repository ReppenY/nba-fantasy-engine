"""
Add/Drop optimizer for waiver wire decisions.

Ranks free agents by how well they fill team needs,
identifies droppable players, and suggests optimal swaps.
"""
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights


@dataclass
class AddCandidate:
    name: str
    z_total: float
    need_weighted_z: float
    salary: float
    helps_cats: list[str] = field(default_factory=list)


@dataclass
class DropCandidate:
    name: str
    z_total: float
    z_per_dollar: float
    salary: float
    droppability_score: float = 0.0
    reason: str = ""


@dataclass
class SwapRecommendation:
    drop: str
    add: str
    net_z_change: float
    net_need_z_change: float
    salary_change: float
    cat_impact: dict[str, float] = field(default_factory=dict)


def best_available(
    roster_z_df: pd.DataFrame,
    fa_z_df: pd.DataFrame,
    punt_cats: list[str] | None = None,
    top_n: int = 20,
) -> list[AddCandidate]:
    """
    Rank free agents by how much they fill team needs.

    Uses need-weighted z-scores: a FA that fills weak categories
    ranks higher than one who is generically good but redundant.
    """
    if punt_cats is None:
        punt_cats = []

    profile = analyze_team(roster_z_df)
    weights = get_need_weights(profile, punt_cats)

    candidates = []
    for _, row in fa_z_df.iterrows():
        need_z = 0.0
        helps = []
        for cat in ALL_CATS:
            z_col = f"z_{cat}"
            if z_col not in row.index:
                continue
            w = weights.get(cat, 1.0)
            contribution = row[z_col] * w
            need_z += contribution
            if row[z_col] > 0.3 and cat not in punt_cats:
                cat_profile = profile.categories.get(cat)
                if cat_profile and cat_profile.strength in ("weak", "average"):
                    helps.append(cat)

        # Position scarcity: scarce-position FAs rank higher
        try:
            from fantasy_engine.analytics.positional_scarcity import get_pos_scarcity_bonus
            need_z += get_pos_scarcity_bonus(row.get("name", "")) * 0.5
        except Exception:
            pass

        candidates.append(AddCandidate(
            name=row.get("name", "Unknown"),
            z_total=round(row.get("z_total", 0), 2),
            need_weighted_z=round(need_z, 2),
            salary=row.get("salary", 1.0),
            helps_cats=helps,
        ))

    candidates.sort(key=lambda x: x.need_weighted_z, reverse=True)
    return candidates[:top_n]


def drop_candidates(
    roster_z_df: pd.DataFrame,
    punt_cats: list[str] | None = None,
    top_n: int = 10,
) -> list[DropCandidate]:
    """
    Rank roster players from most droppable to least.

    Factors: z_total, z_per_dollar, category redundancy.
    """
    if punt_cats is None:
        punt_cats = []

    profile = analyze_team(roster_z_df)
    weights = get_need_weights(profile, punt_cats)

    candidates = []
    for _, row in roster_z_df.iterrows():
        z_total = row.get("z_total", 0)
        salary = row.get("salary", 1.0)
        z_per_dollar = z_total / max(salary, 0.5)

        # Droppability: lower z = more droppable. Also consider redundancy.
        # If a player's best categories are ones the team is already strong in,
        # they're more droppable.
        redundancy_penalty = 0.0
        for cat in ALL_CATS:
            z_col = f"z_{cat}"
            if z_col not in row.index:
                continue
            cat_profile = profile.categories.get(cat)
            if cat_profile and cat_profile.strength == "strong" and row[z_col] > 0.5:
                redundancy_penalty += 0.3  # Penalize contributing to already-strong cats

        droppability = -z_total + redundancy_penalty - (salary * 0.1)

        # Position scarcity: scarce-position players are less droppable
        try:
            from fantasy_engine.analytics.positional_scarcity import get_pos_scarcity_bonus
            droppability -= get_pos_scarcity_bonus(row.get("name", "")) * 0.5
        except Exception:
            pass

        reason_parts = []
        if z_total < -2:
            reason_parts.append("very low z-score")
        elif z_total < 0:
            reason_parts.append("negative z-score")
        if redundancy_penalty > 0.5:
            reason_parts.append("redundant categories")
        if salary <= 1.0:
            reason_parts.append("minimum salary (easy drop)")

        candidates.append(DropCandidate(
            name=row.get("name", "Unknown"),
            z_total=round(z_total, 2),
            z_per_dollar=round(z_per_dollar, 2),
            salary=salary,
            droppability_score=round(droppability, 2),
            reason="; ".join(reason_parts) if reason_parts else "decent player",
        ))

    candidates.sort(key=lambda x: x.droppability_score, reverse=True)
    return candidates[:top_n]


def best_swaps(
    roster_z_df: pd.DataFrame,
    fa_z_df: pd.DataFrame,
    punt_cats: list[str] | None = None,
    top_n: int = 10,
) -> list[SwapRecommendation]:
    """
    Find the best add/drop pairs.

    For each droppable player, find the FA that maximizes
    net need-weighted z-score improvement.
    """
    if punt_cats is None:
        punt_cats = []

    drops = drop_candidates(roster_z_df, punt_cats, top_n=15)
    adds = best_available(roster_z_df, fa_z_df, punt_cats, top_n=20)

    if not drops or not adds:
        return []

    profile = analyze_team(roster_z_df)
    weights = get_need_weights(profile, punt_cats)

    swaps = []
    for drop in drops:
        drop_row = roster_z_df[roster_z_df["name"] == drop.name]
        if drop_row.empty:
            continue
        drop_row = drop_row.iloc[0]

        for add in adds:
            add_row = fa_z_df[fa_z_df["name"] == add.name]
            if add_row.empty:
                continue
            add_row = add_row.iloc[0]

            # Net change per category
            cat_impact = {}
            net_need_z = 0.0
            for cat in ALL_CATS:
                z_col = f"z_{cat}"
                delta = add_row.get(z_col, 0) - drop_row.get(z_col, 0)
                cat_impact[cat] = round(delta, 3)
                net_need_z += delta * weights.get(cat, 1.0)

            net_z = add_row.get("z_total", 0) - drop_row.get("z_total", 0)
            salary_change = add_row.get("salary", 1.0) - drop_row.get("salary", 1.0)

            swaps.append(SwapRecommendation(
                drop=drop.name,
                add=add.name,
                net_z_change=round(net_z, 2),
                net_need_z_change=round(net_need_z, 2),
                salary_change=round(salary_change, 2),
                cat_impact=cat_impact,
            ))

    swaps.sort(key=lambda x: x.net_need_z_change, reverse=True)
    return swaps[:top_n]


def format_add_drop_report(
    adds: list[AddCandidate],
    drops: list[DropCandidate],
    swaps: list[SwapRecommendation],
) -> str:
    """Format add/drop analysis as a readable report."""
    lines = []

    # Best available FAs
    lines.append("=" * 90)
    lines.append("BEST AVAILABLE FREE AGENTS (by team need)")
    lines.append("=" * 90)
    lines.append(
        f"  {'#':>3s}  {'Player':25s}  {'Z-Tot':>6s}  {'Need-Z':>7s}  "
        f"{'$':>5s}  Helps"
    )
    lines.append("  " + "-" * 75)
    for i, a in enumerate(adds[:15], 1):
        helps = ", ".join(a.helps_cats[:4]) if a.helps_cats else "-"
        lines.append(
            f"  {i:3d}  {a.name:25s}  {a.z_total:+6.2f}  {a.need_weighted_z:+7.2f}  "
            f"{a.salary:5.1f}  {helps}"
        )

    # Drop candidates
    lines.append("")
    lines.append("=" * 90)
    lines.append("DROP CANDIDATES (most droppable first)")
    lines.append("=" * 90)
    lines.append(
        f"  {'#':>3s}  {'Player':25s}  {'Z-Tot':>6s}  {'Z/$':>6s}  "
        f"{'$':>5s}  {'Score':>6s}  Reason"
    )
    lines.append("  " + "-" * 80)
    for i, d in enumerate(drops[:10], 1):
        lines.append(
            f"  {i:3d}  {d.name:25s}  {d.z_total:+6.2f}  {d.z_per_dollar:+6.2f}  "
            f"{d.salary:5.1f}  {d.droppability_score:+6.2f}  {d.reason[:35]}"
        )

    # Best swaps
    if swaps:
        lines.append("")
        lines.append("=" * 90)
        lines.append("BEST SWAPS (drop -> add)")
        lines.append("=" * 90)
        lines.append(
            f"  {'#':>3s}  {'Drop':20s}  {'Add':20s}  "
            f"{'Net Z':>6s}  {'Need-Z':>7s}  {'$ Chg':>6s}"
        )
        lines.append("  " + "-" * 75)
        for i, s in enumerate(swaps[:10], 1):
            lines.append(
                f"  {i:3d}  {s.drop:20s}  {s.add:20s}  "
                f"{s.net_z_change:+6.2f}  {s.net_need_z_change:+7.2f}  "
                f"{s.salary_change:+6.2f}"
            )

    return "\n".join(lines)
