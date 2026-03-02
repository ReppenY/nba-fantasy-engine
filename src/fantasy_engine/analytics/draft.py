"""
Draft/Auction value calculator.

Computes fair auction prices for players based on z-scores and
replacement-level economics in a salary cap league.

The key insight: in an auction, you're buying z-scores above replacement
level. The total "surplus" across all teams equals the total salary cap
minus the minimum cost to fill rosters. This surplus is distributed
proportionally to each player's z-score above replacement.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class AuctionValue:
    name: str
    nba_team: str
    z_total: float
    z_above_replacement: float
    auction_value: float       # Fair $ price
    current_salary: float      # What they're currently paid (if rostered)
    value_diff: float          # auction_value - current_salary (+ = underpaid)
    tier: str                  # "elite", "starter", "bench", "replacement"
    age: int
    positions: str


def compute_auction_values(
    all_player_stats: pd.DataFrame,
    salary_cap: float = 200.0,
    num_teams: int = 12,
    roster_size: int = 36,
    active_slots: int = 11,
    min_bid: float = 1.0,
) -> list[AuctionValue]:
    """
    Compute fair auction values for all NBA players.

    Algorithm:
    1. Compute z-scores for all players
    2. Determine replacement level (the z-score of the Nth best player,
       where N = num_teams * active_slots)
    3. Compute z-score above replacement for each player
    4. Total available surplus = (salary_cap * num_teams) - (min_bid * roster_size * num_teams)
    5. Distribute surplus proportionally to z-above-replacement
    """
    from fantasy_engine.analytics.zscores import compute_zscores, ZScoreConfig

    # Compute z-scores for all players
    config = ZScoreConfig(min_games=10, min_minutes=10.0)
    z_df = compute_zscores(all_player_stats, config)

    # Carry forward columns
    for col in ["name", "nba_team", "salary", "age", "positions", "games_played",
                "pts", "reb", "ast", "schedule_adjusted_z", "ros_value", "consistency_rating",
                "games_remaining", "playoff_games"]:
        if col in all_player_stats.columns:
            z_df[col] = all_player_stats[col].values

    # Use schedule-adjusted z if available, otherwise raw z
    sort_col = "schedule_adjusted_z" if "schedule_adjusted_z" in z_df.columns and z_df["schedule_adjusted_z"].sum() != 0 else "z_total"
    z_df = z_df.sort_values(sort_col, ascending=False).reset_index(drop=True)

    # Replacement level = z-score of the player at position (teams * active_slots)
    replacement_rank = num_teams * active_slots
    if len(z_df) > replacement_rank:
        replacement_z = z_df.iloc[replacement_rank]["z_total"]
    else:
        replacement_z = z_df["z_total"].min()

    # Z above replacement
    z_df["z_above_replacement"] = (z_df["z_total"] - replacement_z).clip(lower=0)

    # Apply consistency premium
    if "consistency_rating" in z_df.columns:
        cons = z_df["consistency_rating"].fillna(0.5)
        consistency_premium = 0.85 + 0.15 * cons
        z_df["z_above_replacement"] = z_df["z_above_replacement"] * consistency_premium

    # EMPIRICAL MARKET VALUE
    # Calibrated from actual 2025 dynasty auction draft results.
    # Linear fit of actual bids vs z-scores: price = 2.09 * z + 7.55
    #
    # Key: use the HIGHER of current z-score or recent trend z-score.
    # This prevents injured stars from being drastically undervalued.
    # A player with z:+6 this season but z:+10 last 14 games is likely
    # returning to form — their market value should reflect the upside.
    MARKET_SLOPE = 2.09
    MARKET_BASE = 7.55

    # Use the better of current z or schedule-adjusted z (captures upside)
    effective_z = z_df["z_total"].copy()
    if "schedule_adjusted_z" in z_df.columns:
        sched_z = z_df["schedule_adjusted_z"].fillna(0)
        effective_z = np.maximum(effective_z, sched_z)

    z_df["auction_value"] = (MARKET_SLOPE * effective_z + MARKET_BASE).clip(lower=min_bid)

    # Star premium: elite players (z > 8) get bid up in real auctions
    # because managers pay for name recognition and proven upside
    star_bonus = np.where(effective_z > 8, (effective_z - 8) * 1.5, 0)
    z_df["auction_value"] += star_bonus

    # Minutes adjustment: players with fewer minutes are less valuable
    # because their production is less reliable and they could lose their role.
    # 30+ min = full value, 20-30 = slight discount, <20 = significant discount
    if "minutes" in z_df.columns:
        mins = z_df["minutes"].fillna(20)
        min_mult = np.where(mins >= 30, 1.0,
                   np.where(mins >= 20, 0.7 + 0.3 * ((mins - 20) / 10),
                   np.where(mins >= 10, 0.4 + 0.3 * ((mins - 10) / 10),
                   0.3)))
        z_df["auction_value"] = z_df["auction_value"] * min_mult

    # Age adjustment: gentler than before
    # Young (<=24): +10% premium (dynasty upside)
    # Prime (25-31): neutral (still productive)
    # Aging (32-35): -5% per year over 31
    # Old (36+): -10% per year over 35
    if "age" in z_df.columns:
        age = z_df["age"].fillna(27)
        age_mult = np.where(age <= 24, 1.10,
                   np.where(age <= 31, 1.0,
                   np.where(age <= 35, np.maximum(0.7, 1.0 - 0.05 * (age - 31)),
                   np.maximum(0.5, 0.8 - 0.10 * (age - 35)))))
        z_df["auction_value"] = (z_df["auction_value"] * age_mult).clip(lower=min_bid)

    # Position scarcity premium: scarce positions (C) cost more at auction
    try:
        from fantasy_engine.analytics.positional_scarcity import get_pos_scarcity_bonus
        pos_bonuses = z_df["name"].apply(get_pos_scarcity_bonus)
        pos_mult = (1 + pos_bonuses * 0.08).clip(lower=0.85, upper=1.25)
        z_df["auction_value"] = z_df["auction_value"] * pos_mult
    except Exception:
        pass

    z_df["auction_value"] = z_df["auction_value"].round(1)

    # Z above replacement stays for tier calculation
    z_df.loc[z_df["z_above_replacement"] <= 0, "auction_value"] = z_df.loc[
        z_df["z_above_replacement"] <= 0, "auction_value"
    ].clip(lower=min_bid, upper=3.0)  # Below replacement = min bid territory

    # Round
    z_df["auction_value"] = z_df["auction_value"].round(1)

    # Value diff vs current salary
    z_df["value_diff"] = z_df["auction_value"] - z_df.get("salary", min_bid).fillna(min_bid)

    # Tiers
    def _tier(row):
        if row["z_above_replacement"] > 5:
            return "elite"
        elif row["z_above_replacement"] > 2:
            return "starter"
        elif row["z_above_replacement"] > 0:
            return "bench"
        return "replacement"

    results = []
    for _, row in z_df.iterrows():
        if row.get("games_played", 0) < 5:
            continue
        results.append(AuctionValue(
            name=row.get("name", ""),
            nba_team=row.get("nba_team", ""),
            z_total=round(row.get("z_total", 0), 2),
            z_above_replacement=round(row.get("z_above_replacement", 0), 2),
            auction_value=row.get("auction_value", min_bid),
            current_salary=row.get("salary", 0),
            value_diff=round(row.get("value_diff", 0), 1),
            tier=_tier(row),
            age=int(row.get("age", 0)),
            positions=row.get("positions", ""),
        ))

    return results


def get_bargains(values: list[AuctionValue], top_n: int = 20) -> list[AuctionValue]:
    """Players most underpaid relative to their auction value."""
    return sorted(
        [v for v in values if v.current_salary > 0],
        key=lambda v: v.value_diff,
        reverse=True,
    )[:top_n]


def get_overpays(values: list[AuctionValue], top_n: int = 20) -> list[AuctionValue]:
    """Players most overpaid relative to their auction value."""
    return sorted(
        [v for v in values if v.current_salary > 0],
        key=lambda v: v.value_diff,
    )[:top_n]
