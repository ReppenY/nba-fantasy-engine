"""Trade evaluation endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import TradeRequest, TradeResponse, TradeSideResponse
from fantasy_engine.analytics.trade_eval import evaluate_trade

router = APIRouter()


@router.post("/evaluate", response_model=TradeResponse,
             description="Evaluate a trade proposal. Provide player names for each side.")
def evaluate(
    req: TradeRequest,
    state: LeagueState = Depends(get_state),
):
    try:
        import pandas as pd
        # Combine my roster with all rostered players so we can find
        # players from other teams (the "receive" side)
        if state.all_rostered_z is not None:
            combined = pd.concat([state.z_df, state.all_rostered_z], ignore_index=True)
            combined = combined.drop_duplicates(subset=["name"], keep="first")
        else:
            combined = state.z_df

        ev = evaluate_trade(
            give_names=req.give,
            receive_names=req.receive,
            roster_z_df=combined,
            salary_cap=state.settings.salary_cap,
            punt_cats=req.punt_cats,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return TradeResponse(
        verdict=ev.verdict,
        combined_score=ev.combined_score,
        z_diff=ev.z_diff,
        weighted_score=ev.weighted_score,
        salary_impact=ev.salary_impact,
        cap_room_after=ev.cap_room_after,
        dynasty_diff=ev.dynasty_diff,
        cat_impact=ev.cat_impact,
        improves=ev.improves_cats,
        hurts=ev.hurts_cats,
        explanation=ev.explanation,
        give=TradeSideResponse(
            players=ev.give.players,
            total_salary=ev.give.total_salary,
            total_z=ev.give.total_z,
            z_per_cat=ev.give.z_per_cat,
            dynasty_value=ev.give.dynasty_value,
        ),
        receive=TradeSideResponse(
            players=ev.receive.players,
            total_salary=ev.receive.total_salary,
            total_z=ev.receive.total_z,
            z_per_cat=ev.receive.z_per_cat,
            dynasty_value=ev.receive.dynasty_value,
        ),
    )
