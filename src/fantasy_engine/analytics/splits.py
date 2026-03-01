"""
Player splits analysis: home/away, rest days, opponent strength.

Uses game logs to compute how players perform in different contexts,
improving daily lineup and matchup projections.
"""
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS


STAT_MAP = {
    "PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk",
    "FG3M": "tpm", "TOV": "tov", "MIN": "minutes",
    "FGM": "fgm", "FGA": "fga", "FTM": "ftm", "FTA": "fta",
}


@dataclass
class PlayerSplits:
    """Home/away and contextual splits for a player."""
    name: str
    games_total: int = 0
    # Home vs Away
    home_games: int = 0
    away_games: int = 0
    home_stats: dict[str, float] = field(default_factory=dict)  # cat -> per-game avg
    away_stats: dict[str, float] = field(default_factory=dict)
    # Significant differences
    home_advantage_cats: list[str] = field(default_factory=list)  # Cats better at home
    away_advantage_cats: list[str] = field(default_factory=list)  # Cats better away
    # Rest impact
    rested_stats: dict[str, float] = field(default_factory=dict)   # After 2+ days rest
    b2b_stats: dict[str, float] = field(default_factory=dict)      # Back-to-back games
    b2b_dropoff: dict[str, float] = field(default_factory=dict)    # % drop on B2B


def compute_splits(
    player_name: str,
    game_log: pd.DataFrame,
) -> PlayerSplits:
    """
    Compute home/away and rest-day splits from a game log.

    Game log columns expected: GAME_DATE, MATCHUP (contains @ for away),
    PTS, REB, AST, STL, BLK, FG3M, TOV, MIN, etc.
    """
    splits = PlayerSplits(name=player_name, games_total=len(game_log))

    if game_log.empty:
        return splits

    # Determine home/away from MATCHUP column
    if "MATCHUP" in game_log.columns:
        game_log = game_log.copy()
        game_log["is_home"] = ~game_log["MATCHUP"].str.contains("@", na=False)
    else:
        return splits

    home_games = game_log[game_log["is_home"]]
    away_games = game_log[~game_log["is_home"]]
    splits.home_games = len(home_games)
    splits.away_games = len(away_games)

    # Compute averages
    cats = ["PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV", "MIN"]
    for nba_col in cats:
        stat_key = STAT_MAP.get(nba_col, nba_col.lower())
        if nba_col not in game_log.columns:
            continue

        home_avg = float(home_games[nba_col].mean()) if not home_games.empty else 0
        away_avg = float(away_games[nba_col].mean()) if not away_games.empty else 0

        splits.home_stats[stat_key] = round(home_avg, 1)
        splits.away_stats[stat_key] = round(away_avg, 1)

        # Significant difference (>10% and >1 unit)
        if home_avg > 0 and away_avg > 0:
            diff_pct = (home_avg - away_avg) / away_avg * 100
            if diff_pct > 10 and abs(home_avg - away_avg) > 0.5:
                if stat_key == "tov":
                    splits.away_advantage_cats.append(stat_key)  # Lower TO at home = better
                else:
                    splits.home_advantage_cats.append(stat_key)
            elif diff_pct < -10 and abs(home_avg - away_avg) > 0.5:
                if stat_key == "tov":
                    splits.home_advantage_cats.append(stat_key)
                else:
                    splits.away_advantage_cats.append(stat_key)

    # Rest day analysis
    if "GAME_DATE" in game_log.columns:
        gl = game_log.copy()
        gl["GAME_DATE_PARSED"] = pd.to_datetime(gl["GAME_DATE"])
        gl = gl.sort_values("GAME_DATE_PARSED")

        # Calculate days rest between games
        gl["days_rest"] = gl["GAME_DATE_PARSED"].diff().dt.days.fillna(2)

        b2b = gl[gl["days_rest"] <= 1]
        rested = gl[gl["days_rest"] >= 2]

        for nba_col in cats:
            stat_key = STAT_MAP.get(nba_col, nba_col.lower())
            if nba_col not in gl.columns:
                continue

            rested_avg = float(rested[nba_col].mean()) if not rested.empty else 0
            b2b_avg = float(b2b[nba_col].mean()) if not b2b.empty else 0

            splits.rested_stats[stat_key] = round(rested_avg, 1)
            splits.b2b_stats[stat_key] = round(b2b_avg, 1)

            if rested_avg > 0 and b2b_avg > 0:
                dropoff = (b2b_avg - rested_avg) / rested_avg * 100
                splits.b2b_dropoff[stat_key] = round(dropoff, 1)

    return splits


def compute_all_splits(
    game_logs: dict[str, pd.DataFrame],
) -> dict[str, PlayerSplits]:
    """Compute splits for all players with game logs."""
    return {name: compute_splits(name, gl) for name, gl in game_logs.items()}


def get_b2b_alerts(
    splits: dict[str, PlayerSplits],
    min_dropoff_pct: float = -15.0,
) -> list[dict]:
    """
    Find players who drop off significantly on back-to-backs.

    These players should be benched on B2B nights.
    """
    alerts = []
    for name, s in splits.items():
        pts_drop = s.b2b_dropoff.get("pts", 0)
        min_drop = s.b2b_dropoff.get("minutes", 0)

        if pts_drop < min_dropoff_pct or min_drop < min_dropoff_pct:
            alerts.append({
                "player": name,
                "pts_dropoff": f"{pts_drop:+.0f}%",
                "min_dropoff": f"{min_drop:+.0f}%",
                "rested_pts": s.rested_stats.get("pts", 0),
                "b2b_pts": s.b2b_stats.get("pts", 0),
                "recommendation": f"Bench {name} on back-to-back nights",
            })

    alerts.sort(key=lambda a: float(a["pts_dropoff"].replace("%", "").replace("+", "")))
    return alerts
