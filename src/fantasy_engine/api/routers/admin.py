"""Admin endpoints: refresh data, status."""
from fastapi import APIRouter, Query

from fantasy_engine.api.deps import init_state, init_state_live, init_state_full, get_state
from fantasy_engine.api.schemas import RefreshResponse

router = APIRouter()


@router.post("/refresh", response_model=RefreshResponse,
             description="Reload data from a Fantrax CSV export.")
def refresh_from_csv(
    csv_path: str = Query(..., description="Path to Fantrax CSV file"),
):
    state = init_state(csv_path)
    return _status_response(state)


@router.post("/refresh-live", response_model=RefreshResponse,
             description="Reload data live from Fantrax API + nba_api. No CSV needed.")
def refresh_live(
    league_id: str = Query("z9agcf24meqwg9yw", description="Fantrax league ID"),
    team_id: str = Query("u5koo8ztmeqwg9z7", description="Your Fantrax team ID"),
    season: str = Query("2025-26", description="NBA season"),
):
    state = init_state_live(league_id, team_id, season=season)
    return _status_response(state)


@router.post("/refresh-full", response_model=RefreshResponse,
             description="Full league reload: all 12 teams, free agents, injuries, schedule. "
                         "Enables trade finder, alerts, and real opponent matchups.")
def refresh_full(
    league_id: str = Query("z9agcf24meqwg9yw", description="Fantrax league ID"),
    team_id: str = Query("u5koo8ztmeqwg9z7", description="Your Fantrax team ID"),
    season: str = Query("2025-26", description="NBA season"),
):
    state = init_state_full(league_id, team_id, season=season)
    return _status_response(state)


@router.get("/status", response_model=RefreshResponse,
            description="Check current data status.")
def get_status():
    state = get_state()
    return _status_response(state)


def _status_response(state):
    return RefreshResponse(
        status="ok",
        players_loaded=len(state.z_df),
        active_count=len(state.active_names),
        reserve_count=len(state.reserve_names),
    )
