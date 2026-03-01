"""
Import a Fantrax CSV and compute z-scores.

Usage:
    python -m fantasy_engine.scripts.import_csv /path/to/Fantrax-Team-Roster.csv
"""
import sys
from pathlib import Path

import pandas as pd

from fantasy_engine.ingestion.fantrax_csv import parse_roster_csv
from fantasy_engine.analytics.zscores import compute_zscores, compute_punt_zscores, ALL_CATS


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m fantasy_engine.scripts.import_csv <csv_path>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    # Parse CSV
    print(f"Parsing {csv_path.name}...")
    df = parse_roster_csv(csv_path)
    print(f"  Found {len(df)} players\n")

    # The CSV has per-game averages but not FGM/FGA/FTM/FTA directly.
    # We need to estimate FGM/FGA from FG% and PTS, and FTM/FTA from FT%.
    # Rough estimation: FGA ≈ (PTS - FTM - 3PTM) / (2 * FG%) ... but this is circular.
    # Better approach: use the NBA stats data for accurate FGM/FGA/FTM/FTA.
    # For now, let's do a rough estimate to get the z-score engine working.
    _estimate_shooting_volume(df)

    # Compute z-scores
    print("Computing z-scores (all 9 categories)...")
    z_df = compute_zscores(df)

    # Merge with roster info
    z_df["salary"] = df["salary"].values
    z_df["contract"] = df["contract"].values
    z_df["years_remaining"] = df["years_remaining"].values
    z_df["status"] = df["status"].values
    z_df["roster_slot"] = df["roster_slot"].values

    # Sort by z_total
    z_df = z_df.sort_values("z_total", ascending=False).reset_index(drop=True)

    # Display rankings
    print("\n" + "=" * 100)
    print("PLAYER RANKINGS (by total z-score)")
    print("=" * 100)

    z_cat_cols = [f"z_{c}" for c in ALL_CATS]
    display_cols = ["name", "nba_team", "salary", "status"] + z_cat_cols + ["z_total"]

    for i, row in z_df.iterrows():
        rank = i + 1
        z_cats = " | ".join(f"{c.replace('z_', ''):>5s}:{row[f'z_{c}']:+.2f}" for c in ALL_CATS)
        print(
            f"  #{rank:2d}  {row['name']:25s}  ${row['salary']:5.1f}  "
            f"{'[A]' if row['status'] == 'Act' else '[R]'}  "
            f"Total:{row['z_total']:+.2f}  |  {z_cats}"
        )

    # Category breakdown for active roster
    print("\n" + "=" * 100)
    print("TEAM CATEGORY PROFILE (Active Roster Only)")
    print("=" * 100)
    active = z_df[z_df["status"] == "Act"]
    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        z_sum = active[z_col].sum()
        print(f"  {cat:>6s}: {z_sum:+.2f}")
    print(f"  {'TOTAL':>6s}: {active['z_total'].sum():+.2f}")

    # Value analysis
    print("\n" + "=" * 100)
    print("BEST VALUE (z-score per salary dollar)")
    print("=" * 100)
    z_df["z_per_dollar"] = z_df["z_total"] / z_df["salary"].clip(lower=0.5)
    value_sorted = z_df.sort_values("z_per_dollar", ascending=False).head(15)
    for i, row in value_sorted.iterrows():
        print(
            f"  {row['name']:25s}  ${row['salary']:5.1f}  "
            f"z:{row['z_total']:+.2f}  z/$:{row['z_per_dollar']:+.2f}  "
            f"yrs:{row.get('years_remaining', '?')}"
        )

    # Punt analysis
    print("\n" + "=" * 100)
    print("PUNT ANALYSIS: What if you punt FT% + TO?")
    print("=" * 100)
    punt_z = compute_punt_zscores(df, ["ft_pct", "tov"])
    punt_z["salary"] = df["salary"].values
    punt_z["status"] = df["status"].values
    punt_z = punt_z.sort_values("z_total", ascending=False).reset_index(drop=True)
    for i, row in punt_z.head(10).iterrows():
        rank = i + 1
        print(
            f"  #{rank:2d}  {row['name']:25s}  "
            f"z_total:{row['z_total']:+.2f}  (was: {z_df.loc[z_df['name'] == row['name'], 'z_total'].values[0]:+.2f})"
        )


def _estimate_shooting_volume(df: pd.DataFrame):
    """
    Estimate FGM, FGA, FTM, FTA from available stats.

    The CSV only has FG%, FT%, PTS, 3PTM. We need volume for the
    z-score impact calculation.

    Rough estimation:
    - FTM ≈ PTS * 0.2 (NBA average ~20% of points from FT)
    - FTA ≈ FTM / FT% (if FT% > 0)
    - 2PM ≈ (PTS - FTM - 3PTM * 3) / 2
    - FGM ≈ 2PM + 3PTM
    - FGA ≈ FGM / FG% (if FG% > 0)
    """
    # Better estimation using standard NBA ratios
    # Average player: ~44% of scoring from 2PT, ~33% from 3PT, ~22% from FT
    # FTM = FTA * FT%
    # For a rough estimate: FTA ≈ PTS * 0.25 (typical ratio)
    df["fta"] = df["pts"] * 0.25
    df["ftm"] = df["fta"] * df["ft_pct"]

    # Points from field goals = PTS - FTM
    fg_pts = (df["pts"] - df["ftm"]).clip(lower=0)
    # FGM = (fg_pts - tpm * 2) / 2 + tpm  [since 3PTM already counted as 3 pts]
    # Actually: fg_pts = 2 * (FGM - 3PTM) + 3 * 3PTM = 2*FGM + 3PTM
    # So: FGM = (fg_pts - 3PTM) / 2
    df["fgm"] = ((fg_pts - df["tpm"]) / 2).clip(lower=0)
    df["fga"] = (df["fgm"] / df["fg_pct"].replace(0, float("nan"))).fillna(0)

    return df


if __name__ == "__main__":
    main()
