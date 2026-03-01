"""
NBA stats ingestion via nba_api.

Uses LeagueDashPlayerStats for bulk player averages (single API call for all players).
Uses PlayerGameLog for individual game logs.
"""
import time
import pandas as pd


class NBAStatsClient:
    def __init__(self, delay: float = 0.6):
        self.delay = delay

    def get_all_player_averages(self, season: str = "2025-26") -> pd.DataFrame:
        """
        Fetch season averages for ALL NBA players in one call.

        Returns DataFrame with columns:
            PLAYER_ID, PLAYER_NAME, GP, MIN, FGM, FGA, FG_PCT,
            FG3M, FTM, FTA, FT_PCT, REB, AST, STL, BLK, TOV, PTS
        """
        from nba_api.stats.endpoints import LeagueDashPlayerStats

        stats = LeagueDashPlayerStats(
            season=season,
            per_mode_detailed="PerGame",
        )
        time.sleep(self.delay)
        df = stats.get_data_frames()[0]

        # Normalize column names to our convention
        rename = {
            "PLAYER_ID": "nba_api_id",
            "PLAYER_NAME": "name",
            "GP": "games_played",
            "MIN": "minutes",
            "FGM": "fgm",
            "FGA": "fga",
            "FG_PCT": "fg_pct",
            "FG3M": "tpm",
            "FTM": "ftm",
            "FTA": "fta",
            "FT_PCT": "ft_pct",
            "REB": "reb",
            "AST": "ast",
            "STL": "stl",
            "BLK": "blk",
            "TOV": "tov",
            "PTS": "pts",
            "TEAM_ABBREVIATION": "nba_team",
        }
        df = df.rename(columns=rename)

        # Compute age from AGE column if available, otherwise from PLAYER_AGE
        if "AGE" in df.columns:
            df["age"] = df["AGE"]
        elif "PLAYER_AGE" in df.columns:
            df["age"] = df["PLAYER_AGE"]
        else:
            df["age"] = 0

        # Keep only columns we need
        keep = list(rename.values()) + ["age"]
        available = [c for c in keep if c in df.columns]
        return df[available]

    def get_player_game_logs(
        self, player_id: int, season: str = "2025-26"
    ) -> pd.DataFrame:
        """Get game-by-game logs for a single player."""
        from nba_api.stats.endpoints import PlayerGameLog

        logs = PlayerGameLog(player_id=player_id, season=season)
        time.sleep(self.delay)
        return logs.get_data_frames()[0]
