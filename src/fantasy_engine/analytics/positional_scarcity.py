"""
Positional scarcity analysis for fantasy basketball.

Measures how "position-locked" a player's production is. BLK comes almost
exclusively from C/PF — so a center providing elite BLK has production
that can ONLY be replaced by another big. A guard providing PTS can be
replaced by any position. Players whose best categories are concentrated
at their position get a positive scarcity bonus.

Method:
- Compute category-position concentration: what % of elite production in
  each category comes from each position?
- For each player, score = sum of (their z per category × how concentrated
  that category is at their position)
- Normalize relative to the pool average
"""
import numpy as np
import pandas as pd

from fantasy_engine.analytics.zscores import ALL_CATS

# Only base positions — G, F, Flx are slot types, not positions
BASE_POSITIONS = ["PG", "SG", "SF", "PF", "C"]

# ---------------------------------------------------------------------------
# Global cache — set by deps.py, consumed by all analytics modules
# ---------------------------------------------------------------------------
_position_scarcity_cache: dict[str, float] | None = None
_position_stats_cache: dict[str, dict] | None = None


def set_position_scarcity_cache(
    bonuses: dict[str, float],
    position_stats: dict[str, dict],
):
    """Set the global position scarcity data (called once at startup)."""
    global _position_scarcity_cache, _position_stats_cache
    _position_scarcity_cache = bonuses
    _position_stats_cache = position_stats


def get_pos_scarcity_bonus(player_name: str) -> float:
    """Get a player's position scarcity bonus from cache. 0 if not found."""
    if _position_scarcity_cache is None:
        return 0.0
    return _position_scarcity_cache.get(player_name, 0.0)


def get_replacement_levels() -> dict[str, dict]:
    """Get cached position stats (concentration data per category×position)."""
    return _position_stats_cache or {}


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _parse_base_positions(positions_str) -> list[str]:
    """Extract base positions (PG/SG/SF/PF/C) from a CSV positions string."""
    if not positions_str or pd.isna(positions_str):
        return []
    return [
        p.strip() for p in str(positions_str).split(",")
        if p.strip() in BASE_POSITIONS
    ]


def _compute_category_position_concentration(
    z_df: pd.DataFrame,
    elite_threshold: float = 0.5,
) -> dict[str, dict[str, float]]:
    """
    For each category, compute what fraction of elite production comes
    from each position.

    Returns: {cat: {pos: fraction, ...}, ...}
    e.g., {"blk": {"C": 0.45, "PF": 0.30, "SF": 0.12, ...}}
    """
    concentration = {}

    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col not in z_df.columns:
            continue

        # Elite producers in this category
        elite = z_df[z_df[z_col] >= elite_threshold]
        if len(elite) == 0:
            concentration[cat] = {pos: 1.0 / len(BASE_POSITIONS) for pos in BASE_POSITIONS}
            continue

        # Count how much elite production comes from each position
        pos_production = {}
        total_production = 0.0

        for pos in BASE_POSITIONS:
            # Players eligible at this position who are elite in this category
            pos_elite = elite[
                elite["positions"].fillna("").str.contains(
                    rf"\b{pos}\b", case=False, regex=True,
                )
            ]
            # Sum their z-score in this category (not just count, but actual production)
            pos_z_sum = pos_elite[z_col].sum() if len(pos_elite) > 0 else 0.0
            pos_production[pos] = max(0, pos_z_sum)
            total_production += max(0, pos_z_sum)

        # Normalize to fractions
        if total_production > 0:
            concentration[cat] = {
                pos: round(pos_production[pos] / total_production, 3)
                for pos in BASE_POSITIONS
            }
        else:
            concentration[cat] = {pos: 0.2 for pos in BASE_POSITIONS}

    return concentration


def compute_positional_scarcity(
    z_df: pd.DataFrame,
    num_teams: int = 12,
) -> pd.DataFrame:
    """
    Compute positional scarcity bonus for every player.

    For each player:
    1. Look at their z-score per category
    2. For each positive category, check how concentrated that category
       is at their position (e.g., BLK is 45% from C)
    3. Score = sum of z_cat × (concentration - baseline)
       where baseline = 1/5 = 0.20 (equal distribution)
    4. Players whose production is position-locked get positive bonus

    Multi-position players use whichever position gives the highest bonus.

    Returns DataFrame with: pos_scarcity_bonus, scarcest_position
    """
    concentration = _compute_category_position_concentration(z_df)
    baseline = 1.0 / len(BASE_POSITIONS)  # 0.20 = equal spread

    # Get category scarcity weights — categories that are BOTH position-locked
    # AND scarce (like AST 1.16x, BLK 1.13x) should count more
    from fantasy_engine.analytics.category_analysis import _scarcity_cache
    scarcity_map = {}
    if _scarcity_cache:
        for s in _scarcity_cache:
            cat = s.category if hasattr(s, "category") else s.get("category", "")
            idx = s.scarcity_index if hasattr(s, "scarcity_index") else s.get("scarcity_index", 1.0)
            scarcity_map[cat] = idx

    # Compute raw scores for all players
    raw_scores = []
    scarcest_positions = []

    for _, row in z_df.iterrows():
        base_pos = _parse_base_positions(row.get("positions", ""))

        if not base_pos:
            raw_scores.append(0.0)
            scarcest_positions.append("")
            continue

        best_score = -999.0
        best_pos = base_pos[0]

        for pos in base_pos:
            score = 0.0
            for cat in ALL_CATS:
                z_col = f"z_{cat}"
                z_val = row.get(z_col, 0)
                if z_val <= 0:
                    continue
                # How concentrated is this category at this position?
                conc = concentration.get(cat, {}).get(pos, baseline)
                # Category scarcity amplifier (AST 1.16x, BLK 1.13x)
                scar = scarcity_map.get(cat, 1.0)
                # Two sources of positional value:
                # 1. Position-locked (conc > baseline): this category comes from
                #    this position (BLK from C) — full weight
                # 2. Off-position rarity (conc < baseline): this category is rare
                #    at this position (low TO from PG) — half weight
                if conc >= baseline:
                    deviation = conc - baseline
                else:
                    deviation = (baseline - conc) * 0.5
                score += z_val * deviation * scar

            if score > best_score:
                best_score = score
                best_pos = pos

        raw_scores.append(best_score)
        scarcest_positions.append(best_pos)

    # Normalize: center around 0, scale so typical range is ±1-2
    raw_arr = np.array(raw_scores)
    mean_score = raw_arr[raw_arr != 0].mean() if (raw_arr != 0).any() else 0
    std_score = raw_arr[raw_arr != 0].std() if (raw_arr != 0).any() else 1.0
    if std_score == 0:
        std_score = 1.0

    bonuses = [(s - mean_score) / std_score if s != 0 else 0.0 for s in raw_scores]
    bonuses = [round(b, 3) for b in bonuses]

    result = pd.DataFrame({
        "pos_scarcity_bonus": bonuses,
        "scarcest_position": scarcest_positions,
    }, index=z_df.index)

    # Build position stats summary
    pos_stats = {}
    for pos in BASE_POSITIONS:
        # Average bonus for players at this position
        mask = pd.Series(scarcest_positions, index=z_df.index) == pos
        avg_bonus = pd.Series(bonuses, index=z_df.index)[mask].mean() if mask.any() else 0.0
        count = mask.sum()
        # Top concentrated categories for this position
        top_cats = sorted(
            [(cat, concentration.get(cat, {}).get(pos, 0)) for cat in ALL_CATS],
            key=lambda x: -x[1],
        )[:3]
        pos_stats[pos] = {
            "count": int(count),
            "avg_bonus": round(avg_bonus, 2),
            "concentrated_cats": [
                {"cat": c, "pct": round(p * 100)} for c, p in top_cats if p > baseline
            ],
        }

    result.attrs["pos_stats"] = pos_stats
    result.attrs["concentration"] = concentration

    return result
