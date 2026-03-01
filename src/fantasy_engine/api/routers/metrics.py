"""Advanced metrics endpoints: schedule, consistency, scarcity."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class PlayerMetricsResponse(BaseModel):
    name: str
    z_total: float = 0
    schedule_adjusted_z: float = 0
    ros_value: float = 0
    consistency_rating: float = 0
    games_remaining: int = 0
    games_this_week: int = 0
    playoff_games: int = 0
    schedule_factor: float = 1.0
    weekly_ceiling: float = 0
    weekly_floor: float = 0
    minutes_trend: float = 0


class ScarcityResponse(BaseModel):
    category: str
    scarcity_index: float
    above_avg_count: int
    elite_count: int


class ScheduleResponse(BaseModel):
    team: str
    games_remaining: int
    games_this_week: int
    playoff_games: int
    back_to_backs: int


@router.get("/players", response_model=list[PlayerMetricsResponse],
            description="Get advanced metrics for roster players: schedule-adjusted value, consistency, ceiling/floor.")
def get_player_metrics(
    sort_by: str = Query("schedule_adjusted_z", description="Sort by: schedule_adjusted_z, ros_value, consistency_rating"),
    top: int = Query(35),
    state: LeagueState = Depends(get_state),
):
    metrics = state.advanced_metrics
    if not metrics:
        return []

    items = sorted(metrics.values(), key=lambda m: getattr(m, sort_by, 0), reverse=True)
    return [
        PlayerMetricsResponse(
            name=m.name, z_total=0,
            schedule_adjusted_z=m.schedule_adjusted_z,
            ros_value=m.ros_value,
            consistency_rating=m.consistency_rating,
            games_remaining=m.games_remaining,
            games_this_week=m.games_this_week,
            playoff_games=m.playoff_games,
            schedule_factor=m.schedule_factor,
            weekly_ceiling=m.weekly_ceiling,
            weekly_floor=m.weekly_floor,
            minutes_trend=m.minutes_trend,
        )
        for m in items[:top]
    ]


@router.get("/scarcity", response_model=list[ScarcityResponse],
            description="Category scarcity index: which stats are hardest to find.")
def get_scarcity(state: LeagueState = Depends(get_state)):
    return [
        ScarcityResponse(
            category=s.category,
            scarcity_index=s.scarcity_index,
            above_avg_count=s.above_avg_count,
            elite_count=s.elite_count,
        )
        for s in state.category_scarcity
    ]


@router.get("/schedule", response_model=list[ScheduleResponse],
            description="NBA team schedule: remaining games, this week, playoff games, back-to-backs.")
def get_schedule(state: LeagueState = Depends(get_state)):
    return [
        ScheduleResponse(
            team=s.team,
            games_remaining=s.games_remaining,
            games_this_week=s.games_this_week,
            playoff_games=s.playoff_games,
            back_to_backs=s.back_to_backs,
        )
        for s in sorted(state.schedule_info.values(), key=lambda s: s.games_remaining, reverse=True)
    ]
