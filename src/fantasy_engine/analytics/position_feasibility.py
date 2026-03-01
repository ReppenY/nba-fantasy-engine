"""
Position feasibility checker.

Ensures trades and roster changes don't leave an illegal lineup.
Checks if the roster can fill all 10 active slots given position constraints:
  PG(1), SG(1), SF(1), PF(1), C(1), G(1), F(1), Flx(3)

A player's eligible positions come from Fantrax (e.g., "PG,SG,G,Flx").
"""
import pandas as pd
from dataclasses import dataclass, field
from scipy.optimize import linear_sum_assignment
import numpy as np


REQUIRED_SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "Flx", "Flx", "Flx"]

SLOT_ELIGIBILITY = {
    "PG": ["PG"],
    "SG": ["SG"],
    "SF": ["SF"],
    "PF": ["PF"],
    "C": ["C"],
    "G": ["PG", "SG"],
    "F": ["SF", "PF"],
    "Flx": ["PG", "SG", "SF", "PF", "C"],
}


@dataclass
class PositionAnalysis:
    """Analysis of a roster's position coverage."""
    can_field_legal_lineup: bool
    unfilled_slots: list[str] = field(default_factory=list)
    position_counts: dict[str, int] = field(default_factory=dict)  # PG: 3, SG: 5, etc.
    position_depth: dict[str, list[str]] = field(default_factory=dict)  # PG: [player1, player2]
    thin_positions: list[str] = field(default_factory=list)  # Positions with only 1 eligible player
    surplus_positions: list[str] = field(default_factory=list)  # Positions with 3+ eligible
    warnings: list[str] = field(default_factory=list)


@dataclass
class TradeFeasibility:
    """Position feasibility check for a trade."""
    is_feasible: bool
    positions_lost: dict[str, int] = field(default_factory=dict)  # Positions losing coverage
    positions_gained: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    roster_after: PositionAnalysis | None = None


def analyze_roster_positions(
    roster_df: pd.DataFrame,
    positions_col: str = "positions",
) -> PositionAnalysis:
    """
    Analyze a roster's position coverage.

    Checks if the roster can fill all 10 required slots.
    Identifies thin positions (only 1 eligible player) and surplus.
    """
    players = []
    for _, row in roster_df.iterrows():
        name = row.get("name", "")
        pos_str = str(row.get(positions_col, ""))
        positions = [p.strip() for p in pos_str.split(",") if p.strip()]
        players.append({"name": name, "positions": positions})

    # Count how many players are eligible for each position
    pos_counts: dict[str, int] = {}
    pos_depth: dict[str, list[str]] = {}
    for slot in ["PG", "SG", "SF", "PF", "C"]:
        eligible = [p["name"] for p in players if slot in p["positions"]]
        pos_counts[slot] = len(eligible)
        pos_depth[slot] = eligible

    # G = PG or SG eligible
    g_eligible = [p["name"] for p in players if "PG" in p["positions"] or "SG" in p["positions"] or "G" in p["positions"]]
    pos_counts["G"] = len(g_eligible)
    pos_depth["G"] = g_eligible

    # F = SF or PF eligible
    f_eligible = [p["name"] for p in players if "SF" in p["positions"] or "PF" in p["positions"] or "F" in p["positions"]]
    pos_counts["F"] = len(f_eligible)
    pos_depth["F"] = f_eligible

    # Flx = any position
    flx_eligible = [p["name"] for p in players]
    pos_counts["Flx"] = len(flx_eligible)

    # Check if we can fill all 10 slots using assignment
    can_fill, unfilled = _check_assignment(players, REQUIRED_SLOTS)

    thin = [pos for pos, count in pos_counts.items() if count <= 1 and pos != "Flx"]
    surplus = [pos for pos, count in pos_counts.items() if count >= 4 and pos != "Flx"]

    warnings = []
    for pos in thin:
        if pos_counts[pos] == 0:
            warnings.append(f"No players eligible for {pos} slot!")
        else:
            warnings.append(f"Only {pos_counts[pos]} player(s) eligible for {pos} — thin")

    return PositionAnalysis(
        can_field_legal_lineup=can_fill,
        unfilled_slots=unfilled,
        position_counts=pos_counts,
        position_depth=pos_depth,
        thin_positions=thin,
        surplus_positions=surplus,
        warnings=warnings,
    )


def check_trade_feasibility(
    roster_df: pd.DataFrame,
    give_names: list[str],
    receive_names: list[str],
    receive_positions: dict[str, str] | None = None,
) -> TradeFeasibility:
    """
    Check if a trade leaves the roster with a legal lineup.

    Args:
        roster_df: Current roster with 'name' and 'positions' columns.
        give_names: Players being traded away.
        receive_names: Players being received.
        receive_positions: Optional dict of received player name -> positions string.
                          If not provided, received players assumed to have "Flx" only.
    """
    if receive_positions is None:
        receive_positions = {}

    # Build post-trade roster
    remaining = roster_df[~roster_df["name"].isin(give_names)].copy()

    # Add received players
    new_rows = []
    for name in receive_names:
        positions = receive_positions.get(name, "PG,SG,SF,PF,C")  # Assume flexible if unknown
        new_rows.append({"name": name, "positions": positions})

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        post_trade = pd.concat([remaining, new_df], ignore_index=True)
    else:
        post_trade = remaining

    # Analyze before and after
    before = analyze_roster_positions(roster_df)
    after = analyze_roster_positions(post_trade)

    # Compute position changes
    pos_lost = {}
    pos_gained = {}
    for pos in ["PG", "SG", "SF", "PF", "C", "G", "F"]:
        diff = after.position_counts.get(pos, 0) - before.position_counts.get(pos, 0)
        if diff < 0:
            pos_lost[pos] = abs(diff)
        elif diff > 0:
            pos_gained[pos] = diff

    warnings = []
    if not after.can_field_legal_lineup:
        warnings.append(f"ILLEGAL LINEUP: Cannot fill slots {after.unfilled_slots} after this trade!")
    for pos in after.thin_positions:
        if pos not in before.thin_positions:
            warnings.append(f"Position {pos} becomes thin (only {after.position_counts[pos]} player)")

    return TradeFeasibility(
        is_feasible=after.can_field_legal_lineup,
        positions_lost=pos_lost,
        positions_gained=pos_gained,
        warnings=warnings,
        roster_after=after,
    )


def get_position_needs(roster_df: pd.DataFrame) -> dict[str, int]:
    """
    Get position needs: how many more players are needed at each position.

    Returns dict of position -> need_score (higher = more needed).
    0 = well covered, 1 = thin (only 1 eligible), 2+ = critically short.
    """
    analysis = analyze_roster_positions(roster_df)
    needs = {}
    for pos in ["PG", "SG", "SF", "PF", "C", "G", "F"]:
        count = analysis.position_counts.get(pos, 0)
        if count == 0:
            needs[pos] = 3  # Critical
        elif count == 1:
            needs[pos] = 2  # Thin
        elif count == 2:
            needs[pos] = 1  # OK but could use depth
        else:
            needs[pos] = 0  # Well covered
    return needs


def _check_assignment(
    players: list[dict],
    slots: list[str],
) -> tuple[bool, list[str]]:
    """
    Check if players can fill all required slots using linear assignment.

    Returns (can_fill_all, list_of_unfilled_slots).
    """
    n_players = len(players)
    n_slots = len(slots)

    if n_players < n_slots:
        return False, slots[n_players:]

    cost = np.full((n_players, n_slots), 1000)

    for i, player in enumerate(players):
        for j, slot in enumerate(slots):
            eligible = SLOT_ELIGIBILITY.get(slot, [slot])
            if any(p in eligible for p in player["positions"]):
                cost[i, j] = 0

    row_ind, col_ind = linear_sum_assignment(cost)

    unfilled = []
    for r, c in zip(row_ind, col_ind):
        if cost[r, c] >= 999:
            unfilled.append(slots[c])

    return len(unfilled) == 0, unfilled
