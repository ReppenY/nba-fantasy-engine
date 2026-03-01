"""Player trends and external rankings endpoints."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class PlayerTrendResponse(BaseModel):
    name: str
    trending: str
    trend_score: float
    games_total: int
    # Season vs recent
    pts_season: float = 0
    pts_last14: float = 0
    reb_season: float = 0
    reb_last14: float = 0
    ast_season: float = 0
    ast_last14: float = 0
    stl_season: float = 0
    stl_last14: float = 0
    blk_season: float = 0
    blk_last14: float = 0
    tpm_season: float = 0
    tpm_last14: float = 0
    # Minutes
    minutes_season: float = 0
    minutes_recent: float = 0
    minutes_trend: float = 0
    # Category trends (% change)
    cat_trends: dict[str, float] = {}


class RankingComparisonResponse(BaseModel):
    name: str
    our_rank: int
    our_z: float
    external_rank: int
    external_z: float
    rank_diff: int
    signal: str


@router.get("/rising", response_model=list[PlayerTrendResponse],
            description="Get players trending up (hot streaks, increasing production).")
def get_rising(
    top: int = Query(10),
    state: LeagueState = Depends(get_state),
):
    if not state.player_trends:
        raise HTTPException(400, "Trends not loaded. Need full league mode with game logs.")
    from fantasy_engine.analytics.trends import get_rising_players
    rising = get_rising_players(state.player_trends, top)
    return [_trend_to_response(t) for t in rising]


@router.get("/falling", response_model=list[PlayerTrendResponse],
            description="Get players trending down (cold streaks, declining production).")
def get_falling(
    top: int = Query(10),
    state: LeagueState = Depends(get_state),
):
    if not state.player_trends:
        raise HTTPException(400, "Trends not loaded.")
    from fantasy_engine.analytics.trends import get_falling_players
    falling = get_falling_players(state.player_trends, top)
    return [_trend_to_response(t) for t in falling]


@router.get("/player/{name}", response_model=PlayerTrendResponse,
            description="Get detailed trend data for a specific player.")
def get_player_trend(name: str, state: LeagueState = Depends(get_state)):
    if not state.player_trends:
        raise HTTPException(400, "Trends not loaded.")
    for pname, trend in state.player_trends.items():
        if name.lower() in pname.lower():
            return _trend_to_response(trend)
    raise HTTPException(404, f"Trend data not found for '{name}'")


@router.get("/minutes-gainers", response_model=list[PlayerTrendResponse],
            description="Get players gaining the most minutes recently.")
def get_minutes_gainers(
    top: int = Query(10),
    state: LeagueState = Depends(get_state),
):
    if not state.player_trends:
        raise HTTPException(400, "Trends not loaded.")
    from fantasy_engine.analytics.trends import get_minutes_gainers
    gainers = get_minutes_gainers(state.player_trends, top)
    return [_trend_to_response(t) for t in gainers]


@router.get("/vs-experts", response_model=list[RankingComparisonResponse],
            description="Compare our rankings vs Hashtag Basketball expert rankings. "
                        "Shows buy-low (we rate higher) and sell-high (experts rate higher) candidates.")
def get_vs_experts(
    signal: str = Query("", description="Filter by signal: buy_low, sell_high, agree"),
    top: int = Query(30),
    state: LeagueState = Depends(get_state),
):
    if not state.external_rankings:
        # Fetch live
        from fantasy_engine.ingestion.external import fetch_hashtag_rankings, compare_rankings
        ext = fetch_hashtag_rankings()
        if not ext:
            raise HTTPException(500, "Could not fetch Hashtag Basketball rankings")
        comparisons = compare_rankings(
            state.all_rostered_z if state.all_rostered_z is not None else state.z_df,
            ext,
        )
    else:
        comparisons = state.external_rankings

    if signal:
        comparisons = [c for c in comparisons if c.signal == signal]

    return [
        RankingComparisonResponse(
            name=c.name, our_rank=c.our_rank, our_z=c.our_z,
            external_rank=c.external_rank, external_z=c.external_z,
            rank_diff=c.rank_diff, signal=c.signal,
        )
        for c in comparisons[:top]
    ]


def _trend_to_response(t) -> PlayerTrendResponse:
    return PlayerTrendResponse(
        name=t.name, trending=t.trending, trend_score=t.trend_score,
        games_total=t.games_total,
        pts_season=t.season.get("pts", 0), pts_last14=t.last_14.get("pts", 0),
        reb_season=t.season.get("reb", 0), reb_last14=t.last_14.get("reb", 0),
        ast_season=t.season.get("ast", 0), ast_last14=t.last_14.get("ast", 0),
        stl_season=t.season.get("stl", 0), stl_last14=t.last_14.get("stl", 0),
        blk_season=t.season.get("blk", 0), blk_last14=t.last_14.get("blk", 0),
        tpm_season=t.season.get("tpm", 0), tpm_last14=t.last_14.get("tpm", 0),
        minutes_season=t.minutes_season, minutes_recent=t.minutes_recent,
        minutes_trend=t.minutes_trend,
        cat_trends=t.cat_trends,
    )
