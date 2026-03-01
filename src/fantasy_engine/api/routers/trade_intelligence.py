"""Trade Intelligence API endpoints."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


# ── Schemas ──

class ManagerProfileResponse(BaseModel):
    team_id: str
    team_name: str
    archetype: str
    strongest_cats: list[str]
    weakest_cats: list[str]
    total_z: float
    total_salary: float
    cap_room: float
    avg_age: float
    num_expiring: int
    waiver_moves: int
    num_trades: int
    picks_traded_away: int
    picks_acquired: int
    trade_partners: list[str]
    core_players: list[str]
    expendable_players: list[str]
    buying_signal: float
    trade_openness: float


class TradeGradeResponse(BaseModel):
    team_name: str
    letter_grade: str
    numeric_score: float
    z_change: float
    salary_change: float
    players_out: list[str]
    players_in: list[str]
    picks_out: int
    picks_in: int
    rationale: str


class GradedTradeResponse(BaseModel):
    date: str
    period: int
    teams: list[str]
    grades: list[TradeGradeResponse]
    winner: str
    fairness: str


class TradeProbResponse(BaseModel):
    team_a: str
    team_b: str
    probability: float
    complementary_score: float
    common_ground: list[str]
    historical_trades: int


class TradeablePlayerResponse(BaseModel):
    name: str
    team: str
    salary: float
    z_total: float
    age: int
    years_remaining: int
    reasons: list[str]
    trade_block_score: float
    best_fit_teams: list[str]


class TradeSuggestionResponse(BaseModel):
    rank: int
    give_players: list[str]
    receive_players: list[str]
    opponent: str
    my_benefit: float
    their_benefit: float
    acceptance_likelihood: float
    strategic_rationale: str
    salary_impact: float
    my_cat_changes: dict[str, float]


# ── Helper ──

def _get_intel(state: LeagueState):
    if not state.trade_intelligence:
        raise HTTPException(400, "Trade intelligence not loaded. Start with FANTASY_FULL=1 and provide trade CSV.")
    return state.trade_intelligence


# ── Endpoints ──

@router.get("/manager-profiles", response_model=list[ManagerProfileResponse])
def get_profiles(state: LeagueState = Depends(get_state)):
    intel = _get_intel(state)
    return [
        ManagerProfileResponse(
            team_id=p.team_id, team_name=p.team_name, archetype=p.archetype.value,
            strongest_cats=p.strongest_cats, weakest_cats=p.weakest_cats,
            total_z=p.total_z, total_salary=p.total_salary, cap_room=p.cap_room,
            avg_age=p.avg_age, num_expiring=p.num_expiring,
            waiver_moves=p.waiver_moves, num_trades=p.num_trades,
            picks_traded_away=p.picks_traded_away, picks_acquired=p.picks_acquired,
            trade_partners=p.trade_partners, core_players=p.core_players,
            expendable_players=p.expendable_players,
            buying_signal=p.buying_signal, trade_openness=p.trade_openness,
        )
        for p in sorted(intel.manager_profiles.values(), key=lambda p: p.total_z, reverse=True)
    ]


@router.get("/manager-profiles/{team_id}", response_model=ManagerProfileResponse)
def get_profile(team_id: str, state: LeagueState = Depends(get_state)):
    intel = _get_intel(state)
    p = intel.manager_profiles.get(team_id)
    if not p:
        # Try matching by name
        for tid, prof in intel.manager_profiles.items():
            if team_id.lower() in prof.team_name.lower():
                p = prof
                break
    if not p:
        raise HTTPException(404, f"Team not found: {team_id}")
    return ManagerProfileResponse(
        team_id=p.team_id, team_name=p.team_name, archetype=p.archetype.value,
        strongest_cats=p.strongest_cats, weakest_cats=p.weakest_cats,
        total_z=p.total_z, total_salary=p.total_salary, cap_room=p.cap_room,
        avg_age=p.avg_age, num_expiring=p.num_expiring,
        waiver_moves=p.waiver_moves, num_trades=p.num_trades,
        picks_traded_away=p.picks_traded_away, picks_acquired=p.picks_acquired,
        trade_partners=p.trade_partners, core_players=p.core_players,
        expendable_players=p.expendable_players,
        buying_signal=p.buying_signal, trade_openness=p.trade_openness,
    )


@router.get("/graded-trades", response_model=list[GradedTradeResponse])
def get_graded_trades(state: LeagueState = Depends(get_state)):
    intel = _get_intel(state)
    return [
        GradedTradeResponse(
            date=gt.date, period=gt.period, teams=gt.teams,
            grades=[
                TradeGradeResponse(
                    team_name=g.team_name, letter_grade=g.letter_grade,
                    numeric_score=g.numeric_score, z_change=g.z_change,
                    salary_change=g.salary_change,
                    players_out=g.players_out, players_in=g.players_in,
                    picks_out=g.picks_out, picks_in=g.picks_in,
                    rationale=g.rationale,
                )
                for g in gt.grades
            ],
            winner=gt.winner, fairness=gt.fairness,
        )
        for gt in intel.graded_trades
    ]


@router.get("/trade-matrix", response_model=list[TradeProbResponse])
def get_matrix(
    top: int = Query(20),
    state: LeagueState = Depends(get_state),
):
    intel = _get_intel(state)
    return [
        TradeProbResponse(
            team_a=tp.team_a, team_b=tp.team_b,
            probability=tp.probability, complementary_score=tp.complementary_score,
            common_ground=tp.common_ground, historical_trades=tp.historical_trades,
        )
        for tp in intel.trade_matrix[:top]
    ]


@router.get("/tradeable-players", response_model=list[TradeablePlayerResponse])
def get_tradeable(
    team_id: str = Query("", description="Filter to one team"),
    state: LeagueState = Depends(get_state),
):
    intel = _get_intel(state)
    players = []
    for tid, plist in intel.tradeable_players.items():
        if team_id and tid != team_id:
            continue
        for p in plist:
            players.append(TradeablePlayerResponse(
                name=p.name, team=p.team, salary=p.salary,
                z_total=p.z_total, age=p.age, years_remaining=p.years_remaining,
                reasons=p.reasons, trade_block_score=p.trade_block_score,
                best_fit_teams=p.best_fit_teams,
            ))
    players.sort(key=lambda p: p.trade_block_score, reverse=True)
    return players[:50]


@router.get("/suggestions", response_model=list[TradeSuggestionResponse])
def get_suggestions(
    punt: str = Query(""),
    top: int = Query(15),
    state: LeagueState = Depends(get_state),
):
    intel = _get_intel(state)
    punt_cats = [c.strip() for c in punt.split(",") if c.strip()] if punt else []
    suggestions = intel.generate_suggestions(punt_cats, top)
    return [
        TradeSuggestionResponse(
            rank=s.rank, give_players=s.give_players,
            receive_players=s.receive_players, opponent=s.opponent,
            my_benefit=s.my_benefit, their_benefit=s.their_benefit,
            acceptance_likelihood=s.acceptance_likelihood,
            strategic_rationale=s.strategic_rationale,
            salary_impact=s.salary_impact, my_cat_changes=s.my_cat_changes,
        )
        for s in suggestions
    ]


@router.get("/partners", response_model=list[TradeProbResponse])
def get_partners(state: LeagueState = Depends(get_state)):
    intel = _get_intel(state)
    partners = intel.get_best_partners()
    return [
        TradeProbResponse(
            team_a=tp.team_a, team_b=tp.team_b,
            probability=tp.probability, complementary_score=tp.complementary_score,
            common_ground=tp.common_ground, historical_trades=tp.historical_trades,
        )
        for tp in partners
    ]
