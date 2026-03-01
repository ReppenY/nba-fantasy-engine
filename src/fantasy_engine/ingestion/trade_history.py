"""
Parse Fantrax transaction history CSVs:
- Trades (player-for-player + draft picks)
- Lineup changes (who each manager starts/benches)
- Draft results (auction bids)
"""
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict


# ── Trades ──

@dataclass
class CompletedTrade:
    """A single completed trade between two (or more) teams."""
    date: str
    period: int
    teams: list[str]                              # Team names involved
    movements: dict[str, dict] = field(default_factory=dict)
    # movements[team_name] = {
    #   "players_out": [names], "players_in": [names],
    #   "picks_out": [pick_strings], "picks_in": [pick_strings],
    #   "drops": [names],  # players dropped to make room
    # }


def parse_trades_csv(filepath: str | Path) -> list[CompletedTrade]:
    """
    Parse Fantrax trade history CSV.

    Columns: Player, Team, Position, From, To, Date (IST), Period
    Groups rows by (Date, From, To) pairs to form complete trades.
    Handles draft picks and associated drops.
    """
    df = pd.read_csv(filepath)
    df.columns = ["player", "nba_team", "position", "from_team", "to_team", "date", "period"]
    df["period"] = pd.to_numeric(df["period"], errors="coerce").fillna(0).astype(int)

    # Group by date to find complete trades
    # Multiple rows with the same date = part of the same trade
    trades = []
    for date, group in df.groupby("date", sort=False):
        # Within a date, find distinct trade pairs (From->To combinations, excluding drops)
        real_moves = group[group["to_team"] != "(Drop)"]
        drops = group[group["to_team"] == "(Drop)"]

        if real_moves.empty:
            continue

        # Find unique team pairs involved in this date's trades
        # A trade between A and B will have moves A->B and B->A
        team_pairs = set()
        for _, row in real_moves.iterrows():
            pair = tuple(sorted([row["from_team"], row["to_team"]]))
            team_pairs.add(pair)

        # For each distinct trade (team pair), build the CompletedTrade
        for pair in team_pairs:
            team_a, team_b = pair
            movements = {
                team_a: {"players_out": [], "players_in": [], "picks_out": [], "picks_in": [], "drops": []},
                team_b: {"players_out": [], "players_in": [], "picks_out": [], "picks_in": [], "drops": []},
            }

            for _, row in real_moves.iterrows():
                fr, to = row["from_team"], row["to_team"]
                if {fr, to} != {team_a, team_b}:
                    continue

                player = row["player"]
                is_pick = "Draft Pick" in player

                if fr == team_a:
                    if is_pick:
                        movements[team_a]["picks_out"].append(player)
                        movements[team_b]["picks_in"].append(player)
                    else:
                        movements[team_a]["players_out"].append(player)
                        movements[team_b]["players_in"].append(player)
                else:
                    if is_pick:
                        movements[team_b]["picks_out"].append(player)
                        movements[team_a]["picks_in"].append(player)
                    else:
                        movements[team_b]["players_out"].append(player)
                        movements[team_a]["players_in"].append(player)

            # Add drops for teams in this trade
            for _, row in drops.iterrows():
                fr = row["from_team"]
                if fr in movements:
                    movements[fr]["drops"].append(row["player"])

            period = int(real_moves.iloc[0]["period"])
            trades.append(CompletedTrade(
                date=str(date).strip(),
                period=period,
                teams=[team_a, team_b],
                movements=movements,
            ))

    return trades


def get_team_trade_summary(trades: list[CompletedTrade]) -> dict[str, dict]:
    """
    Summarize trade activity per team.

    Returns dict of team_name -> {
        num_trades, players_traded_away, players_acquired,
        picks_traded_away, picks_acquired,
        trade_partners: [team_names],
    }
    """
    summaries: dict[str, dict] = defaultdict(lambda: {
        "num_trades": 0, "players_traded_away": [], "players_acquired": [],
        "picks_traded_away": [], "picks_acquired": [],
        "trade_partners": [], "drops_from_trades": [],
    })

    for trade in trades:
        for team, moves in trade.movements.items():
            s = summaries[team]
            s["num_trades"] += 1
            s["players_traded_away"].extend(moves["players_out"])
            s["players_acquired"].extend(moves["players_in"])
            s["picks_traded_away"].extend(moves["picks_out"])
            s["picks_acquired"].extend(moves["picks_in"])
            s["drops_from_trades"].extend(moves["drops"])
            # Track partners
            for other_team in trade.teams:
                if other_team != team and other_team not in s["trade_partners"]:
                    s["trade_partners"].append(other_team)

    return dict(summaries)


# ── Lineup Changes ──

@dataclass
class LineupPattern:
    """How a manager uses their lineup slots."""
    team_name: str
    total_changes: int
    always_active: list[str]       # Players never benched
    frequently_streamed: list[str] # Players often swapped in/out
    core_players: list[str]        # Top starters (most active appearances)


def parse_lineup_changes_csv(filepath: str | Path) -> pd.DataFrame:
    """Parse lineup changes CSV."""
    df = pd.read_csv(filepath)
    df.columns = ["player", "nba_team", "position", "fantasy_team", "from_slot", "to_slot", "date", "period"]
    df["period"] = pd.to_numeric(df["period"], errors="coerce").fillna(0).astype(int)
    return df


def analyze_lineup_patterns(df: pd.DataFrame) -> dict[str, LineupPattern]:
    """Analyze lineup change patterns per team."""
    patterns = {}

    for team, group in df.groupby("fantasy_team"):
        total = len(group)

        # Count how often each player is moved TO active vs TO reserve
        activations = group[group["to_slot"].str.contains("Active", case=False, na=False)]
        benchings = group[group["to_slot"].str.contains("Reserve", case=False, na=False)]

        activation_counts = activations["player"].value_counts()
        benching_counts = benchings["player"].value_counts()

        all_players = set(group["player"])
        benched_players = set(benchings["player"])
        always_active = sorted(all_players - benched_players)

        # Frequently streamed = high total movement count
        move_counts = group["player"].value_counts()
        streamed = [p for p, c in move_counts.items() if c >= 4]

        # Core players = most activations (they keep getting put back in)
        core = list(activation_counts.head(10).index)

        patterns[str(team)] = LineupPattern(
            team_name=str(team),
            total_changes=total,
            always_active=always_active[:10],
            frequently_streamed=streamed[:10],
            core_players=core,
        )

    return patterns


# ── Draft Results ──

@dataclass
class DraftPick:
    pick_number: int
    player_name: str
    nba_team: str
    position: str
    bid: float
    fantasy_team: str
    fantrax_id: str


def parse_draft_results_csv(filepath: str | Path) -> list[DraftPick]:
    """Parse draft results CSV."""
    df = pd.read_csv(filepath)
    df.columns = ["player_id", "pick", "position", "player", "nba_team", "bid", "fantasy_team", "time"]
    df["bid"] = pd.to_numeric(df["bid"], errors="coerce").fillna(0)

    picks = []
    for _, row in df.iterrows():
        picks.append(DraftPick(
            pick_number=int(row["pick"]),
            player_name=row["player"],
            nba_team=row.get("nba_team", ""),
            position=row.get("position", ""),
            bid=row["bid"],
            fantasy_team=row["fantasy_team"],
            fantrax_id=row.get("player_id", ""),
        ))
    return picks


def get_draft_spending_by_team(picks: list[DraftPick]) -> dict[str, dict]:
    """Summarize draft spending per team."""
    spending: dict[str, dict] = defaultdict(lambda: {
        "total_spent": 0.0, "picks": 0, "avg_bid": 0.0,
        "max_bid": 0.0, "max_bid_player": "",
        "positions_drafted": defaultdict(int),
    })

    for pick in picks:
        s = spending[pick.fantasy_team]
        s["total_spent"] += pick.bid
        s["picks"] += 1
        if pick.bid > s["max_bid"]:
            s["max_bid"] = pick.bid
            s["max_bid_player"] = pick.player_name
        s["positions_drafted"][pick.position] += 1

    for team, s in spending.items():
        if s["picks"] > 0:
            s["avg_bid"] = round(s["total_spent"] / s["picks"], 2)
        s["positions_drafted"] = dict(s["positions_drafted"])

    return dict(spending)
