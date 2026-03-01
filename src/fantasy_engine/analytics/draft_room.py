"""
Real-time auction draft room assistant.

Tracks the live draft and provides:
- Fair auction values (adjusts as players are drafted)
- Bid/pass recommendations for each nominated player
- Budget tracking for all 12 teams
- Positional scarcity alerts
- Nomination strategy (who to nominate next)
- Value alerts (bargain/overpay)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from copy import deepcopy

from fantasy_engine.analytics.zscores import compute_zscores, ALL_CATS, ZScoreConfig
from fantasy_engine.analytics.draft import compute_auction_values


@dataclass
class DraftPick:
    player_name: str
    team: str
    bid: float
    fair_value: float
    surplus: float  # fair_value - bid (positive = bargain)
    position: str = ""


@dataclass
class TeamBudget:
    team_name: str
    starting_budget: float
    spent: float
    remaining: float
    players_drafted: int
    roster_spots_left: int
    max_bid: float  # Most they can bid on one player (budget - (spots_left - 1) * min_bid)
    positions_filled: dict[str, int] = field(default_factory=dict)
    picks: list[DraftPick] = field(default_factory=list)


@dataclass
class PlayerValue:
    name: str
    nba_team: str
    position: str
    fair_value: float
    tier: str
    z_total: float
    z_above_replacement: float
    drafted: bool = False
    drafted_by: str = ""
    drafted_price: float = 0
    surplus: float = 0  # If drafted: fair_value - price


@dataclass
class BidRecommendation:
    player_name: str
    fair_value: float
    max_bid: float       # Most you should pay
    action: str          # "bid", "strong_bid", "pass", "let_go"
    reason: str
    priority: float      # 0-1 how much you need this player
    fills_need: list[str]  # Categories this player helps


@dataclass
class NominationSuggestion:
    player_name: str
    reason: str
    strategy: str  # "target" (you want him), "drive_price" (make others spend), "value" (undervalued)


class DraftRoom:
    """
    Live auction draft assistant.

    Usage:
    1. Initialize with player pool (all NBA players with stats)
    2. Call compute_values() to get initial fair values
    3. As each pick happens, call record_pick()
    4. Call get_bid_recommendation() when a player is nominated
    5. Call get_nomination_suggestions() when it's your turn to nominate
    """

    def __init__(
        self,
        player_stats: pd.DataFrame,
        num_teams: int = 12,
        budget: float = 233.0,
        roster_size: int = 38,
        active_slots: int = 10,
        min_bid: float = 1.0,
        my_team: str = "",
    ):
        self._stats = player_stats.copy()
        self._num_teams = num_teams
        self._budget = budget
        self._roster_size = roster_size
        self._active_slots = active_slots
        self._min_bid = min_bid
        self._my_team = my_team

        # State
        self._picks: list[DraftPick] = []
        self._budgets: dict[str, TeamBudget] = {}
        self._values: list[PlayerValue] = []
        self._drafted_names: set[str] = set()

        # Initialize
        self._compute_initial_values()

    def _compute_initial_values(self):
        """Compute fair auction values for all players."""
        values = compute_auction_values(
            self._stats,
            salary_cap=self._budget,
            num_teams=self._num_teams,
            roster_size=self._roster_size,
            active_slots=self._active_slots,
            min_bid=self._min_bid,
        )
        self._values = [
            PlayerValue(
                name=v.name, nba_team=v.nba_team, position=v.positions or "",
                fair_value=v.auction_value, tier=v.tier,
                z_total=v.z_total, z_above_replacement=v.z_above_replacement,
            )
            for v in values
        ]

    def init_team(self, team_name: str):
        """Register a team in the draft."""
        self._budgets[team_name] = TeamBudget(
            team_name=team_name,
            starting_budget=self._budget,
            spent=0,
            remaining=self._budget,
            players_drafted=0,
            roster_spots_left=self._roster_size,
            max_bid=self._budget - (self._roster_size - 1) * self._min_bid,
        )

    def record_pick(self, player_name: str, team_name: str, bid: float, position: str = ""):
        """Record a draft pick and update all state."""
        # Find fair value
        fair = self._min_bid
        for v in self._values:
            if v.name.lower() == player_name.lower():
                fair = v.fair_value
                v.drafted = True
                v.drafted_by = team_name
                v.drafted_price = bid
                v.surplus = fair - bid
                break

        self._drafted_names.add(player_name.lower())

        pick = DraftPick(
            player_name=player_name, team=team_name, bid=bid,
            fair_value=fair, surplus=round(fair - bid, 1), position=position,
        )
        self._picks.append(pick)

        # Update team budget
        if team_name not in self._budgets:
            self.init_team(team_name)
        b = self._budgets[team_name]
        b.spent += bid
        b.remaining = b.starting_budget - b.spent
        b.players_drafted += 1
        b.roster_spots_left = self._roster_size - b.players_drafted
        b.max_bid = b.remaining - max(0, (b.roster_spots_left - 1)) * self._min_bid
        b.picks.append(pick)
        if position:
            b.positions_filled[position] = b.positions_filled.get(position, 0) + 1

        # Recompute values for remaining players (scarcity adjustment)
        self._adjust_values()

    def _adjust_values(self):
        """
        Adjust remaining player values based on:
        - How much total budget is left in the draft
        - Positional scarcity (if most Cs are gone, remaining Cs worth more)
        """
        total_remaining_budget = sum(b.remaining for b in self._budgets.values())
        total_remaining_spots = sum(b.roster_spots_left for b in self._budgets.values())
        undrafted = [v for v in self._values if not v.drafted]

        if not undrafted or total_remaining_spots <= 0:
            return

        # Budget inflation: if teams have more money left than expected, values go up
        expected_remaining = (len(undrafted) / (len(self._values) or 1)) * self._budget * self._num_teams
        if expected_remaining > 0:
            inflation = total_remaining_budget / expected_remaining
        else:
            inflation = 1.0

        for v in undrafted:
            v.fair_value = round(max(self._min_bid, v.fair_value * inflation), 1)

    def get_available_players(self, top_n: int = 50) -> list[PlayerValue]:
        """Get undrafted players sorted by fair value."""
        available = [v for v in self._values if not v.drafted]
        available.sort(key=lambda v: v.fair_value, reverse=True)
        return available[:top_n]

    def get_bid_recommendation(self, player_name: str) -> BidRecommendation:
        """Get a bid/pass recommendation for a nominated player."""
        # Find player
        player_val = None
        for v in self._values:
            if v.name.lower() == player_name.lower():
                player_val = v
                break

        if player_val is None:
            return BidRecommendation(
                player_name=player_name, fair_value=self._min_bid,
                max_bid=self._min_bid, action="pass",
                reason="Player not found in value rankings", priority=0,
                fills_need=[],
            )

        fair = player_val.fair_value

        # My budget
        my_budget = self._budgets.get(self._my_team)
        if my_budget:
            can_afford = my_budget.max_bid
        else:
            can_afford = self._budget

        # How much we need this player (based on z-score)
        priority = min(1.0, max(0.0, player_val.z_above_replacement / 8))

        # Max bid = fair value + small premium for high priority
        max_bid = min(can_afford, fair * (1 + 0.15 * priority))

        # Action
        if fair > can_afford:
            action = "pass"
            reason = f"Can't afford — fair value ${fair:.0f} exceeds your max bid ${can_afford:.0f}"
        elif player_val.tier == "elite":
            action = "strong_bid"
            reason = f"Elite player worth ${fair:.0f}. Go up to ${max_bid:.0f}."
        elif player_val.tier == "starter":
            action = "bid"
            reason = f"Solid starter worth ${fair:.0f}. Don't exceed ${max_bid:.0f}."
        elif priority < 0.2:
            action = "let_go"
            reason = f"Low priority. Fair value ${fair:.0f}, only bid if under ${fair * 0.7:.0f}."
        else:
            action = "bid"
            reason = f"Fair value ${fair:.0f}. Good pick up to ${max_bid:.0f}."

        return BidRecommendation(
            player_name=player_name,
            fair_value=round(fair, 1),
            max_bid=round(max_bid, 1),
            action=action,
            reason=reason,
            priority=round(priority, 2),
            fills_need=[],
        )

    def get_nomination_suggestions(self, top_n: int = 5) -> list[NominationSuggestion]:
        """Suggest who to nominate when it's your turn."""
        available = self.get_available_players(100)
        suggestions = []

        # Strategy 1: Nominate players you DON'T want to drive up others' spending
        # Find overvalued players that other teams need
        for v in available:
            if v.tier == "elite" and v.fair_value > 30:
                suggestions.append(NominationSuggestion(
                    player_name=v.name,
                    reason=f"Worth ${v.fair_value:.0f} — will drain other teams' budgets",
                    strategy="drive_price",
                ))
                if len(suggestions) >= 2:
                    break

        # Strategy 2: Nominate players you want at good value (less sexy names)
        for v in available:
            if v.tier == "starter" and v.z_total > 2 and v.fair_value < 15:
                suggestions.append(NominationSuggestion(
                    player_name=v.name,
                    reason=f"Undervalued at ${v.fair_value:.0f} with z:{v.z_total:+.1f}. "
                           f"Likely won't spark a bidding war.",
                    strategy="target",
                ))
                if len([s for s in suggestions if s.strategy == "target"]) >= 2:
                    break

        # Strategy 3: Late-draft value targets
        for v in available:
            if v.fair_value <= 3 and v.z_total > 0:
                suggestions.append(NominationSuggestion(
                    player_name=v.name,
                    reason=f"End-of-draft value. Only ${v.fair_value:.0f} but z:{v.z_total:+.1f}.",
                    strategy="value",
                ))
                if len([s for s in suggestions if s.strategy == "value"]) >= 1:
                    break

        return suggestions[:top_n]

    def get_team_budgets(self) -> list[TeamBudget]:
        """Get all team budgets sorted by remaining."""
        return sorted(self._budgets.values(), key=lambda b: b.remaining, reverse=True)

    def get_draft_log(self) -> list[DraftPick]:
        """Get all picks so far."""
        return list(reversed(self._picks))

    def get_bargains(self, top_n: int = 10) -> list[DraftPick]:
        """Get biggest bargains so far."""
        return sorted(self._picks, key=lambda p: p.surplus, reverse=True)[:top_n]

    def get_overpays(self, top_n: int = 10) -> list[DraftPick]:
        """Get biggest overpays so far."""
        return sorted(self._picks, key=lambda p: p.surplus)[:top_n]

    def get_summary(self) -> dict:
        """Get current draft status summary."""
        return {
            "picks_made": len(self._picks),
            "players_remaining": len([v for v in self._values if not v.drafted]),
            "teams": len(self._budgets),
            "total_spent": sum(b.spent for b in self._budgets.values()),
            "avg_pick_price": round(sum(p.bid for p in self._picks) / max(len(self._picks), 1), 1),
        }
