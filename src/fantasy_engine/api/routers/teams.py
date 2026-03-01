"""Team endpoints: category profile, roster."""
from fastapi import APIRouter, Depends, Query

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import TeamProfileResponse, CategoryInfo, PlayerZScores
from fantasy_engine.analytics.category_analysis import analyze_team
from fantasy_engine.analytics.zscores import ALL_CATS

router = APIRouter()


@router.get("/my/profile", response_model=TeamProfileResponse,
            description="Get my team's category strengths and weaknesses.")
def get_my_profile(
    active_only: bool = Query(False, description="Only analyze active roster"),
    state: LeagueState = Depends(get_state),
):
    if active_only:
        df = state.z_df[state.z_df["status"] == "Act"]
    else:
        df = state.z_df

    profile = analyze_team(df)
    return TeamProfileResponse(
        categories={
            cat: CategoryInfo(
                z_sum=cp.z_sum,
                rank=cp.rank,
                strength=cp.strength,
            )
            for cat, cp in profile.categories.items()
        },
        strongest_cats=profile.strongest_cats,
        weakest_cats=profile.weakest_cats,
        suggested_punts=profile.suggested_punts,
        total_z=round(profile.total_z, 2),
    )


@router.get("/my/roster", response_model=list[PlayerZScores],
            description="Get full roster with z-scores.")
def get_my_roster(
    status: str = Query("", description="Filter by status: Act, Res, or empty for all"),
    state: LeagueState = Depends(get_state),
):
    from fantasy_engine.api.routers.players import _row_to_zscores

    df = state.z_df
    if status:
        df = df[df["status"] == status]

    return [_row_to_zscores(row) for _, row in df.sort_values("z_total", ascending=False).iterrows()]
