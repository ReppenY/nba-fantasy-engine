"""
Full league data loader.

Pulls all 12 teams from Fantrax, merges with NBA stats,
computes z-scores for every rostered player, and identifies
real free agents (NBA players not on any fantasy team).
"""
import pandas as pd

from fantasy_engine.ingestion.fantrax_api import FantraxAPIClient, merge_with_nba_stats
from fantasy_engine.ingestion.nba_stats import NBAStatsClient
from fantasy_engine.analytics.zscores import compute_zscores


def load_full_league(
    league_id: str,
    my_team_id: str,
    season: str = "2025-26",
    min_games_fa: int = 10,
    min_minutes_fa: float = 10.0,
) -> dict:
    """
    Load the entire league: all teams, all players, free agents.

    Returns dict with:
        - "my_team": DataFrame of my roster with z-scores
        - "teams": dict of team_id -> {"name": str, "roster": DataFrame}
        - "free_agents": DataFrame of NBA players not on any team
        - "all_rostered": DataFrame of all rostered players
        - "nba_stats": DataFrame of all NBA player stats
        - "team_names": dict of team_id -> team_name
    """
    print("Loading full league data...")
    fx = FantraxAPIClient(league_id)

    # 1. Get team names
    team_names = fx.get_team_names()
    print(f"  League: {len(team_names)} teams")

    # 2. Get all rosters
    print("  Fetching all team rosters from Fantrax...")
    all_rosters_raw = {}
    raw = fx.get_team_rosters_raw()
    rosters_data = raw.get("rosters", {})

    for team_id in rosters_data:
        roster_df = fx.get_team_roster_df(team_id)
        all_rosters_raw[team_id] = roster_df

    total_players = sum(len(r) for r in all_rosters_raw.values())
    print(f"  Total rostered players: {total_players}")

    # 3. Fetch NBA stats (one bulk call)
    print(f"  Fetching NBA stats (season: {season})...")
    nba = NBAStatsClient()
    nba_stats = nba.get_all_player_averages(season)
    print(f"  NBA players with stats: {len(nba_stats)}")

    # 4. Merge each team's roster with stats
    print("  Merging rosters with stats...")
    teams = {}
    all_rostered_dfs = []
    rostered_nba_names = set()

    for team_id, roster_df in all_rosters_raw.items():
        merged = merge_with_nba_stats(roster_df, nba_stats)
        merged["fantasy_team_id"] = team_id
        merged["fantasy_team_name"] = team_names.get(team_id, team_id)
        merged["is_my_team"] = team_id == my_team_id

        teams[team_id] = {
            "name": team_names.get(team_id, team_id),
            "roster": merged,
        }
        all_rostered_dfs.append(merged)
        rostered_nba_names.update(merged["name"].str.lower().tolist())

    all_rostered = pd.concat(all_rostered_dfs, ignore_index=True)
    matched = all_rostered[all_rostered["games_played"] > 0]
    print(f"  Matched with NBA stats: {len(matched)}/{len(all_rostered)}")

    # 5. Compute z-scores for ALL rostered players together
    # This gives a league-wide perspective (not just within one team)
    print("  Computing league-wide z-scores...")
    league_z = compute_zscores(all_rostered)
    # Carry columns
    carry_cols = [c for c in all_rostered.columns if c not in league_z.columns]
    for col in carry_cols:
        league_z[col] = all_rostered[col].values

    # Split back into per-team DataFrames with league z-scores
    for team_id in teams:
        mask = league_z["fantasy_team_id"] == team_id
        teams[team_id]["roster_z"] = league_z[mask].copy()

    my_team_z = league_z[league_z["fantasy_team_id"] == my_team_id].copy()

    # 6. Identify free agents
    print("  Identifying free agents...")
    from fantasy_engine.ingestion.fantrax_api import _normalize_name

    rostered_normalized = {_normalize_name(n) for n in all_rostered["name"]}

    fa_mask = nba_stats["name"].apply(
        lambda n: _normalize_name(n) not in rostered_normalized
    )
    fa_stats = nba_stats[fa_mask].copy()

    # Filter to meaningful FAs (enough games/minutes)
    fa_stats = fa_stats[
        (fa_stats["games_played"] >= min_games_fa)
        & (fa_stats["minutes"] >= min_minutes_fa)
    ]

    # Compute z-scores for FAs using league-wide population stats
    if len(fa_stats) > 0:
        # Add placeholder columns that z-score engine might need
        fa_stats = fa_stats.copy()
        fa_stats["salary"] = 1.0
        fa_stats["status"] = "FA"
        fa_stats["years_remaining"] = 1
        fa_stats["age"] = 0
        fa_stats["positions"] = ""
        fa_z = compute_zscores(fa_stats)
        for col in fa_stats.columns:
            if col not in fa_z.columns:
                fa_z[col] = fa_stats[col].values
    else:
        fa_z = pd.DataFrame()

    print(f"  Free agents (>={min_games_fa} GP, >={min_minutes_fa} MIN): {len(fa_z)}")

    return {
        "my_team": my_team_z,
        "teams": teams,
        "free_agents": fa_z,
        "all_rostered": league_z,
        "nba_stats": nba_stats,
        "team_names": team_names,
    }
