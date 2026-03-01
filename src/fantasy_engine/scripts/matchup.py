"""
Phase 3 analysis: matchup prediction, lineup optimization, add/drop.

Usage:
    python -m fantasy_engine.scripts.matchup /path/to/Fantrax-Team-Roster.csv

Also tests Fantrax Beta API access if LEAGUE_ID is set.
"""
import sys
from pathlib import Path

import pandas as pd

from fantasy_engine.ingestion.fantrax_csv import parse_roster_csv
from fantasy_engine.analytics.zscores import compute_zscores, ALL_CATS
from fantasy_engine.analytics.matchup import (
    predict_matchup_analytical,
    predict_matchup_monte_carlo,
    format_matchup_report,
)
from fantasy_engine.analytics.lineup import optimize_lineup, format_lineup_report
from fantasy_engine.analytics.add_drop import (
    best_available, drop_candidates, best_swaps,
    format_add_drop_report,
)

LEAGUE_ID = "z9agcf24meqwg9yw"


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m fantasy_engine.scripts.matchup <csv_path>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    df = parse_roster_csv(csv_path)
    _estimate_shooting_volume(df)

    print(f"Loaded {len(df)} players from {csv_path.name}\n")

    # Compute z-scores and carry forward raw stats
    z_df = compute_zscores(df)
    carry_cols = [
        "salary", "age", "years_remaining", "status", "nba_team",
        "positions", "games_played", "fantrax_id", "name",
        # Raw stats needed for matchup prediction
        "pts", "reb", "ast", "stl", "blk", "tpm", "tov",
        "fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct",
    ]
    for col in carry_cols:
        if col in df.columns:
            z_df[col] = df[col].values

    # Split active vs reserve
    active_z = z_df[z_df["status"] == "Act"].copy()
    reserve_z = z_df[z_df["status"] == "Res"].copy()

    # ========================================================================
    # 1. MATCHUP PREDICTION
    # ========================================================================
    # Simulate a matchup: active roster vs a "league average" opponent
    # Create a synthetic opponent at league average z-scores
    print("Creating synthetic opponent (league average)...")
    opp_df = _create_average_opponent(z_df, n_players=11)

    print("\n--- ANALYTICAL PREDICTION ---")
    pred_a = predict_matchup_analytical(active_z, opp_df)
    print(format_matchup_report(pred_a))

    print("\n--- MONTE CARLO PREDICTION (10K simulations) ---")
    pred_mc = predict_matchup_monte_carlo(active_z, opp_df, n_simulations=10000)
    print(format_matchup_report(pred_mc))

    # ========================================================================
    # 2. LINEUP OPTIMIZATION
    # ========================================================================
    print("\n")
    # Optimize from full roster (active + reserve)
    rec = optimize_lineup(
        z_df,
        injured_players=[],  # Add injured names here
        punt_cats=[],
    )
    print(format_lineup_report(rec))

    # Also optimize with punt FT%
    print("\n--- LINEUP OPTIMIZED FOR PUNT FT% ---")
    rec_punt = optimize_lineup(
        z_df,
        punt_cats=["ft_pct"],
    )
    print(format_lineup_report(rec_punt))

    # ========================================================================
    # 3. ADD/DROP ANALYSIS
    # ========================================================================
    # Use reserve players as "free agents" to demonstrate
    # In production, this would be actual FAs from Fantrax
    print("\n")
    print("(Using reserve players as simulated free agents for demo)")
    adds = best_available(active_z, reserve_z, punt_cats=[])
    drops = drop_candidates(active_z, punt_cats=[])
    swaps_list = best_swaps(active_z, reserve_z, punt_cats=[])
    print(format_add_drop_report(adds, drops, swaps_list))

    # ========================================================================
    # 4. FANTRAX API TEST
    # ========================================================================
    print("\n")
    _test_fantrax_api()


def _create_average_opponent(z_df: pd.DataFrame, n_players: int = 11) -> pd.DataFrame:
    """Create a synthetic opponent at league-average stats."""
    # Pick players near zero z-score to simulate average
    z_df_sorted = z_df.copy()
    z_df_sorted["abs_z"] = z_df_sorted["z_total"].abs()
    avg_players = z_df_sorted.nsmallest(n_players, "abs_z")
    return avg_players.drop(columns=["abs_z"])


def _test_fantrax_api():
    """Test the Fantrax Beta API."""
    print("=" * 60)
    print("FANTRAX BETA API TEST")
    print("=" * 60)

    try:
        from fantasy_engine.ingestion.fantrax_api import (
            FantraxAPIClient, format_league_info
        )

        client = FantraxAPIClient(LEAGUE_ID)

        # League info
        print("\nFetching league info...")
        info = client.get_league_info()
        print(format_league_info(info))

        # Standings
        print("\nFetching standings...")
        standings = client.get_standings()
        if isinstance(standings, dict):
            print(f"  Teams in standings: {len(standings)}")
        elif isinstance(standings, list):
            print(f"  Standings entries: {len(standings)}")

        # Rosters
        print("\nFetching all team rosters...")
        rosters = client.get_team_rosters()
        if isinstance(rosters, dict):
            print(f"  Teams: {len(rosters)}")
            for team_id, players in list(rosters.items())[:2]:
                n = len(players) if isinstance(players, list) else "?"
                print(f"    {team_id}: {n} players")

        # ADP
        print("\nFetching ADP data...")
        adp = client.get_adp()
        if isinstance(adp, list):
            print(f"  ADP entries: {len(adp)}")
            if adp:
                top3 = adp[:3]
                for p in top3:
                    print(f"    #{p.get('ADP', '?'):.0f} {p.get('name', '?')} ({p.get('pos', '?')})")

        print("\n  Fantrax Beta API: ALL ENDPOINTS WORKING")

    except Exception as e:
        print(f"\n  Fantrax API test failed: {e}")


def _estimate_shooting_volume(df):
    """Estimate FGM, FGA, FTM, FTA from available stats."""
    df["fta"] = df["pts"] * 0.25
    df["ftm"] = df["fta"] * df["ft_pct"]
    fg_pts = (df["pts"] - df["ftm"]).clip(lower=0)
    df["fgm"] = ((fg_pts - df["tpm"]) / 2).clip(lower=0)
    df["fga"] = (df["fgm"] / df["fg_pct"].replace(0, float("nan"))).fillna(0)


if __name__ == "__main__":
    main()
