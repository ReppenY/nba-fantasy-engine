"""
Weekly-Optimized Daily Lineup Engine.

Maximizes end-of-week category wins by:
1. Simulating both teams' full week day-by-day
2. Classifying categories as target/concede/swing
3. Each day selecting 10 players that maximize weekly category win count
4. Using scarcity weights only for swing categories
5. Factoring consistency, trends, team context, schedule
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import date, timedelta
from scipy.optimize import linear_sum_assignment

from fantasy_engine.analytics.zscores import ALL_CATS, COUNTING_CATS, NEGATIVE_CATS


POSITION_SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "Flx", "Flx", "Flx"]
SLOT_ELIGIBILITY = {
    "PG": ["PG"], "SG": ["SG"], "SF": ["SF"], "PF": ["PF"], "C": ["C"],
    "G": ["PG", "SG"], "F": ["SF", "PF"],
    "Flx": ["PG", "SG", "SF", "PF", "C"],
}

COUNTING_STAT_MAP = {
    "pts": "pts", "reb": "reb", "ast": "ast", "stl": "stl",
    "blk": "blk", "tpm": "tpm", "tov": "tov",
}


@dataclass
class CategoryStrategy:
    category: str
    status: str           # locked_win, lean_win, swing, lean_loss, locked_loss
    my_projected: float
    opp_projected: float
    margin: float
    action: str           # "target" or "concede"
    scarcity_weight: float


@dataclass
class DailyLineup:
    date_str: str
    day_name: str
    active: list[dict]    # [{name, slot, games_today, contribution}]
    bench: list[str]
    available_count: int


@dataclass
class WeeklyPlan:
    period: int
    opponent: str
    categories: list[CategoryStrategy]
    target_cats: list[str]
    concede_cats: list[str]
    swing_cats: list[str]
    expected_wins: float
    daily_lineups: dict[str, DailyLineup]
    my_weekly_totals: dict[str, float]
    opp_weekly_totals: dict[str, float]


class WeeklyOptimizer:
    """
    Optimizes daily lineups across a full week to maximize category wins.
    """

    def __init__(
        self,
        my_roster_z: pd.DataFrame,
        opp_roster_z: pd.DataFrame,
        daily_schedule: dict[str, set[str]],
        opponent_name: str = "Opponent",
        period: int = 0,
        scarcity: list | None = None,
        trends: dict | None = None,
        opportunities: dict | None = None,
        injuries: list | None = None,
    ):
        self._my = my_roster_z.copy()
        self._opp = opp_roster_z.copy()
        self._daily_schedule = daily_schedule
        self._opponent_name = opponent_name
        self._period = period
        self._scarcity = scarcity or []
        self._trends = trends or {}
        self._opportunities = opportunities or {}
        self._injured_names = set()

        if injuries:
            for inj in injuries:
                name = inj.player_name if hasattr(inj, "player_name") else ""
                status = inj.status if hasattr(inj, "status") else ""
                if status == "Out":
                    self._injured_names.add(name.lower())

        # Compute adjusted per-game projections
        self._my_projections = self._compute_projections(self._my)
        self._opp_projections = self._compute_projections(self._opp)

        # Scarcity map
        self._scarcity_map = {}
        for s in self._scarcity:
            cat = s.category if hasattr(s, "category") else s.get("category", "")
            idx = s.scarcity_index if hasattr(s, "scarcity_index") else s.get("scarcity_index", 1.0)
            self._scarcity_map[cat] = idx

    def optimize(self) -> WeeklyPlan:
        """Run the full weekly optimization."""
        # Step 1: Project opponent's full week
        opp_totals = self._project_opponent_week()

        # Step 2: Initial category strategy (using basic lineup)
        my_initial_totals = self._project_my_week_basic()
        strategy = self._classify_categories(my_initial_totals, opp_totals)

        # Step 3: Determine target/concede
        target_cats, concede_cats, swing_cats = self._select_strategy(strategy)

        # Step 4: Optimize daily lineups for target categories
        daily_lineups = {}
        running_totals = {cat: 0.0 for cat in ALL_CATS}
        running_totals["fgm"] = 0.0
        running_totals["fga"] = 0.0
        running_totals["ftm"] = 0.0
        running_totals["fta"] = 0.0

        for day_str in sorted(self._daily_schedule.keys()):
            teams_today = self._daily_schedule[day_str]
            d = date.fromisoformat(day_str)
            day_name = d.strftime("%A")

            lineup = self._optimize_day(
                day_str, teams_today, target_cats, swing_cats,
                running_totals, opp_totals,
            )
            daily_lineups[day_str] = DailyLineup(
                date_str=day_str, day_name=day_name,
                active=lineup["active"], bench=lineup["bench"],
                available_count=lineup["available_count"],
            )

            # Update running totals with ALL categories for this day's active players
            for p in lineup["active"]:
                if p["plays_today"]:
                    name = p["name"]
                    proj = self._my_projections.get(name, {})
                    for cat in COUNTING_STAT_MAP:
                        running_totals[cat] += proj.get("stats", {}).get(cat, 0)
                    running_totals["fgm"] += proj.get("fgm", 0)
                    running_totals["fga"] += proj.get("fga", 0)
                    running_totals["ftm"] += proj.get("ftm", 0)
                    running_totals["fta"] += proj.get("fta", 0)

        # Compute final weekly totals
        my_totals = dict(running_totals)
        my_totals["fg_pct"] = my_totals["fgm"] / my_totals["fga"] if my_totals["fga"] > 0 else 0
        my_totals["ft_pct"] = my_totals["ftm"] / my_totals["fta"] if my_totals["fta"] > 0 else 0

        # Re-classify with final totals
        final_strategy = self._classify_categories(my_totals, opp_totals)
        expected_wins = sum(1 for s in final_strategy if s.status in ("locked_win", "lean_win"))
        expected_wins += sum(0.5 for s in final_strategy if s.status == "swing")

        return WeeklyPlan(
            period=self._period,
            opponent=self._opponent_name,
            categories=final_strategy,
            target_cats=target_cats,
            concede_cats=concede_cats,
            swing_cats=swing_cats,
            expected_wins=round(expected_wins, 1),
            daily_lineups=daily_lineups,
            my_weekly_totals={k: round(v, 2) for k, v in my_totals.items()},
            opp_weekly_totals={k: round(v, 2) for k, v in opp_totals.items()},
        )

    # ── Projections ──

    def _compute_projections(self, roster_df: pd.DataFrame) -> dict[str, dict]:
        """
        Compute adjusted per-game projections for each player.

        Tiered model: season baseline + trend + minutes + opportunity adjustment.
        """
        projections = {}
        for _, row in roster_df.iterrows():
            name = row.get("name", "")
            team = row.get("nba_team", "")
            gp = int(row.get("games_played", 0))

            if gp < 3 or name.lower() in self._injured_names:
                projections[name] = {"team": team, "stats": {s: 0 for s in COUNTING_STAT_MAP}, "fgm": 0, "fga": 0, "ftm": 0, "fta": 0}
                continue

            stats = {}
            for cat in COUNTING_STAT_MAP:
                base = row.get(cat, 0)

                # Trend adjustment
                trend = self._trends.get(name)
                if trend and hasattr(trend, "last_14") and trend.trend_score > 0.1:
                    recent = trend.last_14.get(cat, base)
                    base = base * 0.8 + recent * 0.2  # 20% shift toward recent

                # Minutes adjustment
                if trend and hasattr(trend, "minutes_trend") and trend.minutes_trend > 2.0:
                    if trend.minutes_season > 0:
                        base *= trend.minutes_recent / trend.minutes_season

                # Opportunity adjustment
                opp = self._opportunities.get(name)
                if opp and hasattr(opp, "opportunity_score") and opp.opportunity_score >= 3:
                    base *= 1 + 0.05 * opp.opportunity_score

                stats[cat] = round(base, 2)

            # FGM/FGA/FTM/FTA for percentage calculations
            fgm = row.get("fgm", 0)
            fga = row.get("fga", 0)
            ftm = row.get("ftm", 0)
            fta = row.get("fta", 0)

            projections[name] = {
                "team": team, "stats": stats,
                "fgm": fgm, "fga": fga, "ftm": ftm, "fta": fta,
                "positions": row.get("positions", ""),
                "consistency": row.get("consistency_rating", 0.5),
            }

        return projections

    def _project_opponent_week(self) -> dict[str, float]:
        """Project opponent's weekly totals assuming optimal play."""
        totals = {cat: 0.0 for cat in ALL_CATS}
        totals["fgm"] = 0.0
        totals["fga"] = 0.0
        totals["ftm"] = 0.0
        totals["fta"] = 0.0

        for name, proj in self._opp_projections.items():
            team = proj["team"]
            games = sum(1 for teams in self._daily_schedule.values() if team in teams)
            for cat in COUNTING_STAT_MAP:
                totals[cat] += proj["stats"].get(cat, 0) * games
            totals["fgm"] += proj["fgm"] * games
            totals["fga"] += proj["fga"] * games
            totals["ftm"] += proj["ftm"] * games
            totals["fta"] += proj["fta"] * games

        totals["fg_pct"] = totals["fgm"] / totals["fga"] if totals["fga"] > 0 else 0
        totals["ft_pct"] = totals["ftm"] / totals["fta"] if totals["fta"] > 0 else 0
        return {k: round(v, 2) for k, v in totals.items()}

    def _project_my_week_basic(self) -> dict[str, float]:
        """
        Project my weekly totals assuming I start the best 10 players each day.

        Uses the daily schedule to count games per player, then takes the
        top contributors (limited to roughly 10 per day via z_total ranking).
        """
        totals = {cat: 0.0 for cat in ALL_CATS}
        totals["fgm"] = 0.0
        totals["fga"] = 0.0
        totals["ftm"] = 0.0
        totals["fta"] = 0.0

        # For each day, simulate playing the best ~10 available players
        for day_str, teams_today in self._daily_schedule.items():
            # Find players with games today, sorted by approximate value
            day_players = []
            for name, proj in self._my_projections.items():
                if proj["team"] in teams_today:
                    total_stats = sum(proj["stats"].get(c, 0) for c in COUNTING_STAT_MAP)
                    day_players.append((name, proj, total_stats))

            # Sort by total stats, take top 10 (roster limit)
            day_players.sort(key=lambda x: x[2], reverse=True)
            for name, proj, _ in day_players[:10]:
                for cat in COUNTING_STAT_MAP:
                    totals[cat] += proj["stats"].get(cat, 0)
                totals["fgm"] += proj["fgm"]
                totals["fga"] += proj["fga"]
                totals["ftm"] += proj["ftm"]
                totals["fta"] += proj["fta"]

        totals["fg_pct"] = totals["fgm"] / totals["fga"] if totals["fga"] > 0 else 0
        totals["ft_pct"] = totals["ftm"] / totals["fta"] if totals["fta"] > 0 else 0
        return totals

    # ── Category Classification ──

    def _classify_categories(
        self, my_totals: dict, opp_totals: dict,
    ) -> list[CategoryStrategy]:
        """Classify each category by projected margin."""
        strategies = []

        # Estimate weekly std for margin calculation
        # Rough: counting stats std ≈ 15% of total, percentages ≈ 0.02
        for cat in ALL_CATS:
            my_val = my_totals.get(cat, 0)
            opp_val = opp_totals.get(cat, 0)

            if cat in ("fg_pct", "ft_pct"):
                std_est = 0.015
                diff = my_val - opp_val
            elif cat == "tov":
                std_est = max(abs(my_val) * 0.15, 1)
                diff = opp_val - my_val  # Lower TO is better, so flip
            else:
                std_est = max(abs(my_val) * 0.15, 1)
                diff = my_val - opp_val

            margin = diff / std_est if std_est > 0 else 0

            if margin > 1.5:
                status = "locked_win"
            elif margin > 0.5:
                status = "lean_win"
            elif margin > -0.5:
                status = "swing"
            elif margin > -1.5:
                status = "lean_loss"
            else:
                status = "locked_loss"

            strategies.append(CategoryStrategy(
                category=cat, status=status,
                my_projected=round(my_val, 2),
                opp_projected=round(opp_val, 2),
                margin=round(margin, 2),
                action="target",  # Will be set in _select_strategy
                scarcity_weight=self._scarcity_map.get(cat, 1.0),
            ))

        return strategies

    def _select_strategy(
        self, strategies: list[CategoryStrategy],
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Decide which categories to fight for vs concede.

        Goal: maximize total category wins (5+ = matchup win).
        Logic:
        - Locked wins: always keep (free wins)
        - Locked losses: always concede (can't win them)
        - Lean wins: target (high probability, protect them)
        - Swing: target (these decide the matchup)
        - Lean losses: target only the closest ones IF we need more cats to reach 5
        """
        target = []
        concede = []
        swing = []

        # First pass: categorize
        locked_wins = [s for s in strategies if s.status == "locked_win"]
        lean_wins = [s for s in strategies if s.status == "lean_win"]
        swings = [s for s in strategies if s.status == "swing"]
        lean_losses = sorted([s for s in strategies if s.status == "lean_loss"], key=lambda s: s.margin, reverse=True)
        locked_losses = [s for s in strategies if s.status == "locked_loss"]

        # Always target locked wins (free) and lean wins (protect)
        for s in locked_wins + lean_wins:
            s.action = "target"
            target.append(s.category)

        # Always target swings (these are the battleground)
        for s in swings:
            s.action = "target"
            target.append(s.category)
            swing.append(s.category)

        # If we still need more cats to get to 5, add the closest lean losses
        for s in lean_losses:
            if len(target) < 5:
                s.action = "target"
                target.append(s.category)
                swing.append(s.category)
            else:
                s.action = "concede"
                concede.append(s.category)

        # Locked losses: always concede
        for s in locked_losses:
            s.action = "concede"
            concede.append(s.category)

        return target, concede, swing

    # ── Daily Optimization ──

    def _optimize_day(
        self,
        day_str: str,
        teams_today: set[str],
        target_cats: list[str],
        swing_cats: list[str],
        running_totals: dict[str, float],
        opp_totals: dict[str, float],
    ) -> dict:
        """
        Optimize lineup for one day to maximize weekly target category outcomes.
        """
        # Filter to available players (have a game today, not injured)
        available = []
        all_players = []

        for _, row in self._my.iterrows():
            name = row.get("name", "")
            team = row.get("nba_team", "")
            plays = team in teams_today
            injured = name.lower() in self._injured_names

            if injured:
                continue

            proj = self._my_projections.get(name, {})
            positions = proj.get("positions", row.get("positions", ""))
            consistency = proj.get("consistency", 0.5)

            # Score this player for today: contribution to target categories only
            score = 0.0
            player_proj = {}
            if plays:
                for cat in target_cats:
                    val = proj.get("stats", {}).get(cat, 0)
                    # Weight swing categories by scarcity
                    weight = self._scarcity_map.get(cat, 1.0) if cat in swing_cats else 1.0
                    score += val * weight
                    player_proj[cat] = val

                # Percentage category contribution (approximate)
                player_proj["fgm"] = proj.get("fgm", 0)
                player_proj["fga"] = proj.get("fga", 0)
                player_proj["ftm"] = proj.get("ftm", 0)
                player_proj["fta"] = proj.get("fta", 0)

                # Consistency bonus for swing categories
                score *= (0.8 + 0.2 * consistency)

            all_players.append({
                "name": name, "positions": positions, "score": score,
                "plays_today": plays, "projections": player_proj,
                "team": team,
            })

        # Sort by score
        all_players.sort(key=lambda p: p["score"], reverse=True)

        # Assign to slots using linear assignment
        slots = POSITION_SLOTS
        n_players = len(all_players)
        n_slots = len(slots)

        if n_players == 0:
            return {"active": [], "bench": [], "available_count": 0}

        cost_matrix = np.full((n_players, n_slots), 1000.0)

        for i, player in enumerate(all_players):
            pos_list = [p.strip() for p in str(player["positions"]).split(",")]
            for j, slot in enumerate(slots):
                eligible = SLOT_ELIGIBILITY.get(slot, [slot])
                if any(p in eligible for p in pos_list):
                    cost_matrix[i, j] = -player["score"]

        if n_players >= n_slots:
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
        else:
            row_ind, col_ind = linear_sum_assignment(cost_matrix[:, :n_players].T)
            row_ind, col_ind = col_ind, row_ind

        active_set = set()
        active_list = []
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] >= 999:
                continue
            p = all_players[r]
            active_set.add(p["name"])
            active_list.append({
                "name": p["name"],
                "slot": slots[c],
                "plays_today": p["plays_today"],
                "score": round(p["score"], 2),
                "projections": p["projections"],
                "team": p["team"],
            })

        bench = [p["name"] for p in all_players if p["name"] not in active_set]
        avail = sum(1 for p in all_players if p["plays_today"])

        return {"active": active_list, "bench": bench, "available_count": avail}
