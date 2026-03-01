"""
Real-time auction draft room API.

POST /draft/init — Start a new draft session
POST /draft/pick — Record a pick (player, team, bid)
GET  /draft/recommend/{player} — Get bid recommendation
GET  /draft/nominate — Get nomination suggestions
GET  /draft/available — Get remaining players with values
GET  /draft/budgets — Get all team budgets
GET  /draft/log — Get draft log
GET  /draft/bargains — Best bargains so far
GET  /draft/overpays — Biggest overpays so far
GET  /draft/summary — Draft status summary
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()

# Singleton draft room
_draft_room = None


def _get_room():
    global _draft_room
    if _draft_room is None:
        raise HTTPException(400, "Draft not initialized. POST /draft/init first.")
    return _draft_room


# ── Schemas ──

class DraftInitRequest(BaseModel):
    teams: list[str] = []  # Team names. If empty, uses league teams.
    budget: float = 233.0
    roster_size: int = 38
    my_team: str = "He Who Remains"


class PickRequest(BaseModel):
    player_name: str
    team: str
    bid: float
    position: str = ""


class PlayerValueResponse(BaseModel):
    name: str
    nba_team: str
    position: str
    fair_value: float
    tier: str
    z_total: float
    drafted: bool = False
    drafted_by: str = ""
    drafted_price: float = 0
    surplus: float = 0


class BidResponse(BaseModel):
    player_name: str
    fair_value: float
    max_bid: float
    action: str
    reason: str
    priority: float


class NominationResponse(BaseModel):
    player_name: str
    reason: str
    strategy: str


class BudgetResponse(BaseModel):
    team_name: str
    remaining: float
    spent: float
    players_drafted: int
    roster_spots_left: int
    max_bid: float


class PickResponse(BaseModel):
    player_name: str
    team: str
    bid: float
    fair_value: float
    surplus: float


# ── Endpoints ──

@router.post("/init", description="Initialize a new draft session.")
def init_draft(
    req: DraftInitRequest,
    state: LeagueState = Depends(get_state),
):
    global _draft_room
    from fantasy_engine.analytics.draft_room import DraftRoom

    # Use all NBA stats as the player pool
    if state.all_rostered_z is not None:
        stats = state.all_rostered_z
    else:
        stats = state.raw_df

    _draft_room = DraftRoom(
        player_stats=stats,
        num_teams=len(req.teams) if req.teams else 12,
        budget=req.budget,
        roster_size=req.roster_size,
        my_team=req.my_team,
    )

    # Register teams with their REAL remaining cap space
    teams = req.teams or list(state.team_names.values()) if state.team_names else []
    for t in teams:
        _draft_room.init_team(t)

    # Set actual budgets from current roster salaries
    if state.all_teams:
        for tid, tdata in state.all_teams.items():
            team_name = tdata["name"]
            rz = tdata.get("roster_z")
            if rz is not None and team_name in _draft_room._budgets:
                current_salary = rz["salary"].sum() if "salary" in rz.columns else 0
                budget = _draft_room._budgets[team_name]
                budget.spent = round(current_salary, 1)
                budget.remaining = round(req.budget - current_salary, 1)
                budget.players_drafted = len(rz)
                budget.roster_spots_left = max(0, req.roster_size - len(rz))
                budget.max_bid = round(budget.remaining - max(0, budget.roster_spots_left - 1) * 1.0, 1)

    return {
        "status": "draft initialized",
        "teams": len(teams),
        "players_available": len(_draft_room.get_available_players(9999)),
        "budget": req.budget,
    }


@router.post("/pick", description="Record a draft pick.")
def record_pick(req: PickRequest):
    room = _get_room()
    room.record_pick(req.player_name, req.team, req.bid, req.position)

    # Return the pick details
    pick = room._picks[-1]
    verdict = "BARGAIN" if pick.surplus > 3 else ("OVERPAY" if pick.surplus < -3 else "FAIR")
    return {
        "player": pick.player_name, "team": pick.team, "bid": pick.bid,
        "fair_value": pick.fair_value, "surplus": pick.surplus, "verdict": verdict,
    }


@router.get("/recommend/{player_name}", response_model=BidResponse,
            description="Get bid recommendation for a nominated player.")
def get_recommendation(player_name: str):
    room = _get_room()
    rec = room.get_bid_recommendation(player_name)
    return BidResponse(
        player_name=rec.player_name, fair_value=rec.fair_value,
        max_bid=rec.max_bid, action=rec.action,
        reason=rec.reason, priority=rec.priority,
    )


@router.get("/nominate", response_model=list[NominationResponse],
            description="Get nomination strategy suggestions.")
def get_nominations():
    room = _get_room()
    suggestions = room.get_nomination_suggestions()
    return [
        NominationResponse(
            player_name=s.player_name, reason=s.reason, strategy=s.strategy,
        )
        for s in suggestions
    ]


@router.get("/available", response_model=list[PlayerValueResponse],
            description="Get undrafted players with fair values.")
def get_available(top: int = Query(50)):
    room = _get_room()
    available = room.get_available_players(top)
    return [
        PlayerValueResponse(
            name=v.name, nba_team=v.nba_team, position=v.position,
            fair_value=v.fair_value, tier=v.tier, z_total=v.z_total,
        )
        for v in available
    ]


@router.get("/budgets", response_model=list[BudgetResponse],
            description="Get all team budgets and spending.")
def get_budgets():
    room = _get_room()
    return [
        BudgetResponse(
            team_name=b.team_name, remaining=round(b.remaining, 1),
            spent=round(b.spent, 1), players_drafted=b.players_drafted,
            roster_spots_left=b.roster_spots_left,
            max_bid=round(b.max_bid, 1),
        )
        for b in room.get_team_budgets()
    ]


@router.get("/log", response_model=list[PickResponse],
            description="Get all picks so far (most recent first).")
def get_log():
    room = _get_room()
    return [
        PickResponse(
            player_name=p.player_name, team=p.team, bid=p.bid,
            fair_value=p.fair_value, surplus=p.surplus,
        )
        for p in room.get_draft_log()
    ]


@router.get("/bargains", response_model=list[PickResponse],
            description="Get biggest bargains so far.")
def get_bargains(top: int = Query(10)):
    room = _get_room()
    return [
        PickResponse(
            player_name=p.player_name, team=p.team, bid=p.bid,
            fair_value=p.fair_value, surplus=p.surplus,
        )
        for p in room.get_bargains(top)
    ]


@router.get("/overpays", response_model=list[PickResponse],
            description="Get biggest overpays so far.")
def get_overpays(top: int = Query(10)):
    room = _get_room()
    return [
        PickResponse(
            player_name=p.player_name, team=p.team, bid=p.bid,
            fair_value=p.fair_value, surplus=p.surplus,
        )
        for p in room.get_overpays(top)
    ]


@router.get("/summary", description="Get current draft status.")
def get_summary():
    room = _get_room()
    return room.get_summary()
