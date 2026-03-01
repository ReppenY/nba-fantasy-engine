"""Weekly-optimized daily lineup API."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class CategoryStrategyResponse(BaseModel):
    category: str
    status: str
    my_projected: float
    opp_projected: float
    margin: float
    action: str
    scarcity_weight: float


class DailyLineupResponse(BaseModel):
    date_str: str
    day_name: str
    active: list[dict]
    bench: list[str]
    available_count: int


class WeeklyPlanResponse(BaseModel):
    period: int
    opponent: str
    categories: list[CategoryStrategyResponse]
    target_cats: list[str]
    concede_cats: list[str]
    swing_cats: list[str]
    expected_wins: float
    daily_lineups: dict[str, DailyLineupResponse]
    my_weekly_totals: dict[str, float]
    opp_weekly_totals: dict[str, float]


@router.get("/plan", response_model=WeeklyPlanResponse,
            description="Get the full week plan: category strategy + daily lineups optimized for weekly category wins.")
def get_weekly_plan(state: LeagueState = Depends(get_state)):
    if not state.league_rules or not state.all_teams:
        raise HTTPException(400, "Full league data needed. Start with FANTASY_FULL=1")

    from fantasy_engine.ingestion.league_rules import get_current_matchup
    from fantasy_engine.ingestion.schedule import get_daily_schedule
    from fantasy_engine.analytics.weekly_optimizer import WeeklyOptimizer

    # Get current opponent
    matchup = get_current_matchup(state.league_rules, state.team_id, state.current_period)
    if not matchup:
        raise HTTPException(404, "No matchup found for current period")

    opp_id = matchup["opponent_id"]
    opp_data = state.all_teams.get(opp_id)
    if not opp_data or opp_data.get("roster_z") is None:
        raise HTTPException(404, "Opponent roster not found")

    # Get daily schedule for this week
    today = date.today()
    # Find this week's Monday
    mon = today - timedelta(days=today.weekday())
    sun = mon + timedelta(days=6)
    daily_schedule = get_daily_schedule(mon, sun)

    if not daily_schedule:
        raise HTTPException(500, "Could not fetch NBA schedule")

    # Run optimizer
    optimizer = WeeklyOptimizer(
        my_roster_z=state.z_df,
        opp_roster_z=opp_data["roster_z"],
        daily_schedule=daily_schedule,
        opponent_name=matchup["opponent_name"],
        period=state.current_period,
        scarcity=state.category_scarcity,
        trends=state.player_trends,
        opportunities=state.player_opportunities,
        injuries=state.injuries,
    )

    plan = optimizer.optimize()

    return WeeklyPlanResponse(
        period=plan.period,
        opponent=plan.opponent,
        categories=[
            CategoryStrategyResponse(
                category=c.category, status=c.status,
                my_projected=c.my_projected, opp_projected=c.opp_projected,
                margin=c.margin, action=c.action, scarcity_weight=c.scarcity_weight,
            ) for c in plan.categories
        ],
        target_cats=plan.target_cats,
        concede_cats=plan.concede_cats,
        swing_cats=plan.swing_cats,
        expected_wins=plan.expected_wins,
        daily_lineups={
            k: DailyLineupResponse(
                date_str=v.date_str, day_name=v.day_name,
                active=v.active, bench=v.bench[:10],
                available_count=v.available_count,
            ) for k, v in plan.daily_lineups.items()
        },
        my_weekly_totals=plan.my_weekly_totals,
        opp_weekly_totals=plan.opp_weekly_totals,
    )


@router.get("/today",
            description="Get today's recommended lineup with rationale.")
def get_today(state: LeagueState = Depends(get_state)):
    plan_response = get_weekly_plan(state)
    today_str = date.today().isoformat()

    if today_str in plan_response.daily_lineups:
        today_lineup = plan_response.daily_lineups[today_str]
    else:
        # Find closest day
        for day_str, lineup in plan_response.daily_lineups.items():
            today_lineup = lineup
            break

    return {
        "date": today_str,
        "opponent": plan_response.opponent,
        "strategy": {
            "target": plan_response.target_cats,
            "concede": plan_response.concede_cats,
            "swing": plan_response.swing_cats,
        },
        "lineup": today_lineup,
        "expected_wins": plan_response.expected_wins,
    }


@router.get("/strategy",
            description="Get category strategy: which cats to target vs concede.")
def get_strategy(state: LeagueState = Depends(get_state)):
    plan_response = get_weekly_plan(state)
    return {
        "opponent": plan_response.opponent,
        "categories": plan_response.categories,
        "target": plan_response.target_cats,
        "concede": plan_response.concede_cats,
        "swing": plan_response.swing_cats,
        "expected_wins": plan_response.expected_wins,
    }
