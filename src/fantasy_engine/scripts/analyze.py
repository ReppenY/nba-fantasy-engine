"""
Phase 2 analysis: valuations, category profile, punt optimizer, trade evaluation.

Usage:
    python -m fantasy_engine.scripts.analyze /path/to/Fantrax-Team-Roster.csv
"""
import sys
from pathlib import Path

from fantasy_engine.ingestion.fantrax_csv import parse_roster_csv
from fantasy_engine.analytics.zscores import compute_zscores
from fantasy_engine.analytics.valuation import compute_valuations, format_valuations_report
from fantasy_engine.analytics.category_analysis import (
    analyze_team, format_team_profile,
)
from fantasy_engine.analytics.punting import find_optimal_punt, format_punt_report
from fantasy_engine.analytics.trade_eval import evaluate_trade, format_trade_report


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m fantasy_engine.scripts.analyze <csv_path>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    df = parse_roster_csv(csv_path)
    print(f"Loaded {len(df)} players from {csv_path.name}\n")

    # Estimate shooting volume (same as import_csv)
    _estimate_shooting_volume(df)

    # Compute z-scores
    z_df = compute_zscores(df)

    # Merge roster info into z_df
    for col in ["salary", "age", "years_remaining", "status", "contract",
                "nba_team", "positions", "games_played", "fantrax_id"]:
        if col in df.columns:
            z_df[col] = df[col].values

    # ========================================================================
    # 1. VALUATIONS
    # ========================================================================
    val_df = compute_valuations(z_df)
    print(format_valuations_report(val_df))

    # ========================================================================
    # 2. TEAM CATEGORY PROFILE (full roster)
    # ========================================================================
    print("\n")
    full_profile = analyze_team(z_df)
    print(format_team_profile(full_profile, "Full Roster"))

    # Active roster only
    active_z = z_df[z_df["status"] == "Act"]
    if len(active_z) > 0:
        print("\n")
        active_profile = analyze_team(active_z)
        print(format_team_profile(active_profile, "Active Roster"))

    # ========================================================================
    # 3. PUNT OPTIMIZER
    # ========================================================================
    print("\n")
    all_indices = list(range(len(df)))
    punt_results = find_optimal_punt(df, all_indices, max_punt_cats=2)
    print(format_punt_report(punt_results, top_n=15))

    # ========================================================================
    # 4. SAMPLE TRADE EVALUATIONS
    # ========================================================================
    print("\n")
    _run_sample_trades(z_df)


def _run_sample_trades(z_df):
    """Run a few interesting trade scenarios against the roster."""
    print("=" * 90)
    print("SAMPLE TRADE EVALUATIONS")
    print("=" * 90)

    # Trade 1: LeBron (old, expensive) for a hypothetical young player
    # Since we only have roster players, let's do roster-internal trades
    trades = [
        {
            "description": "Sell high on LeBron (41yo, $16.50) for young upside",
            "give": ["LeBron James"],
            "receive": ["Amen Thompson"],
            "punt": [],
        },
        {
            "description": "Swap aging expensive for cheap young contributors",
            "give": ["Giannis Antetokounmpo"],
            "receive": ["Miles McBride", "Bilal Coulibaly", "Goga Bitadze"],
            "punt": [],
        },
        {
            "description": "Punt FT% trade: gain blocks/rebounds, lose FT%",
            "give": ["Cameron Thomas"],
            "receive": ["Andre Drummond"],
            "punt": ["ft_pct", "tov"],
        },
    ]

    for trade in trades:
        print(f"\n--- {trade['description']} ---")
        try:
            evaluation = evaluate_trade(
                give_names=trade["give"],
                receive_names=trade["receive"],
                roster_z_df=z_df,
                punt_cats=trade["punt"],
            )
            print(format_trade_report(evaluation))
        except Exception as e:
            print(f"  Error: {e}")


def _estimate_shooting_volume(df):
    """Estimate FGM, FGA, FTM, FTA from available stats."""
    df["fta"] = df["pts"] * 0.25
    df["ftm"] = df["fta"] * df["ft_pct"]
    fg_pts = (df["pts"] - df["ftm"]).clip(lower=0)
    df["fgm"] = ((fg_pts - df["tpm"]) / 2).clip(lower=0)
    df["fga"] = (df["fgm"] / df["fg_pct"].replace(0, float("nan"))).fillna(0)


if __name__ == "__main__":
    main()
