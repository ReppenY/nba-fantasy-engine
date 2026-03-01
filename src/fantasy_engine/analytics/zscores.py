"""
Z-score engine for 9-category fantasy basketball.

Handles:
- Counting stats (PTS, REB, AST, STL, BLK, 3PTM): standard z-score
- Percentage stats (FG%, FT%): volume-weighted impact method
- Negative stats (TO): inverted z-score
- Punt-aware mode: recompute excluding punted categories
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


COUNTING_CATS = ["pts", "reb", "ast", "stl", "blk", "tpm"]
PERCENTAGE_CATS = ["fg_pct", "ft_pct"]
NEGATIVE_CATS = ["tov"]
ALL_CATS = COUNTING_CATS + PERCENTAGE_CATS + NEGATIVE_CATS


@dataclass
class ZScoreConfig:
    min_games: int = 10
    min_minutes: float = 10.0


def compute_zscores(
    stats_df: pd.DataFrame,
    config: ZScoreConfig | None = None,
) -> pd.DataFrame:
    """
    Compute z-scores for all players across all 9 categories.

    For counting stats: z = (x - mean) / std
    For FG%: impact = (FG% - league_avg_FG%) * FGA, then z-score the impact
    For FT%: impact = (FT% - league_avg_FT%) * FTA, then z-score the impact
    For TO: z = -1 * (x - mean) / std

    Input DataFrame must have columns:
        games_played, minutes, pts, reb, ast, stl, blk, tpm,
        fgm, fga, fg_pct, ftm, fta, ft_pct, tov

    Returns DataFrame with z_<cat> columns and z_total.
    """
    if config is None:
        config = ZScoreConfig()

    # Filter to qualified players for population stats
    has_minutes = "minutes" in stats_df.columns
    if has_minutes:
        qualified = stats_df[
            (stats_df["games_played"] >= config.min_games)
            & (stats_df["minutes"] >= config.min_minutes)
        ].copy()
    else:
        qualified = stats_df[
            stats_df["games_played"] >= config.min_games
        ].copy()

    if len(qualified) == 0:
        raise ValueError("No players meet the minimum games/minutes threshold")

    # We'll compute z-scores for ALL players using the qualified population's mean/std
    result = stats_df[["name"]].copy() if "name" in stats_df.columns else pd.DataFrame()
    if "player_id" in stats_df.columns:
        result["player_id"] = stats_df["player_id"].values

    # Counting stats
    for cat in COUNTING_CATS:
        mean = qualified[cat].mean()
        std = qualified[cat].std()
        if std == 0 or np.isnan(std):
            result[f"z_{cat}"] = 0.0
        else:
            result[f"z_{cat}"] = (stats_df[cat] - mean) / std

    # FG% (volume-weighted impact)
    total_fgm = qualified["fgm"].sum()
    total_fga = qualified["fga"].sum()
    if total_fga > 0:
        league_avg_fg = total_fgm / total_fga
        # Impact: how many extra makes above league average, given volume
        fg_impact_pop = (qualified["fg_pct"] - league_avg_fg) * qualified["fga"]
        fg_mean = fg_impact_pop.mean()
        fg_std = fg_impact_pop.std()

        fg_impact_all = (stats_df["fg_pct"] - league_avg_fg) * stats_df["fga"]
        if fg_std > 0:
            result["z_fg_pct"] = (fg_impact_all - fg_mean) / fg_std
        else:
            result["z_fg_pct"] = 0.0
    else:
        result["z_fg_pct"] = 0.0

    # FT% (volume-weighted impact)
    total_ftm = qualified["ftm"].sum()
    total_fta = qualified["fta"].sum()
    if total_fta > 0:
        league_avg_ft = total_ftm / total_fta
        ft_impact_pop = (qualified["ft_pct"] - league_avg_ft) * qualified["fta"]
        ft_mean = ft_impact_pop.mean()
        ft_std = ft_impact_pop.std()

        ft_impact_all = (stats_df["ft_pct"] - league_avg_ft) * stats_df["fta"]
        if ft_std > 0:
            result["z_ft_pct"] = (ft_impact_all - ft_mean) / ft_std
        else:
            result["z_ft_pct"] = 0.0
    else:
        result["z_ft_pct"] = 0.0

    # Turnovers (inverted: fewer = better)
    tov_mean = qualified["tov"].mean()
    tov_std = qualified["tov"].std()
    if tov_std > 0:
        result["z_tov"] = -1 * (stats_df["tov"] - tov_mean) / tov_std
    else:
        result["z_tov"] = 0.0

    # Total z-score (sum of all 9)
    z_cols = [f"z_{c}" for c in ALL_CATS]
    result["z_total"] = result[z_cols].sum(axis=1)

    # Copy identifying columns
    for col in ["name", "nba_team", "salary", "positions", "games_played", "minutes"]:
        if col in stats_df.columns:
            result[col] = stats_df[col].values

    return result


def compute_punt_zscores(
    stats_df: pd.DataFrame,
    punt_cats: list[str],
    config: ZScoreConfig | None = None,
) -> pd.DataFrame:
    """
    Recompute z-scores excluding punted categories from the total.

    The individual z-scores stay the same; only z_total changes
    to reflect only the categories you're competing in.
    """
    z_df = compute_zscores(stats_df, config)

    active_cats = [c for c in ALL_CATS if c not in punt_cats]
    z_cols = [f"z_{c}" for c in active_cats]
    z_df["z_total"] = z_df[z_cols].sum(axis=1)
    z_df["punted_cats"] = ",".join(punt_cats) if punt_cats else ""

    return z_df
