"""Waiver wire / add-drop endpoints."""
from fastapi import APIRouter, Depends, Query

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import (
    WaiverResponse, AddCandidateResponse,
    DropCandidateResponse, SwapResponse,
)
from fantasy_engine.analytics.add_drop import best_available, drop_candidates, best_swaps

router = APIRouter()


@router.get("/analysis", response_model=WaiverResponse,
            description="Full waiver analysis: best FAs, drop candidates, and optimal swaps. "
                        "Uses reserve players as the FA pool (in production, would use actual FAs).")
def get_waiver_analysis(
    punt: str = Query("", description="Comma-separated categories to punt"),
    top: int = Query(10, description="Number of results per section"),
    state: LeagueState = Depends(get_state),
):
    punt_cats = [c.strip() for c in punt.split(",") if c.strip()] if punt else []

    active_z = state.z_df[state.z_df["status"] == "Act"]
    reserve_z = state.z_df[state.z_df["status"] == "Res"]

    adds = best_available(active_z, reserve_z, punt_cats, top_n=top)
    drops = drop_candidates(active_z, punt_cats, top_n=top)
    swaps_list = best_swaps(active_z, reserve_z, punt_cats, top_n=top)

    return WaiverResponse(
        best_available=[
            AddCandidateResponse(
                name=a.name, z_total=a.z_total,
                need_weighted_z=a.need_weighted_z,
                salary=a.salary, helps_cats=a.helps_cats,
            ) for a in adds
        ],
        drop_candidates=[
            DropCandidateResponse(
                name=d.name, z_total=d.z_total,
                z_per_dollar=d.z_per_dollar, salary=d.salary,
                droppability_score=d.droppability_score, reason=d.reason,
            ) for d in drops
        ],
        best_swaps=[
            SwapResponse(
                drop=s.drop, add=s.add,
                net_z_change=s.net_z_change,
                net_need_z_change=s.net_need_z_change,
                salary_change=s.salary_change,
            ) for s in swaps_list
        ],
    )
