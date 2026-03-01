"""Dynasty-specific endpoints."""
from fastapi import APIRouter, Depends, Query

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import PlayerValuationResponse, PuntStrategyResponse
from fantasy_engine.analytics.valuation import compute_valuations
from fantasy_engine.analytics.punting import find_optimal_punt

router = APIRouter()


@router.get("/rankings", response_model=list[PlayerValuationResponse],
            description="Dynasty player rankings: age-adjusted, contract-weighted value.")
def get_dynasty_rankings(
    top: int = Query(30),
    state: LeagueState = Depends(get_state),
):
    val_df = compute_valuations(state.z_df)
    val_df = val_df.sort_values("dynasty_value", ascending=False).head(top)

    return [
        PlayerValuationResponse(
            name=row.get("name", ""),
            salary=row.get("salary", 0),
            age=int(row.get("age", 0)),
            years_remaining=int(row.get("years_remaining", 1)),
            z_total=round(row.get("z_total", 0), 2),
            z_per_dollar=round(row.get("z_per_dollar", 0), 2),
            surplus_value=round(row.get("surplus_value", 0), 2),
            dynasty_value=round(row.get("dynasty_value", 0), 2),
            age_factor=round(row.get("age_factor", 1), 2),
        )
        for _, row in val_df.iterrows()
    ]


@router.get("/punt-strategies", response_model=list[PuntStrategyResponse],
            description="Find optimal punt strategies for your roster.")
def get_punt_strategies(
    max_punts: int = Query(2, description="Max categories to punt (1 or 2)"),
    top: int = Query(15),
    state: LeagueState = Depends(get_state),
):
    all_indices = list(range(len(state.raw_df)))
    results = find_optimal_punt(state.raw_df, all_indices, max_punt_cats=max_punts)

    return [
        PuntStrategyResponse(**r)
        for r in results[:top]
    ]
