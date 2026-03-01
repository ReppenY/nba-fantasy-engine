"""
NBA advanced stats from nba_api.

Pulls usage rate, pace, and other advanced metrics that help
predict player value beyond basic box scores.
"""
import time
import pandas as pd


def get_advanced_stats(season: str = "2025-26", delay: float = 0.6) -> pd.DataFrame:
    """
    Fetch advanced stats for all NBA players.

    Returns DataFrame with:
    - USG_PCT: Usage rate (% of team possessions used)
    - PACE: Team pace (possessions per 48 min)
    - TS_PCT: True shooting percentage
    - AST_PCT: Assist percentage
    - REB_PCT: Rebound percentage
    - PIE: Player impact estimate
    """
    try:
        from nba_api.stats.endpoints import LeagueDashPlayerStats

        stats = LeagueDashPlayerStats(
            season=season,
            per_mode_detailed="PerGame",
            measure_type_detailed_defense="Advanced",
        )
        time.sleep(delay)
        df = stats.get_data_frames()[0]

        rename = {
            "PLAYER_ID": "nba_api_id",
            "PLAYER_NAME": "name",
            "TEAM_ABBREVIATION": "nba_team",
            "GP": "games_played",
            "MIN": "minutes",
            "USG_PCT": "usage_rate",
            "PACE": "pace",
            "TS_PCT": "ts_pct",
            "AST_PCT": "ast_pct",
            "REB_PCT": "reb_pct",
            "PIE": "pie",
            "OFF_RATING": "off_rating",
            "DEF_RATING": "def_rating",
            "NET_RATING": "net_rating",
        }

        available_renames = {k: v for k, v in rename.items() if k in df.columns}
        df = df.rename(columns=available_renames)

        keep = list(available_renames.values())
        available = [c for c in keep if c in df.columns]
        return df[available]

    except Exception as e:
        print(f"  Advanced stats fetch failed: {e}")
        return pd.DataFrame()


def merge_advanced_stats(
    player_df: pd.DataFrame,
    advanced_df: pd.DataFrame,
) -> pd.DataFrame:
    """Merge advanced stats into player DataFrame by name matching."""
    if advanced_df.empty:
        return player_df

    from fantasy_engine.ingestion.fantrax_api import _normalize_name

    player = player_df.copy()
    adv = advanced_df.copy()

    player["_match"] = player["name"].apply(_normalize_name)
    adv["_match"] = adv["name"].apply(_normalize_name)

    adv_lookup = {}
    for idx, row in adv.iterrows():
        adv_lookup[row["_match"]] = idx

    adv_cols = ["usage_rate", "pace", "ts_pct", "pie", "net_rating"]
    for col in adv_cols:
        if col not in player.columns:
            player[col] = 0.0

    for i, row in player.iterrows():
        norm = row["_match"]
        ai = adv_lookup.get(norm)
        if ai is not None:
            for col in adv_cols:
                if col in adv.columns:
                    player.at[i, col] = adv.at[ai, col]

    player = player.drop(columns=["_match"])
    return player
