"""
Player trends from game-by-game data.

Computes rolling averages, z-score trajectory, category-specific trends,
and rising/falling player detection from nba_api game logs.
"""
import time
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS


STAT_COLS = ["pts", "reb", "ast", "stl", "blk", "tpm", "fgm", "fga", "ftm", "fta", "tov", "minutes"]
STAT_MAP = {
    "PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk",
    "FG3M": "tpm", "FGM": "fgm", "FGA": "fga", "FTM": "ftm", "FTA": "fta",
    "TOV": "tov", "MIN": "minutes",
}


@dataclass
class PlayerTrend:
    name: str
    nba_api_id: int = 0
    games_total: int = 0

    # Season averages
    season: dict[str, float] = field(default_factory=dict)

    # Rolling averages
    last_7: dict[str, float] = field(default_factory=dict)
    last_14: dict[str, float] = field(default_factory=dict)
    last_30: dict[str, float] = field(default_factory=dict)

    # Trend direction per category (last_14 - season)
    cat_trends: dict[str, float] = field(default_factory=dict)

    # Overall trend
    trending: str = "stable"  # "hot", "rising", "stable", "cooling", "cold"
    trend_score: float = 0.0  # Positive = trending up

    # Minutes
    minutes_season: float = 0.0
    minutes_recent: float = 0.0
    minutes_trend: float = 0.0

    # Computed percentages for recent splits
    fg_pct_last14: float = 0.0
    ft_pct_last14: float = 0.0


def fetch_game_logs_batch(
    player_ids: dict[str, int],
    season: str = "2025-26",
    delay: float = 0.6,
    max_players: int = 50,
) -> dict[str, pd.DataFrame]:
    """
    Fetch game logs for multiple players from nba_api.

    Args:
        player_ids: Dict of player_name -> nba_api_id
        season: NBA season string
        delay: Seconds between API calls
        max_players: Limit to avoid rate limiting

    Returns: Dict of player_name -> DataFrame of game logs
    """
    from nba_api.stats.endpoints import PlayerGameLog

    logs = {}
    count = 0

    for name, pid in player_ids.items():
        if count >= max_players:
            break
        try:
            gl = PlayerGameLog(player_id=pid, season=season)
            time.sleep(delay)
            df = gl.get_data_frames()[0]
            if not df.empty:
                logs[name] = df
            count += 1
        except Exception:
            continue

    return logs


def compute_player_trends(
    player_name: str,
    game_log: pd.DataFrame,
    season_avg: dict[str, float] | None = None,
) -> PlayerTrend:
    """
    Compute trends for a single player from their game log.
    """
    trend = PlayerTrend(name=player_name, games_total=len(game_log))

    if game_log.empty:
        return trend

    # Normalize column names
    gl = game_log.rename(columns=STAT_MAP)
    for col in STAT_COLS:
        if col not in gl.columns:
            gl[col] = 0

    # Ensure numeric
    for col in STAT_COLS:
        gl[col] = pd.to_numeric(gl[col], errors="coerce").fillna(0)

    # Game logs are typically most-recent-first
    # Season averages
    season_stats = {}
    for col in STAT_COLS:
        season_stats[col] = round(float(gl[col].mean()), 2)
    trend.season = season_stats

    # Rolling averages
    for n, attr in [(7, "last_7"), (14, "last_14"), (30, "last_30")]:
        recent = gl.head(min(n, len(gl)))
        rolling = {}
        for col in STAT_COLS:
            rolling[col] = round(float(recent[col].mean()), 2)
        setattr(trend, attr, rolling)

    # Percentage stats for last 14
    recent_14 = gl.head(min(14, len(gl)))
    fgm_14 = recent_14["fgm"].sum()
    fga_14 = recent_14["fga"].sum()
    ftm_14 = recent_14["ftm"].sum()
    fta_14 = recent_14["fta"].sum()
    trend.fg_pct_last14 = round(fgm_14 / fga_14, 3) if fga_14 > 0 else 0
    trend.ft_pct_last14 = round(ftm_14 / fta_14, 3) if fta_14 > 0 else 0

    # Category trends (last_14 vs season)
    trend_score = 0.0
    cat_trends = {}
    for cat in ["pts", "reb", "ast", "stl", "blk", "tpm", "tov", "minutes"]:
        season_val = season_stats.get(cat, 0)
        recent_val = trend.last_14.get(cat, 0)
        if season_val > 0:
            pct_change = (recent_val - season_val) / season_val
        else:
            pct_change = 0

        cat_trends[cat] = round(pct_change, 3)

        # Weight towards fantasy-relevant cats (not minutes)
        if cat != "minutes" and cat != "tov":
            trend_score += pct_change
        elif cat == "tov":
            trend_score -= pct_change  # Fewer TO is better

    trend.cat_trends = cat_trends
    trend.trend_score = round(trend_score, 3)

    # Classify trend
    if trend_score > 0.3:
        trend.trending = "hot"
    elif trend_score > 0.1:
        trend.trending = "rising"
    elif trend_score < -0.3:
        trend.trending = "cold"
    elif trend_score < -0.1:
        trend.trending = "cooling"
    else:
        trend.trending = "stable"

    # Minutes trend
    trend.minutes_season = season_stats.get("minutes", 0)
    trend.minutes_recent = trend.last_14.get("minutes", 0)
    trend.minutes_trend = round(trend.minutes_recent - trend.minutes_season, 1)

    return trend


def compute_all_trends(
    game_logs: dict[str, pd.DataFrame],
) -> dict[str, PlayerTrend]:
    """Compute trends for all players with game logs."""
    trends = {}
    for name, gl in game_logs.items():
        trends[name] = compute_player_trends(name, gl)
    return trends


def get_rising_players(trends: dict[str, PlayerTrend], top_n: int = 10) -> list[PlayerTrend]:
    """Get players trending up the most."""
    return sorted(
        [t for t in trends.values() if t.trending in ("hot", "rising") and t.games_total >= 10],
        key=lambda t: t.trend_score,
        reverse=True,
    )[:top_n]


def get_falling_players(trends: dict[str, PlayerTrend], top_n: int = 10) -> list[PlayerTrend]:
    """Get players trending down the most."""
    return sorted(
        [t for t in trends.values() if t.trending in ("cold", "cooling") and t.games_total >= 10],
        key=lambda t: t.trend_score,
    )[:top_n]


def get_minutes_gainers(trends: dict[str, PlayerTrend], top_n: int = 10) -> list[PlayerTrend]:
    """Get players gaining the most minutes recently."""
    return sorted(
        [t for t in trends.values() if t.minutes_trend > 1 and t.games_total >= 10],
        key=lambda t: t.minutes_trend,
        reverse=True,
    )[:top_n]
