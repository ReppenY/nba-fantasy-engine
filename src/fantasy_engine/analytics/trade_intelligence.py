"""
Trade Intelligence System.

Central module for all trade analysis: manager profiling, trade grading,
trade probability matrix, tradeable player detection, and proactive
trade suggestions.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from fantasy_engine.analytics.zscores import ALL_CATS
from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights
from fantasy_engine.analytics.valuation import age_curve_multiplier


# ── Data Models ──

class ManagerArchetype(str, Enum):
    CONTENDER = "contender"
    REBUILDER = "rebuilder"
    BUYER = "buyer"
    SELLER = "seller"
    TINKERER = "tinkerer"
    PASSIVE = "passive"


class TradeBlockReason(str, Enum):
    OVERPAID = "overpaid"
    REDUNDANT_CATS = "redundant_categories"
    INJURED = "injured"
    EXPIRING_NON_CONTENDER = "expiring_non_contender"
    AGE_DECLINING = "age_declining"
    LOW_PRODUCTION = "low_production"


@dataclass
class ManagerProfile:
    team_id: str
    team_name: str
    archetype: ManagerArchetype
    strongest_cats: list[str] = field(default_factory=list)
    weakest_cats: list[str] = field(default_factory=list)
    need_weights: dict[str, float] = field(default_factory=dict)
    total_z: float = 0
    total_salary: float = 0
    cap_room: float = 0
    avg_age: float = 0
    num_expiring: int = 0
    num_injured: int = 0
    waiver_moves: int = 0
    waiver_rank: int = 0
    preferred_positions: dict[str, int] = field(default_factory=dict)
    num_trades: int = 0
    players_traded_away: list[str] = field(default_factory=list)
    players_acquired: list[str] = field(default_factory=list)
    picks_traded_away: int = 0
    picks_acquired: int = 0
    trade_partners: list[str] = field(default_factory=list)
    core_players: list[str] = field(default_factory=list)
    expendable_players: list[str] = field(default_factory=list)
    buying_signal: float = 0.0
    trade_openness: float = 0.5


@dataclass
class TradeGrade:
    team_name: str
    letter_grade: str
    numeric_score: float
    z_change: float
    salary_change: float
    players_out: list[str] = field(default_factory=list)
    players_in: list[str] = field(default_factory=list)
    picks_out: int = 0
    picks_in: int = 0
    rationale: str = ""


@dataclass
class GradedTrade:
    date: str
    period: int
    teams: list[str]
    grades: list[TradeGrade]
    winner: str = ""
    fairness: str = ""  # "fair", "lopsided", "robbery"


@dataclass
class TradeProbability:
    team_a: str
    team_b: str
    probability: float
    complementary_score: float
    common_ground: list[str] = field(default_factory=list)
    historical_trades: int = 0


@dataclass
class TradeablePlayer:
    name: str
    team: str
    salary: float
    z_total: float
    age: int
    years_remaining: int
    reasons: list[str] = field(default_factory=list)
    trade_block_score: float = 0
    best_fit_teams: list[str] = field(default_factory=list)


@dataclass
class TradeSuggestion:
    rank: int
    give_players: list[str]
    receive_players: list[str]
    opponent: str
    my_benefit: float
    their_benefit: float
    acceptance_likelihood: float
    strategic_rationale: str
    salary_impact: float = 0
    my_cat_changes: dict[str, float] = field(default_factory=dict)


# ── Trade Intelligence System ──

class TradeIntelligence:
    """
    Central orchestrator for all trade intelligence.

    Lazily computes and caches: manager profiles, tradeable players,
    trade probability matrix, trade grades, and suggestions.
    """

    def __init__(
        self,
        all_teams: dict,
        my_team_id: str,
        my_roster_z: pd.DataFrame,
        salary_cap: float = 233.0,
        completed_trades: list | None = None,
        waiver_activity: dict | None = None,
        lineup_patterns: dict | None = None,
        injuries: list | None = None,
        all_rostered_z: pd.DataFrame | None = None,
    ):
        self._all_teams = all_teams
        self._my_team_id = my_team_id
        self._my_roster_z = my_roster_z
        self._salary_cap = salary_cap
        self._completed_trades = completed_trades or []
        self._waiver_activity = waiver_activity or {}
        self._lineup_patterns = lineup_patterns or {}
        self._injuries = injuries or []
        self._all_rostered_z = all_rostered_z

        # Caches
        self._profiles: dict[str, ManagerProfile] | None = None
        self._tradeable: dict[str, list[TradeablePlayer]] | None = None
        self._matrix: list[TradeProbability] | None = None
        self._graded: list[GradedTrade] | None = None

    # ── Public Properties (lazy) ──

    @property
    def manager_profiles(self) -> dict[str, ManagerProfile]:
        if self._profiles is None:
            self._profiles = self._build_profiles()
        return self._profiles

    @property
    def tradeable_players(self) -> dict[str, list[TradeablePlayer]]:
        if self._tradeable is None:
            self._tradeable = self._detect_tradeable()
        return self._tradeable

    @property
    def trade_matrix(self) -> list[TradeProbability]:
        if self._matrix is None:
            self._matrix = self._compute_matrix()
        return self._matrix

    @property
    def graded_trades(self) -> list[GradedTrade]:
        if self._graded is None:
            self._graded = self._grade_all_trades()
        return self._graded

    # ── Manager Profiling ──

    def _build_profiles(self) -> dict[str, ManagerProfile]:
        # Trade summary per team
        from fantasy_engine.ingestion.trade_history import get_team_trade_summary
        trade_summary = get_team_trade_summary(self._completed_trades)

        # Z-score rankings for archetype
        team_z_scores = {}
        for tid, tdata in self._all_teams.items():
            rz = tdata.get("roster_z")
            if rz is not None and not rz.empty and "z_total" in rz.columns:
                team_z_scores[tdata["name"]] = rz["z_total"].sum()

        z_sorted = sorted(team_z_scores.items(), key=lambda x: x[1], reverse=True)
        z_ranks = {name: i + 1 for i, (name, _) in enumerate(z_sorted)}

        # Waiver activity ranking
        waiver_sorted = sorted(self._waiver_activity.items(), key=lambda x: x[1].total_moves if hasattr(x[1], 'total_moves') else 0, reverse=True)
        waiver_ranks = {name: i + 1 for i, (name, _) in enumerate(waiver_sorted)}

        profiles = {}
        for tid, tdata in self._all_teams.items():
            name = tdata["name"]
            rz = tdata.get("roster_z")
            if rz is None or rz.empty:
                continue

            profile = analyze_team(rz)
            needs = get_need_weights(profile)

            total_z = rz["z_total"].sum() if "z_total" in rz.columns else 0
            total_salary = rz["salary"].sum() if "salary" in rz.columns else 0
            cap_room = self._salary_cap - total_salary
            avg_age = rz["age"].mean() if "age" in rz.columns else 0
            num_expiring = len(rz[rz["years_remaining"] <= 1]) if "years_remaining" in rz.columns else 0

            # Trade history
            ts = trade_summary.get(name, {})
            num_trades = ts.get("num_trades", 0)
            picks_out = len(ts.get("picks_traded_away", []))
            picks_in = len(ts.get("picks_acquired", []))

            # Waiver activity
            wa = self._waiver_activity.get(name)
            waiver_moves = wa.total_moves if wa and hasattr(wa, 'total_moves') else 0
            preferred_pos = wa.frequently_added_positions if wa and hasattr(wa, 'frequently_added_positions') else {}

            # Lineup patterns
            lp = self._lineup_patterns.get(name)
            core = lp.core_players if lp else []

            # Archetype
            rank = z_ranks.get(name, 6)
            if rank <= 3 and cap_room < 30:
                archetype = ManagerArchetype.CONTENDER
            elif rank >= 9 and (picks_in > picks_out or avg_age < 25):
                archetype = ManagerArchetype.REBUILDER
            elif waiver_moves >= 40:
                archetype = ManagerArchetype.TINKERER
            elif waiver_moves <= 15 and num_trades == 0:
                archetype = ManagerArchetype.PASSIVE
            elif picks_in > picks_out + 2:
                archetype = ManagerArchetype.SELLER
            elif picks_out > picks_in + 2:
                archetype = ManagerArchetype.BUYER
            else:
                archetype = ManagerArchetype.CONTENDER if rank <= 6 else ManagerArchetype.REBUILDER

            # Buying signal
            signal = 0.0
            if archetype == ManagerArchetype.CONTENDER:
                signal += 0.3
            elif archetype == ManagerArchetype.REBUILDER:
                signal -= 0.3
            if picks_out > picks_in:
                signal += 0.2
            elif picks_in > picks_out:
                signal -= 0.2

            # Trade openness
            openness = 0.5
            if num_trades > 0:
                openness += min(0.3, num_trades * 0.1)
            if waiver_moves > 30:
                openness += 0.1
            if archetype == ManagerArchetype.PASSIVE:
                openness -= 0.2

            profiles[tid] = ManagerProfile(
                team_id=tid,
                team_name=name,
                archetype=archetype,
                strongest_cats=profile.strongest_cats,
                weakest_cats=profile.weakest_cats,
                need_weights=needs,
                total_z=round(total_z, 1),
                total_salary=round(total_salary, 1),
                cap_room=round(cap_room, 1),
                avg_age=round(avg_age, 1),
                num_expiring=num_expiring,
                num_injured=0,
                waiver_moves=waiver_moves,
                waiver_rank=waiver_ranks.get(name, 12),
                preferred_positions=dict(preferred_pos) if isinstance(preferred_pos, dict) else {},
                num_trades=num_trades,
                players_traded_away=ts.get("players_traded_away", []),
                players_acquired=ts.get("players_acquired", []),
                picks_traded_away=picks_out,
                picks_acquired=picks_in,
                trade_partners=ts.get("trade_partners", []),
                core_players=core[:5],
                expendable_players=[],  # Filled below
                buying_signal=round(signal, 2),
                trade_openness=round(min(1.0, max(0.0, openness)), 2),
            )

        # Fill expendable players
        tradeable = self._detect_tradeable()
        for tid, players in tradeable.items():
            if tid in profiles:
                profiles[tid].expendable_players = [p.name for p in players[:5]]

        return profiles

    # ── Tradeable Player Detection ──

    def _detect_tradeable(self) -> dict[str, list[TradeablePlayer]]:
        result = {}

        for tid, tdata in self._all_teams.items():
            rz = tdata.get("roster_z")
            if rz is None or rz.empty:
                continue

            name = tdata["name"]
            profile = analyze_team(rz)
            players = []

            for _, row in rz.iterrows():
                pname = row.get("name", "")
                salary = row.get("salary", 0)
                z_total = row.get("z_total", 0)
                age = int(row.get("age", 0))
                yrs = int(row.get("years_remaining", 1))
                gp = int(row.get("games_played", 0))

                if gp == 0:
                    continue

                score = 0.0
                reasons = []

                # Overpaid
                z_per_dollar = z_total / max(salary, 0.5)
                if z_per_dollar < -0.5 and salary > 5:
                    score += 2.0
                    reasons.append(TradeBlockReason.OVERPAID.value)

                # Redundant categories
                player_best = []
                for cat in ALL_CATS:
                    z_col = f"z_{cat}"
                    if z_col in row.index and row[z_col] > 0.5:
                        player_best.append(cat)
                overlap = set(player_best) & set(profile.strongest_cats[:3])
                if len(overlap) >= 2:
                    score += 1.5
                    reasons.append(TradeBlockReason.REDUNDANT_CATS.value)

                # Expiring
                if yrs <= 1 and z_total > 0:
                    score += 1.0
                    reasons.append(TradeBlockReason.EXPIRING_NON_CONTENDER.value)

                # Age declining
                if age > 0 and age_curve_multiplier(age) < 0.6:
                    score += 1.5
                    reasons.append(TradeBlockReason.AGE_DECLINING.value)

                # Low production
                if z_total < 0 and salary > 3:
                    score += 1.0
                    reasons.append(TradeBlockReason.LOW_PRODUCTION.value)

                if score > 0:
                    # Find best fit teams
                    fits = self._find_best_fits(row, tid)
                    players.append(TradeablePlayer(
                        name=pname, team=name, salary=salary,
                        z_total=round(z_total, 2), age=age,
                        years_remaining=yrs, reasons=reasons,
                        trade_block_score=round(score, 1),
                        best_fit_teams=fits[:5],
                    ))

            players.sort(key=lambda p: p.trade_block_score, reverse=True)
            result[tid] = players

        return result

    def _find_best_fits(self, player_row, exclude_team_id: str) -> list[str]:
        """Find teams that would benefit most from this player."""
        fits = []
        for tid, tdata in self._all_teams.items():
            if tid == exclude_team_id:
                continue
            rz = tdata.get("roster_z")
            if rz is None or rz.empty:
                continue

            profile = analyze_team(rz)
            needs = get_need_weights(profile)

            fit_score = 0
            for cat in ALL_CATS:
                z_col = f"z_{cat}"
                if z_col in player_row.index:
                    fit_score += player_row[z_col] * needs.get(cat, 1.0)

            if fit_score > 1.0:
                fits.append((tdata["name"], fit_score))

        fits.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in fits]

    # ── Trade Probability Matrix ──

    def _compute_matrix(self) -> list[TradeProbability]:
        profiles = self.manager_profiles
        team_ids = list(profiles.keys())
        matrix = []

        # Count historical trades between pairs
        pair_history: dict[tuple, int] = defaultdict(int)
        for trade in self._completed_trades:
            if len(trade.teams) == 2:
                pair = tuple(sorted(trade.teams))
                pair_history[pair] += 1

        for i, tid_a in enumerate(team_ids):
            for tid_b in team_ids[i + 1:]:
                pa = profiles[tid_a]
                pb = profiles[tid_b]

                # Complementary score
                comp = 0.0
                common = []
                for cat in ALL_CATS:
                    wa = pa.need_weights.get(cat, 1.0)
                    wb = pb.need_weights.get(cat, 1.0)
                    if wa > 1.2 and wb < 0.8:
                        comp += (wa - wb)
                        common.append(f"{pa.team_name} needs {cat}")
                    if wb > 1.2 and wa < 0.8:
                        comp += (wb - wa)
                        common.append(f"{pb.team_name} needs {cat}")

                # Historical
                pair = tuple(sorted([pa.team_name, pb.team_name]))
                hist = pair_history.get(pair, 0)

                # Openness
                avg_openness = (pa.trade_openness + pb.trade_openness) / 2

                # Probability
                raw = 0.4 * min(comp / 10, 1.0) + 0.3 * avg_openness + 0.3 * min(hist / 3, 1.0)
                prob = 1 / (1 + np.exp(-5 * (raw - 0.3)))  # Sigmoid

                matrix.append(TradeProbability(
                    team_a=pa.team_name,
                    team_b=pb.team_name,
                    probability=round(float(prob), 3),
                    complementary_score=round(comp, 2),
                    common_ground=common[:5],
                    historical_trades=hist,
                ))

        matrix.sort(key=lambda x: x.probability, reverse=True)
        return matrix

    # ── Trade Grading ──

    def _grade_all_trades(self) -> list[GradedTrade]:
        graded = []
        for trade in self._completed_trades:
            graded.append(self._grade_trade(trade))
        return graded

    def _grade_trade(self, trade) -> GradedTrade:
        grades = []

        for team_name, moves in trade.movements.items():
            # Find this team's roster z-scores (use all_rostered for lookup)
            players_out = moves.get("players_out", [])
            players_in = moves.get("players_in", [])
            picks_out = len(moves.get("picks_out", []))
            picks_in = len(moves.get("picks_in", []))

            z_out = self._lookup_z_total(players_out)
            z_in = self._lookup_z_total(players_in)
            z_change = z_in - z_out

            salary_out = self._lookup_salary(players_out)
            salary_in = self._lookup_salary(players_in)
            salary_change = salary_in - salary_out

            # Score: z-change + pick value adjustment
            # Each pick ≈ 2.0 z-score value (rough estimate for dynasty)
            pick_value = (picks_in - picks_out) * 2.0
            score = z_change + pick_value * 0.5 + (salary_out - salary_in) * 0.05

            # Letter grade
            grade = self._score_to_grade(score)

            rationale = self._build_grade_rationale(
                team_name, players_out, players_in, z_change,
                picks_out, picks_in, salary_change, grade,
            )

            grades.append(TradeGrade(
                team_name=team_name,
                letter_grade=grade,
                numeric_score=round(score, 2),
                z_change=round(z_change, 2),
                salary_change=round(salary_change, 2),
                players_out=players_out,
                players_in=players_in,
                picks_out=picks_out,
                picks_in=picks_in,
                rationale=rationale,
            ))

        # Winner
        if len(grades) == 2:
            if grades[0].numeric_score > grades[1].numeric_score + 2:
                winner = grades[0].team_name
            elif grades[1].numeric_score > grades[0].numeric_score + 2:
                winner = grades[1].team_name
            else:
                winner = "Even"

            diff = abs(grades[0].numeric_score - grades[1].numeric_score)
            if diff > 5:
                fairness = "robbery"
            elif diff > 2:
                fairness = "lopsided"
            else:
                fairness = "fair"
        else:
            winner = "N/A"
            fairness = "N/A"

        return GradedTrade(
            date=trade.date,
            period=trade.period,
            teams=trade.teams,
            grades=grades,
            winner=winner,
            fairness=fairness,
        )

    def _lookup_z_total(self, player_names: list[str]) -> float:
        if self._all_rostered_z is None:
            return 0.0
        total = 0.0
        for name in player_names:
            match = self._all_rostered_z[self._all_rostered_z["name"].str.lower() == name.lower()]
            if not match.empty:
                total += match.iloc[0].get("z_total", 0)
        return total

    def _lookup_salary(self, player_names: list[str]) -> float:
        if self._all_rostered_z is None:
            return 0.0
        total = 0.0
        for name in player_names:
            match = self._all_rostered_z[self._all_rostered_z["name"].str.lower() == name.lower()]
            if not match.empty:
                total += match.iloc[0].get("salary", 0)
        return total

    @staticmethod
    def _score_to_grade(score: float) -> str:
        if score > 5.0: return "A+"
        if score > 3.5: return "A"
        if score > 2.5: return "A-"
        if score > 1.5: return "B+"
        if score > 0.5: return "B"
        if score > 0.0: return "B-"
        if score > -0.5: return "C+"
        if score > -1.5: return "C"
        if score > -2.5: return "C-"
        if score > -4.0: return "D"
        return "F"

    @staticmethod
    def _build_grade_rationale(team, p_out, p_in, z_change, picks_out, picks_in, sal_change, grade):
        parts = []
        if p_out:
            parts.append(f"Traded away {', '.join(p_out)}")
        if p_in:
            parts.append(f"Received {', '.join(p_in)}")
        if picks_in > 0:
            parts.append(f"+{picks_in} picks")
        if picks_out > 0:
            parts.append(f"-{picks_out} picks")
        parts.append(f"Z-change: {z_change:+.1f}")
        if sal_change != 0:
            parts.append(f"Salary: {sal_change:+.0f}")
        return ". ".join(parts)

    # ── Proactive Trade Suggestions ──

    def generate_suggestions(
        self,
        punt_cats: list[str] | None = None,
        max_suggestions: int = 20,
    ) -> list[TradeSuggestion]:
        if punt_cats is None:
            punt_cats = []

        profiles = self.manager_profiles
        tradeable = self.tradeable_players

        matrix = self.trade_matrix

        my_profile = analyze_team(self._my_roster_z)
        my_needs = get_need_weights(my_profile, punt_cats)

        # Find top trade partners
        my_name = None
        for tid, p in profiles.items():
            if tid == self._my_team_id:
                my_name = p.team_name
                break

        partner_probs = {
            tp.team_b if tp.team_a == my_name else tp.team_a: tp.probability
            for tp in matrix
            if tp.team_a == my_name or tp.team_b == my_name
        }

        suggestions = []
        rank = 0

        for tid, tdata in self._all_teams.items():
            if tid == self._my_team_id:
                continue

            opp_name = tdata["name"]
            opp_rz = tdata.get("roster_z")
            if opp_rz is None or opp_rz.empty:
                continue

            opp_profile = analyze_team(opp_rz)
            opp_needs = get_need_weights(opp_profile)
            partner_prob = partner_probs.get(opp_name, 0.3)

            # Get my tradeable players (expendables first, then all if empty)
            my_tradeable = tradeable.get(self._my_team_id, [])
            if not my_tradeable:
                # Fall back to all roster players sorted by z-total ascending (worst first = most tradeable)
                my_sorted = self._my_roster_z.sort_values("z_total", ascending=True)
                my_tradeable = [
                    TradeablePlayer(
                        name=row.get("name", ""), team="", salary=row.get("salary", 0),
                        z_total=round(row.get("z_total", 0), 2), age=int(row.get("age", 0)),
                        years_remaining=int(row.get("years_remaining", 1)),
                        reasons=[], trade_block_score=0,
                    )
                    for _, row in my_sorted.head(10).iterrows()
                    if row.get("games_played", 0) >= 5
                ]
            # For receiving: look at ALL their players (we want good ones, not their expendables)
            # But also check their expendables as realistic targets
            opp_expendable_names = {p.name for p in tradeable.get(tid, [])}

            # Try matching their players to my needs
            for _, their_row in opp_rz.iterrows():
                if their_row.get("games_played", 0) < 5:
                    continue

                # How much does this player help me?
                my_gain = 0.0
                for cat in ALL_CATS:
                    z_col = f"z_{cat}"
                    z_val = float(their_row.get(z_col, 0) or 0)
                    my_gain += z_val * my_needs.get(cat, 1.0)

                if my_gain <= 0:
                    continue

                their_name = their_row.get("name", "?")
                their_sal = float(their_row.get("salary", 0) or 0)

                # Find a matching player from my side they'd want
                for my_player in my_tradeable[:10]:
                    my_row = self._my_roster_z[self._my_roster_z["name"] == my_player.name]
                    if my_row.empty:
                        continue
                    my_row = my_row.iloc[0]

                    # No salary restriction — dynasty leagues trade across salary levels
                    # (the salary cap handles constraints, not individual trade balance)
                    sal_diff = abs(their_sal - float(my_row.get("salary", 0) or 0))

                    # How much does my player help them?
                    their_gain = 0.0
                    for cat in ALL_CATS:
                        z_val = float(my_row.get(f"z_{cat}", 0) or 0)
                        their_gain += z_val * opp_needs.get(cat, 1.0)

                    # In dynasty, teams might accept losing z-score for
                    # salary relief, picks, or youth — so only filter extreme losses
                    if their_gain < -15:
                        continue

                    # Position feasibility check
                    try:
                        from fantasy_engine.analytics.position_feasibility import check_trade_feasibility
                        their_name = their_row.get("name", "?")
                        recv_pos = {their_name: their_row.get("positions", "")}
                        feas = check_trade_feasibility(
                            self._my_roster_z, [my_player.name], [their_name], recv_pos,
                        )
                        if not feas.is_feasible:
                            continue  # Skip trades that break the roster
                    except Exception:
                        pass

                    # Acceptance likelihood
                    is_their_expendable = their_row.get("name", "") in opp_expendable_names
                    acceptance = min(0.95, max(0.05,
                        0.30 * min(their_gain / 5, 1.0) +
                        0.20 * (1 - sal_diff / 30) +
                        0.20 * partner_prob +
                        0.15 * profiles.get(tid, ManagerProfile(team_id="", team_name="", archetype=ManagerArchetype.PASSIVE)).trade_openness +
                        0.15 * (1.0 if is_their_expendable else 0.3)
                    ))

                    # Category changes
                    my_cats = {}
                    for cat in ALL_CATS:
                        z_col = f"z_{cat}"
                        delta = their_row.get(z_col, 0) - my_row.get(z_col, 0)
                        my_cats[cat] = round(delta, 2)

                    sal_impact = their_row.get("salary", 0) - my_row.get("salary", 0)

                    their_name = their_row.get("name", "?")
                    rationale = (
                        f"Trade your {my_player.name} (${my_row.get('salary', 0):.0f}) "
                        f"to {opp_name} for {their_name} (${their_row.get('salary', 0):.0f}). "
                        f"{opp_name} is a {profiles.get(tid, ManagerProfile(team_id='', team_name='', archetype=ManagerArchetype.PASSIVE)).archetype.value} "
                        f"who needs {', '.join(opp_profile.weakest_cats[:2])}."
                    )

                    rank += 1
                    suggestions.append(TradeSuggestion(
                        rank=rank,
                        give_players=[my_player.name],
                        receive_players=[their_name],
                        opponent=opp_name,
                        my_benefit=round(my_gain, 2),
                        their_benefit=round(their_gain, 2),
                        acceptance_likelihood=round(acceptance, 2),
                        strategic_rationale=rationale,
                        salary_impact=round(sal_impact, 1),
                        my_cat_changes=my_cats,
                    ))

        # Sort by combined value and acceptance
        suggestions.sort(
            key=lambda s: 0.5 * min(s.my_benefit, 10) / 10 + 0.5 * s.acceptance_likelihood,
            reverse=True,
        )

        # Re-rank
        for i, s in enumerate(suggestions[:max_suggestions]):
            s.rank = i + 1

        return suggestions[:max_suggestions]

    # ── Partners ──

    def get_best_partners(self) -> list[TradeProbability]:
        my_name = None
        for tid, tdata in self._all_teams.items():
            if tid == self._my_team_id:
                my_name = tdata["name"]
                break
        if not my_name:
            return []
        return [
            tp for tp in self.trade_matrix
            if tp.team_a == my_name or tp.team_b == my_name
        ]
