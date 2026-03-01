"""
Draft pick valuation system.

Values future picks based on:
- Round (1st >> 5th)
- Year (sooner > later, but only slightly for 1-2 year gap)
- Original team strength (bad team's pick = higher pick = more valuable)
- Lottery vs playoff (bottom 6 get picks 1-6, top 6 get 7-12)
- Historical auction data from last draft (what did pick-level players cost?)

The league has 5 rounds, 12 teams per round.
Lottery: bottom 6 teams by record, worst gets #1.
Playoff: top 6 teams pick 7-12 based on final standing.
"""
from dataclasses import dataclass, field


@dataclass
class PickAsset:
    year: int
    round: int
    original_team: str
    original_team_id: str
    current_owner: str
    current_owner_id: str
    # Valuation
    estimated_pick_number: int = 0  # 1-12 within the round
    estimated_overall: int = 0      # Overall pick number (1-60)
    expected_z: float = 0.0         # Expected z-score of drafted player
    is_lottery: bool = False        # Will this team be in the lottery?
    confidence: str = "medium"      # How confident in the team's projected pick position


@dataclass
class PickPortfolio:
    """A team's complete draft pick portfolio."""
    team_name: str
    picks_owned: list[PickAsset]
    picks_traded_away: list[PickAsset]
    total_expected_z: float = 0.0
    num_first_rounders: int = 0
    num_lottery_picks: int = 0


# ── Pick Value Table ──
# These are ROOKIE DRAFT picks — not free agency auction.
# Values are EXPECTED Z-SCORE of the rookie drafted.
#
# Rookie production in year 1 is much lower than established stars:
# - #1 overall rookie (e.g., Wembanyama) might produce z:+3 to +5 in year 1
# - Mid-first-rounder: z:+1 to +2
# - Late first: z:0 to +1
# - Round 2+: z:-1 to 0 (development players, might not contribute immediately)
#
# Dynasty value is HIGHER than year-1 z because:
# - Rookies improve over 2-3 years
# - They're on cheap contracts ($1)
# - They have a long career ahead
#
# We use a "dynasty-adjusted" expected z that accounts for
# both immediate production AND future trajectory.

PICK_EXPECTED_Z = {
    # Round 1: lottery (picks 1-6) — top prospects
    (1, 1): 4.0, (1, 2): 3.5, (1, 3): 3.0, (1, 4): 2.5,
    (1, 5): 2.2, (1, 6): 2.0,
    # Round 1: late (picks 7-12) — solid prospects
    (1, 7): 1.7, (1, 8): 1.5, (1, 9): 1.2, (1, 10): 1.0,
    (1, 11): 0.8, (1, 12): 0.5,
    # Round 2 — deeper prospects, hit-or-miss
    (2, 1): 0.4, (2, 2): 0.3, (2, 3): 0.2, (2, 4): 0.1,
    (2, 5): 0.0, (2, 6): 0.0, (2, 7): -0.1, (2, 8): -0.2,
    (2, 9): -0.3, (2, 10): -0.3, (2, 11): -0.4, (2, 12): -0.5,
    # Round 3 — long shots
    (3, 1): -0.5, (3, 2): -0.6, (3, 3): -0.7, (3, 4): -0.7,
    (3, 5): -0.8, (3, 6): -0.8, (3, 7): -0.9, (3, 8): -0.9,
    (3, 9): -1.0, (3, 10): -1.0, (3, 11): -1.0, (3, 12): -1.0,
    # Round 4-5: lottery tickets
}


def estimate_pick_position(
    original_team_name: str,
    team_standings: list[dict],  # [{name, total_z, power_rank}] sorted by rank
) -> tuple[int, bool, str]:
    """
    Estimate where a team's pick will land.

    Bottom 6 = lottery (picks 1-6, worst gets 1st).
    Top 6 = playoff (picks 7-12).

    Returns: (estimated_pick_position_1_to_12, is_lottery, confidence)
    """
    num_teams = len(team_standings)
    if num_teams == 0:
        return 6, True, "low"

    # Find team's rank
    rank = None
    for i, t in enumerate(team_standings):
        if t.get("name", "") == original_team_name:
            rank = i + 1  # 1-indexed
            break

    if rank is None:
        return 6, True, "low"

    # Bottom 6 = lottery
    if rank > num_teams - 6:
        # Lottery position: worst team (rank 12) gets pick 1
        lottery_pos = num_teams - rank + 1  # 1 = worst, 6 = best of lottery
        return lottery_pos, True, "medium"
    else:
        # Playoff: rank 1 gets pick 12, rank 6 gets pick 7
        playoff_pos = 12 - rank + 1
        # Clamp to 7-12
        playoff_pos = max(7, min(12, playoff_pos))
        return playoff_pos, False, "medium"


def value_pick(
    year: int,
    round_num: int,
    pick_position: int,
    current_year: int = 2026,
) -> float:
    """
    Value a single draft pick as expected z-score of the player drafted.

    A Round 1 #1 pick is expected to produce ~z:+7.0 (a star).
    A Round 3 #12 pick is expected to produce ~z:-1.0 (bench player).

    Future picks are slightly discounted (5% per year) because of uncertainty.
    """
    base = PICK_EXPECTED_Z.get((round_num, pick_position))
    if base is None:
        if round_num == 4:
            base = -1.5
        elif round_num >= 5:
            base = -2.0
        else:
            base = 0.0

    # Future discount: 5% per year (smaller than dollar discount
    # because good players stay good)
    years_out = max(0, year - current_year)
    if base > 0:
        discount = 0.95 ** years_out
        return round(base * discount, 1)
    else:
        # Negative picks don't discount — they're already bad
        return round(base, 1)


def build_pick_portfolio(
    picks_data: list[dict],
    team_id: str,
    team_names: dict[str, str],
    team_standings: list[dict],
    current_year: int = 2026,
) -> PickPortfolio:
    """
    Build a complete pick portfolio for a team.

    Args:
        picks_data: Raw picks from Fantrax getDraftPicks API
        team_id: The team to build portfolio for
        team_names: team_id -> team_name mapping
        team_standings: Sorted list of team standings
    """
    owned = []
    traded_away = []
    team_name = team_names.get(team_id, team_id)

    for p in picks_data:
        orig_id = p.get("originalOwnerTeamId", "")
        curr_id = p.get("currentOwnerTeamId", "")
        year = p.get("year", 0)
        round_num = p.get("round", 0)

        orig_name = team_names.get(orig_id, orig_id)

        # Estimate pick position based on original team's strength
        pick_pos, is_lottery, confidence = estimate_pick_position(orig_name, team_standings)

        expected_z = value_pick(year, round_num, pick_pos, current_year)

        asset = PickAsset(
            year=year,
            round=round_num,
            original_team=orig_name,
            original_team_id=orig_id,
            current_owner=team_names.get(curr_id, curr_id),
            current_owner_id=curr_id,
            estimated_pick_number=pick_pos,
            estimated_overall=(round_num - 1) * 12 + pick_pos,
            expected_z=expected_z,
            is_lottery=is_lottery,
            confidence=confidence,
        )

        if curr_id == team_id:
            owned.append(asset)
        if orig_id == team_id and curr_id != team_id:
            traded_away.append(asset)

    # Sort
    owned.sort(key=lambda p: (p.year, p.round, p.estimated_pick_number))
    traded_away.sort(key=lambda p: (p.year, p.round))

    total_value = sum(p.expected_z for p in owned)
    first_rounders = len([p for p in owned if p.round == 1])
    lottery_picks = len([p for p in owned if p.round == 1 and p.is_lottery])

    return PickPortfolio(
        team_name=team_name,
        picks_owned=owned,
        picks_traded_away=traded_away,
        total_expected_z=round(total_value, 1),
        num_first_rounders=first_rounders,
        num_lottery_picks=lottery_picks,
    )


def build_all_portfolios(
    picks_data: list[dict],
    team_names: dict[str, str],
    team_standings: list[dict],
) -> dict[str, PickPortfolio]:
    """Build portfolios for all teams."""
    portfolios = {}
    for team_id in team_names:
        portfolios[team_id] = build_pick_portfolio(
            picks_data, team_id, team_names, team_standings,
        )
    return portfolios
