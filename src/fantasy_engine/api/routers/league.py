"""League-wide endpoints: trade finder, alerts, free agents, all teams."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class TeamSummary(BaseModel):
    team_id: str
    name: str
    player_count: int
    total_z: float
    schedule_adjusted_z: float = 0
    avg_consistency: float = 0
    avg_games_remaining: float = 0
    playoff_games: float = 0
    strongest: list[str]
    weakest: list[str]
    power_rank: int = 0


class TradeProposalResponse(BaseModel):
    opponent_team: str
    give: list[str]
    receive: list[str]
    my_score: float
    their_score: float
    mutual_score: float
    salary_diff: float
    z_diff: float
    improves_me: list[str]
    improves_them: list[str]


class AlertResponse(BaseModel):
    type: str
    priority: str
    title: str
    detail: str
    player: str = ""
    action: str = ""


class FreeAgentResponse(BaseModel):
    name: str
    nba_team: str
    z_total: float
    pts: float = 0
    reb: float = 0
    ast: float = 0
    games_played: int = 0


@router.get("/teams", response_model=list[TeamSummary],
            description="Get summary of all 12 teams in the league.")
def get_all_teams(state: LeagueState = Depends(get_state)):
    if not state.all_teams:
        raise HTTPException(400, "Full league data not loaded. Use POST /admin/refresh-full")

    from fantasy_engine.analytics.category_analysis import analyze_team

    summaries = []
    for team_id, team in state.all_teams.items():
        roster_z = team.get("roster_z")
        if roster_z is None or roster_z.empty:
            continue
        profile = analyze_team(roster_z)

        # Advanced metrics
        sched_z = roster_z["schedule_adjusted_z"].sum() if "schedule_adjusted_z" in roster_z.columns else profile.total_z
        avg_cons = roster_z["consistency_rating"].mean() if "consistency_rating" in roster_z.columns else 0
        avg_games = roster_z["games_remaining"].mean() if "games_remaining" in roster_z.columns else 0
        playoff = roster_z["playoff_games"].mean() if "playoff_games" in roster_z.columns else 0

        summaries.append(TeamSummary(
            team_id=team_id,
            name=team["name"],
            player_count=len(roster_z),
            total_z=round(profile.total_z, 2),
            schedule_adjusted_z=round(sched_z, 2),
            avg_consistency=round(avg_cons, 3),
            avg_games_remaining=round(avg_games, 1),
            playoff_games=round(playoff, 1),
            strongest=profile.strongest_cats,
            weakest=profile.weakest_cats,
        ))
    summaries.sort(key=lambda t: t.schedule_adjusted_z, reverse=True)
    for i, s in enumerate(summaries):
        s.power_rank = i + 1
    return summaries


@router.get("/free-agents", response_model=list[FreeAgentResponse],
            description="Get best available free agents (NBA players not on any fantasy team).")
def get_free_agents(
    top: int = Query(30),
    state: LeagueState = Depends(get_state),
):
    if state.free_agents_z is None or state.free_agents_z.empty:
        raise HTTPException(400, "Full league data not loaded. Use POST /admin/refresh-full")

    fa = state.free_agents_z.nlargest(top, "z_total")
    return [
        FreeAgentResponse(
            name=row.get("name", ""),
            nba_team=row.get("nba_team", ""),
            z_total=round(row.get("z_total", 0), 2),
            pts=round(row.get("pts", 0), 1),
            reb=round(row.get("reb", 0), 1),
            ast=round(row.get("ast", 0), 1),
            games_played=int(row.get("games_played", 0)),
        )
        for _, row in fa.iterrows()
    ]


@router.get("/trade-finder", response_model=list[TradeProposalResponse],
            description="Auto-find mutually beneficial trades with other teams.")
def find_trades(
    punt: str = Query("", description="Comma-separated categories to punt"),
    top: int = Query(15),
    state: LeagueState = Depends(get_state),
):
    if not state.all_teams:
        raise HTTPException(400, "Full league data not loaded. Use POST /admin/refresh-full")

    from fantasy_engine.analytics.trade_finder import find_trades as _find

    punt_cats = [c.strip() for c in punt.split(",") if c.strip()] if punt else []
    proposals = _find(
        my_roster_z=state.z_df,
        all_teams=state.all_teams,
        my_team_id=state.team_id,
        punt_cats=punt_cats,
        top_n=top,
    )
    return [
        TradeProposalResponse(
            opponent_team=p.opponent_team,
            give=p.give, receive=p.receive,
            my_score=p.my_score, their_score=p.their_score,
            mutual_score=p.mutual_score, salary_diff=p.salary_diff,
            z_diff=p.z_diff, improves_me=p.improves_me, improves_them=p.improves_them,
        )
        for p in proposals
    ]


@router.get("/alerts", response_model=list[AlertResponse],
            description="Get actionable alerts: injuries, lineup issues, trade opportunities, hot FAs.")
def get_alerts(state: LeagueState = Depends(get_state)):
    from fantasy_engine.analytics.alerts import generate_alerts
    from fantasy_engine.analytics.trade_finder import find_trades as _find

    # Get trade proposals if league data available
    trade_proposals = None
    if state.all_teams:
        try:
            trade_proposals = _find(
                my_roster_z=state.z_df,
                all_teams=state.all_teams,
                my_team_id=state.team_id,
                top_n=3,
            )
        except Exception:
            pass

    alerts = generate_alerts(
        my_roster_z=state.z_df,
        free_agents_z=state.free_agents_z,
        injuries=state.injuries if state.injuries else None,
        trade_proposals=trade_proposals,
    )
    return [
        AlertResponse(
            type=a.type, priority=a.priority, title=a.title,
            detail=a.detail, player=a.player, action=a.action,
        )
        for a in alerts
    ]


class InjuryResponse(BaseModel):
    player: str
    team: str
    status: str
    description: str
    return_date: str
    days_until_return: int | None = None
    long_description: str = ""


@router.get("/injuries", response_model=list[InjuryResponse],
            description="Get injury report. Shows all NBA injuries or filtered to your roster.")
def get_injuries(
    roster_only: bool = Query(True, description="Filter to your roster players only"),
    state: LeagueState = Depends(get_state),
):
    from fantasy_engine.ingestion.injuries import (
        fetch_all_injuries, filter_roster_injuries, get_return_timeline,
    )

    # Fetch fresh injuries from ESPN
    all_injuries = fetch_all_injuries()

    if roster_only:
        all_injuries = filter_roster_injuries(all_injuries, state.roster_names)

    timeline = get_return_timeline(all_injuries)
    return [
        InjuryResponse(
            player=t["player"],
            team=t["team"],
            status=t["status"],
            description=t["description"],
            return_date=t["return_date"],
            days_until_return=t["days_until_return"],
            long_description=t["long_description"],
        )
        for t in timeline
    ]
