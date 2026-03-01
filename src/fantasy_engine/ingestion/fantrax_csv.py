"""
Parse Fantrax CSV roster exports.

CSV structure (from actual export):
Row 1: "","Player"  (header label row — skip)
Row 2: "ID","Pos","Player","Team","Eligible","Status","Age",
       "Opponent","Salary","Contract","GP","FG%","3PTM","FT%",
       "PTS","REB","AST","ST","BLK","TO"
Row 3+: Data rows
"""
import pandas as pd
from pathlib import Path


# Map CSV column names to our internal names
COLUMN_MAP = {
    "ID": "fantrax_id",
    "Pos": "roster_slot",
    "Player": "name",
    "Team": "nba_team",
    "Eligible": "positions",
    "Status": "status",
    "Age": "age",
    "Opponent": "opponent",
    "Salary": "salary",
    "Contract": "contract",
    "GP": "games_played",
    "FG%": "fg_pct",
    "3PTM": "tpm",
    "FT%": "ft_pct",
    "PTS": "pts",
    "REB": "reb",
    "AST": "ast",
    "ST": "stl",
    "BLK": "blk",
    "TO": "tov",
}


def parse_roster_csv(filepath: str | Path) -> pd.DataFrame:
    """Parse a Fantrax team roster CSV export into a clean DataFrame."""
    filepath = Path(filepath)
    df = pd.read_csv(filepath, skiprows=1)

    # Strip whitespace and quotes from column names
    df.columns = df.columns.str.strip().str.replace('"', '')

    # Rename columns
    df = df.rename(columns=COLUMN_MAP)

    # Drop empty rows
    df = df.dropna(subset=["name"])
    df = df[df["name"].str.strip() != ""]

    # Parse numeric columns
    numeric_cols = [
        "salary", "age", "games_played", "fg_pct", "tpm", "ft_pct",
        "pts", "reb", "ast", "stl", "blk", "tov",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Parse contract years remaining
    df["years_remaining"] = df["contract"].apply(_parse_contract_years)
    df["is_expiring"] = df["years_remaining"] <= 1

    # Clean string columns
    df["fantrax_id"] = df["fantrax_id"].str.strip().str.replace('"', '')
    df["name"] = df["name"].str.strip()
    df["nba_team"] = df["nba_team"].str.strip()
    df["positions"] = df["positions"].str.strip()
    df["status"] = df["status"].str.strip()
    df["roster_slot"] = df["roster_slot"].str.strip()

    return df


def _parse_contract_years(contract_str) -> int:
    """Convert '1st'->3, '2nd'->2, '3rd'->1, '2026'->1 (expiring)."""
    if pd.isna(contract_str):
        return 1
    contract_str = str(contract_str).strip()
    mapping = {"1st": 3, "2nd": 2, "3rd": 1}
    if contract_str in mapping:
        return mapping[contract_str]
    try:
        year = int(contract_str)
        return max(1, year - 2025)
    except ValueError:
        return 1
