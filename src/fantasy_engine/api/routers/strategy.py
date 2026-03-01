"""Team strategy endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class PlayerTargetResponse(BaseModel):
    name: str
    team: str
    why: str
    target_method: str
    estimated_cost: str
    fits_cats: list[str]
    age: int
    z_total: float


class PositionNeedResponse(BaseModel):
    position: str
    current_players: list[str]
    current_best_z: float
    need_level: str
    target_archetype: str
    target_cats: list[str]


class StrategyResponse(BaseModel):
    # Category build
    target_categories: list[str]
    punt_categories: list[str]
    expected_weekly_wins: float
    build_rationale: str
    # Position needs
    position_needs: list[PositionNeedResponse]
    # Targets
    extensions: list[PlayerTargetResponse]
    trade_targets: list[PlayerTargetResponse]
    fa_auction_targets: list[PlayerTargetResponse]
    rookie_targets: list[PlayerTargetResponse]
    sell_candidates: list[PlayerTargetResponse]
    # Timeline
    immediate_actions: list[str]
    offseason_plan: list[str]
    two_year_outlook: str


def _to_target(t) -> PlayerTargetResponse:
    return PlayerTargetResponse(
        name=t.name, team=t.team, why=t.why,
        target_method=t.target_method, estimated_cost=t.estimated_cost,
        fits_cats=t.fits_cats, age=t.age, z_total=t.z_total,
    )


@router.get("", response_model=StrategyResponse,
            description="Get comprehensive team strategy: category build, position needs, "
                        "trade targets, FA auction targets, rookie draft plan, sell candidates, and timeline.")
def get_strategy(state: LeagueState = Depends(get_state)):
    if not state.all_teams:
        raise HTTPException(400, "Full league data needed")

    from fantasy_engine.analytics.strategy import generate_strategy

    strategy = generate_strategy(
        my_roster_z=state.z_df,
        all_teams=state.all_teams,
        all_rostered_z=state.all_rostered_z,
        my_team_id=state.team_id,
        category_scarcity=state.category_scarcity,
        injuries=state.injuries,
        salary_cap=state.settings.salary_cap,
    )

    return StrategyResponse(
        target_categories=strategy.category_build.target_5,
        punt_categories=strategy.category_build.punt_4,
        expected_weekly_wins=strategy.category_build.expected_weekly_wins,
        build_rationale=strategy.category_build.rationale,
        position_needs=[
            PositionNeedResponse(
                position=n.position, current_players=n.current_players,
                current_best_z=n.current_best_z, need_level=n.need_level,
                target_archetype=n.target_archetype, target_cats=n.target_cats,
            ) for n in strategy.position_needs
        ],
        extensions=[_to_target(t) for t in strategy.extension_targets],
        trade_targets=[_to_target(t) for t in strategy.trade_targets],
        fa_auction_targets=[_to_target(t) for t in strategy.fa_auction_targets],
        rookie_targets=[_to_target(t) for t in strategy.rookie_targets],
        sell_candidates=[_to_target(t) for t in strategy.sell_candidates],
        immediate_actions=strategy.immediate_actions,
        offseason_plan=strategy.offseason_plan,
        two_year_outlook=strategy.two_year_outlook,
    )
