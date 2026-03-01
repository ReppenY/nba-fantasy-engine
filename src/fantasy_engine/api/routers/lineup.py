"""Lineup optimization endpoints."""
from fastapi import APIRouter, Depends, Query

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import LineupResponse, LineupSlotResponse
from fantasy_engine.analytics.lineup import optimize_lineup

router = APIRouter()


@router.get("/optimize", response_model=LineupResponse,
            description="Get optimal lineup from full roster. Considers position eligibility.")
def get_optimal_lineup(
    punt: str = Query("", description="Comma-separated categories to punt"),
    injured: str = Query("", description="Comma-separated injured player names to exclude"),
    state: LeagueState = Depends(get_state),
):
    punt_cats = [c.strip() for c in punt.split(",") if c.strip()] if punt else []
    injured_list = [n.strip() for n in injured.split(",") if n.strip()] if injured else []

    rec = optimize_lineup(
        state.z_df,
        injured_players=injured_list,
        punt_cats=punt_cats,
    )

    return LineupResponse(
        active=[
            LineupSlotResponse(
                slot=s.slot,
                player_name=s.player_name,
                positions=s.positions,
                games_this_week=s.games_this_week,
                weekly_z=s.weekly_z,
            )
            for s in rec.active
        ],
        bench=rec.bench,
        total_weekly_z=rec.total_weekly_z,
        category_projections=rec.category_projections,
    )
