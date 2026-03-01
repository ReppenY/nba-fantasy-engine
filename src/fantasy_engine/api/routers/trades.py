"""Trade evaluation endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import TradeRequest, TradeResponse, TradeSideResponse
from fantasy_engine.analytics.trade_eval import evaluate_trade

router = APIRouter()


@router.get("/my-picks", description="Get draft picks I own (for trade give side).")
def get_my_picks(state: LeagueState = Depends(get_state)):
    import requests
    r = requests.get("https://www.fantrax.com/fxea/general/getDraftPicks",
                     params={"leagueId": "z9agcf24meqwg9yw"}, timeout=15)
    picks = r.json().get("futureDraftPicks", [])
    my_picks = [p for p in picks if p.get("currentOwnerTeamId") == state.team_id]
    # Format as readable strings
    team_names = state.team_names or {}
    result = []
    for p in sorted(my_picks, key=lambda x: (x["year"], x["round"])):
        orig = team_names.get(p["originalOwnerTeamId"], p["originalOwnerTeamId"])
        label = f"{p['year']} Round {p['round']} ({orig})"
        result.append(label)
    return result


@router.get("/other-picks", description="Get draft picks owned by other teams (for trade receive side).")
def get_other_picks(state: LeagueState = Depends(get_state)):
    import requests
    r = requests.get("https://www.fantrax.com/fxea/general/getDraftPicks",
                     params={"leagueId": "z9agcf24meqwg9yw"}, timeout=15)
    picks = r.json().get("futureDraftPicks", [])
    other_picks = [p for p in picks if p.get("currentOwnerTeamId") != state.team_id]
    team_names = state.team_names or {}
    result = []
    for p in sorted(other_picks, key=lambda x: (x["year"], x["round"])):
        owner = team_names.get(p["currentOwnerTeamId"], "")
        orig = team_names.get(p["originalOwnerTeamId"], "")
        label = f"{p['year']} Round {p['round']} ({orig}) — owned by {owner}"
        result.append(label)
    return result


@router.get("/my-players", description="Get player names on MY roster (for trade give side).")
def get_my_players(state: LeagueState = Depends(get_state)):
    return sorted(state.z_df["name"].tolist())


@router.get("/other-players", description="Get player names on OTHER teams (for trade receive side).")
def get_other_players(state: LeagueState = Depends(get_state)):
    if state.all_rostered_z is None:
        return []
    my_names = set(state.z_df["name"].str.lower())
    others = state.all_rostered_z[~state.all_rostered_z["name"].str.lower().isin(my_names)]
    return sorted(others["name"].tolist())


@router.post("/evaluate", response_model=TradeResponse,
             description="Evaluate a trade proposal. Provide player names for each side.")
def evaluate(
    req: TradeRequest,
    state: LeagueState = Depends(get_state),
):
    try:
        import pandas as pd

        # Give side: must be on MY roster
        my_names = state.z_df["name"].str.lower().tolist()
        for g in req.give:
            if not any(g.lower().strip() in n for n in my_names):
                raise ValueError(f"'{g}' is not on your roster. You can only trade players you own.")

        # Receive side: must be on ANOTHER team's roster
        if state.all_rostered_z is not None:
            other_players = state.all_rostered_z[
                ~state.all_rostered_z["name"].str.lower().isin(my_names)
            ]
            # Combine my roster + other players for the evaluator
            combined = pd.concat([state.z_df, other_players], ignore_index=True)
            combined = combined.drop_duplicates(subset=["name"], keep="first")
        else:
            combined = state.z_df

        ev = evaluate_trade(
            give_names=req.give,
            receive_names=req.receive,
            roster_z_df=combined,
            salary_cap=state.settings.salary_cap,
            punt_cats=req.punt_cats,
            give_picks=req.give_picks if req.give_picks else None,
            receive_picks=req.receive_picks if req.receive_picks else None,
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
