"""
Parse Fantrax transaction history CSV.

CSV columns:
    Player, Team, Position, Type, Team (fantasy team), Bid, Pr, Grp/Max, Date (IST), Period

Transaction types: "Claim" (add) and "Drop"
Claims and drops are paired — same team, same period, same group number.
"""
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Transaction:
    date: str
    period: int
    team: str
    type: str          # "claim" or "drop"
    player: str
    nba_team: str
    position: str
    bid: float = 0.0


@dataclass
class WaiverMove:
    """A paired claim+drop (add/drop swap)."""
    date: str
    period: int
    team: str
    added: str
    dropped: str
    added_team: str = ""
    dropped_team: str = ""
    bid: float = 0.0


@dataclass
class TeamActivity:
    """Summary of a team's transaction behavior."""
    team_name: str
    total_claims: int = 0
    total_drops: int = 0
    total_moves: int = 0
    avg_bid: float = 0.0
    most_active_period: int = 0
    frequently_added_positions: dict = field(default_factory=dict)
    players_cycled: list[str] = field(default_factory=list)  # Players added then dropped


def parse_transactions_csv(filepath: str | Path) -> pd.DataFrame:
    """Parse transaction history CSV into a DataFrame."""
    df = pd.read_csv(filepath)
    df.columns = [
        "player", "nba_team", "position", "type", "fantasy_team",
        "bid", "priority", "group_max", "date", "period",
    ]
    df["bid"] = pd.to_numeric(df["bid"], errors="coerce").fillna(0)
    df["period"] = pd.to_numeric(df["period"], errors="coerce").fillna(0).astype(int)
    df["type"] = df["type"].str.lower().str.strip()
    df["player"] = df["player"].str.strip()
    df["fantasy_team"] = df["fantasy_team"].str.strip()
    return df


def get_waiver_moves(df: pd.DataFrame) -> list[WaiverMove]:
    """
    Pair claims with their corresponding drops.

    Claims and drops by the same team in the same period with the same
    group number are paired as a single waiver move.
    """
    moves = []
    # Group by team + period + extract group from "Grp/Max"
    for (team, period), group in df.groupby(["fantasy_team", "period"]):
        claims = group[group["type"] == "claim"]
        drops = group[group["type"] == "drop"]

        # Simple pairing: match by order (claims and drops appear in pairs)
        for i, (_, claim) in enumerate(claims.iterrows()):
            drop_player = ""
            drop_team = ""
            if i < len(drops):
                drop_row = drops.iloc[i]
                drop_player = drop_row["player"]
                drop_team = drop_row.get("nba_team", "")

            moves.append(WaiverMove(
                date=claim.get("date", ""),
                period=int(period),
                team=str(team),
                added=claim["player"],
                dropped=drop_player,
                added_team=claim.get("nba_team", ""),
                dropped_team=drop_team,
                bid=claim.get("bid", 0),
            ))

    moves.sort(key=lambda m: m.period, reverse=True)
    return moves


def analyze_team_activity(df: pd.DataFrame) -> dict[str, TeamActivity]:
    """Analyze transaction patterns per fantasy team."""
    results = {}

    for team, group in df.groupby("fantasy_team"):
        claims = group[group["type"] == "claim"]
        drops = group[group["type"] == "drop"]

        # Position frequency for claims
        pos_freq = {}
        for pos_str in claims["position"]:
            for p in str(pos_str).split(","):
                p = p.strip()
                if p:
                    pos_freq[p] = pos_freq.get(p, 0) + 1

        # Most active period
        period_counts = group["period"].value_counts()
        most_active = int(period_counts.index[0]) if not period_counts.empty else 0

        # Players cycled: added then dropped by same team
        added_players = set(claims["player"])
        dropped_players = set(drops["player"])
        cycled = sorted(added_players & dropped_players)

        results[str(team)] = TeamActivity(
            team_name=str(team),
            total_claims=len(claims),
            total_drops=len(drops),
            total_moves=len(claims) + len(drops),
            avg_bid=round(claims["bid"].mean(), 2) if len(claims) > 0 else 0,
            most_active_period=most_active,
            frequently_added_positions=pos_freq,
            players_cycled=cycled,
        )

    return results


def get_league_transaction_summary(df: pd.DataFrame) -> dict:
    """Get a high-level summary of all league transactions."""
    claims = df[df["type"] == "claim"]
    drops = df[df["type"] == "drop"]

    # Most claimed players
    most_claimed = claims["player"].value_counts().head(10).to_dict()

    # Most dropped players
    most_dropped = drops["player"].value_counts().head(10).to_dict()

    # Team activity ranking
    team_moves = df.groupby("fantasy_team").size().sort_values(ascending=False)

    # Activity by period (weekly)
    period_activity = df.groupby("period").size().to_dict()

    # Hot players: recently claimed (last 2 weeks)
    recent = claims[claims["period"] >= claims["period"].max() - 14]
    recently_hot = recent["player"].value_counts().head(10).to_dict()

    return {
        "total_transactions": len(df),
        "total_claims": len(claims),
        "total_drops": len(drops),
        "periods_covered": f"{df['period'].min()} to {df['period'].max()}",
        "most_claimed_players": most_claimed,
        "most_dropped_players": most_dropped,
        "most_active_teams": team_moves.head(5).to_dict(),
        "recently_hot_pickups": recently_hot,
    }


def format_transaction_report(df: pd.DataFrame) -> str:
    """Format a full transaction analysis report."""
    summary = get_league_transaction_summary(df)
    team_activity = analyze_team_activity(df)

    lines = []
    lines.append("=" * 90)
    lines.append("TRANSACTION HISTORY ANALYSIS")
    lines.append("=" * 90)
    lines.append(f"  Total transactions: {summary['total_transactions']}")
    lines.append(f"  Claims: {summary['total_claims']}  |  Drops: {summary['total_drops']}")
    lines.append(f"  Periods: {summary['periods_covered']}")

    lines.append("\n  MOST ACTIVE TEAMS:")
    for team, count in summary["most_active_teams"].items():
        lines.append(f"    {team:25s}  {count} moves")

    lines.append("\n  MOST CLAIMED PLAYERS (league-wide):")
    for player, count in list(summary["most_claimed_players"].items())[:8]:
        lines.append(f"    {player:25s}  claimed {count}x")

    lines.append("\n  MOST DROPPED PLAYERS (league-wide):")
    for player, count in list(summary["most_dropped_players"].items())[:8]:
        lines.append(f"    {player:25s}  dropped {count}x")

    lines.append("\n  RECENTLY HOT PICKUPS:")
    for player, count in list(summary["recently_hot_pickups"].items())[:8]:
        lines.append(f"    {player:25s}  {count}x recently")

    lines.append("\n  TEAM-BY-TEAM ANALYSIS:")
    for team_name, activity in sorted(team_activity.items(), key=lambda x: x[1].total_moves, reverse=True):
        lines.append(f"\n    {team_name}:")
        lines.append(f"      Moves: {activity.total_moves} ({activity.total_claims} adds, {activity.total_drops} drops)")
        if activity.players_cycled:
            lines.append(f"      Cycled (added then dropped): {', '.join(activity.players_cycled[:5])}")
        top_pos = sorted(activity.frequently_added_positions.items(), key=lambda x: x[1], reverse=True)[:3]
        if top_pos:
            lines.append(f"      Targets positions: {', '.join(f'{p}({n})' for p,n in top_pos)}")

    return "\n".join(lines)
