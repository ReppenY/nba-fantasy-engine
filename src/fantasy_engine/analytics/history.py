"""
Historical tracking: save daily snapshots, detect trends.

Stores z-scores and stats to SQLite daily. Computes:
- Z-score trajectory (rising/falling over last 7/14/30 days)
- Player trend detection
- Roster change tracking
"""
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DB_PATH = Path("data/history.db")


def init_history_db(db_path: Path | None = None):
    """Create history tables if they don't exist."""
    p = db_path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            snapshot_date TEXT NOT NULL,
            player_name TEXT NOT NULL,
            nba_team TEXT,
            fantasy_team TEXT,
            salary REAL,
            status TEXT,
            z_total REAL,
            z_pts REAL, z_reb REAL, z_ast REAL, z_stl REAL, z_blk REAL,
            z_tpm REAL, z_fg_pct REAL, z_ft_pct REAL, z_tov REAL,
            pts REAL, reb REAL, ast REAL, stl REAL, blk REAL,
            tpm REAL, fg_pct REAL, ft_pct REAL, tov REAL,
            games_played INTEGER,
            PRIMARY KEY (snapshot_date, player_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roster_changes (
            change_date TEXT NOT NULL,
            player_name TEXT NOT NULL,
            change_type TEXT,  -- 'added', 'dropped', 'traded_in', 'traded_out'
            from_team TEXT,
            to_team TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_snapshot(z_df: pd.DataFrame, db_path: Path | None = None):
    """Save current z-scores as a daily snapshot."""
    p = db_path or DB_PATH
    init_history_db(p)

    today = date.today().isoformat()
    conn = sqlite3.connect(str(p))

    for _, row in z_df.iterrows():
        conn.execute("""
            INSERT OR REPLACE INTO daily_snapshots VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            today, row.get("name", ""), row.get("nba_team", ""),
            row.get("fantasy_team_name", ""), row.get("salary", 0),
            row.get("status", ""),
            row.get("z_total", 0),
            row.get("z_pts", 0), row.get("z_reb", 0), row.get("z_ast", 0),
            row.get("z_stl", 0), row.get("z_blk", 0), row.get("z_tpm", 0),
            row.get("z_fg_pct", 0), row.get("z_ft_pct", 0), row.get("z_tov", 0),
            row.get("pts", 0), row.get("reb", 0), row.get("ast", 0),
            row.get("stl", 0), row.get("blk", 0), row.get("tpm", 0),
            row.get("fg_pct", 0), row.get("ft_pct", 0), row.get("tov", 0),
            int(row.get("games_played", 0)),
        ))

    conn.commit()
    conn.close()
    return today


def get_player_trend(
    player_name: str,
    days: int = 14,
    db_path: Path | None = None,
) -> dict:
    """
    Get a player's z-score trend over the last N days.

    Returns:
        {"dates": [...], "z_totals": [...], "trend": "rising"/"falling"/"stable",
         "z_change": float, "current_z": float}
    """
    p = db_path or DB_PATH
    if not p.exists():
        return {"error": "No history data yet. Run save_snapshot first."}

    conn = sqlite3.connect(str(p))
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    df = pd.read_sql_query(
        "SELECT snapshot_date, z_total FROM daily_snapshots "
        "WHERE player_name = ? AND snapshot_date >= ? ORDER BY snapshot_date",
        conn, params=(player_name, cutoff),
    )
    conn.close()

    if df.empty:
        return {"error": f"No history for {player_name}"}

    dates = df["snapshot_date"].tolist()
    z_totals = df["z_total"].tolist()

    if len(z_totals) >= 2:
        z_change = z_totals[-1] - z_totals[0]
        if z_change > 0.5:
            trend = "rising"
        elif z_change < -0.5:
            trend = "falling"
        else:
            trend = "stable"
    else:
        z_change = 0
        trend = "stable"

    return {
        "player": player_name,
        "dates": dates,
        "z_totals": [round(z, 2) for z in z_totals],
        "trend": trend,
        "z_change": round(z_change, 2),
        "current_z": round(z_totals[-1], 2) if z_totals else 0,
        "days_tracked": len(dates),
    }


def get_trending_players(
    days: int = 7,
    top_n: int = 10,
    db_path: Path | None = None,
) -> dict:
    """Get players with biggest z-score changes over N days."""
    p = db_path or DB_PATH
    if not p.exists():
        return {"rising": [], "falling": []}

    conn = sqlite3.connect(str(p))
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Get earliest and latest snapshot for each player in the window
    df = pd.read_sql_query("""
        SELECT player_name,
               MIN(CASE WHEN snapshot_date = (SELECT MIN(snapshot_date) FROM daily_snapshots WHERE snapshot_date >= ?) THEN z_total END) as z_start,
               MAX(CASE WHEN snapshot_date = (SELECT MAX(snapshot_date) FROM daily_snapshots) THEN z_total END) as z_end
        FROM daily_snapshots
        WHERE snapshot_date >= ?
        GROUP BY player_name
        HAVING z_start IS NOT NULL AND z_end IS NOT NULL
    """, conn, params=(cutoff, cutoff))
    conn.close()

    if df.empty:
        return {"rising": [], "falling": []}

    df["z_change"] = df["z_end"] - df["z_start"]

    rising = df.nlargest(top_n, "z_change")[["player_name", "z_change", "z_end"]].to_dict("records")
    falling = df.nsmallest(top_n, "z_change")[["player_name", "z_change", "z_end"]].to_dict("records")

    return {"rising": rising, "falling": falling}
