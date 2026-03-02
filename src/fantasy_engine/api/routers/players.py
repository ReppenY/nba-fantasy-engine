"""Player endpoints: z-scores, rankings, valuations."""
from fastapi import APIRouter, Depends, Query

from fantasy_engine.api.deps import get_state, LeagueState
from fantasy_engine.api.schemas import PlayerZScores, PlayerValuationResponse
from fantasy_engine.analytics.zscores import ALL_CATS, compute_punt_zscores
from fantasy_engine.analytics.valuation import compute_valuations

router = APIRouter()


@router.get("/rankings", response_model=list[PlayerZScores],
            description="Get player rankings. Sort by z_total, schedule_adjusted_z, or ros_value.")
def get_rankings(
    punt: str = Query("", description="Comma-separated categories to punt"),
    sort_by: str = Query("schedule_adjusted_z", description="Sort by: z_total, schedule_adjusted_z, ros_value"),
    top: int = Query(50),
    state: LeagueState = Depends(get_state),
):
    punt_cats = [c.strip() for c in punt.split(",") if c.strip()] if punt else []

    if punt_cats:
        z_df = compute_punt_zscores(state.raw_df, punt_cats)
        for col in state.z_df.columns:
            if col not in z_df.columns:
                z_df[col] = state.z_df[col].values
    else:
        z_df = state.z_df

    sort_col = sort_by if sort_by in z_df.columns else "z_total"
    sorted_df = z_df.sort_values(sort_col, ascending=False).head(top)
    return [_row_to_zscores(row) for _, row in sorted_df.iterrows()]


@router.get("/{name}/zscores", response_model=PlayerZScores,
            description="Get full metrics for a specific player.")
def get_player_zscores(
    name: str,
    state: LeagueState = Depends(get_state),
):
    row = state.z_df[state.z_df["name"].str.lower() == name.lower()]
    if row.empty:
        row = state.z_df[state.z_df["name"].str.lower().str.contains(name.lower())]
    if row.empty:
        from fastapi import HTTPException
        raise HTTPException(404, f"Player '{name}' not found")
    return _row_to_zscores(row.iloc[0])


@router.get("/valuations", response_model=list[PlayerValuationResponse],
            description="Get player valuations with schedule-adjusted values.")
def get_valuations(
    sort_by: str = Query("dynasty_value", description="Sort by: dynasty_value, z_per_dollar, surplus_value, ros_value"),
    top: int = Query(50),
    state: LeagueState = Depends(get_state),
):
    val_df = compute_valuations(state.z_df)
    if sort_by in val_df.columns:
        val_df = val_df.sort_values(sort_by, ascending=False)
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
        for _, row in val_df.head(top).iterrows()
    ]


def _row_to_zscores(row) -> PlayerZScores:
    return PlayerZScores(
        name=row.get("name", ""),
        nba_team=row.get("nba_team"),
        salary=row.get("salary", 0),
        age=int(row.get("age", 0)),
        positions=row.get("positions"),
        games_played=int(row.get("games_played", 0)),
        **{f"z_{c}": round(row.get(f"z_{c}", 0), 3) for c in ALL_CATS},
        z_total=round(row.get("z_total", 0), 3),
        pos_scarcity_bonus=round(row.get("pos_scarcity_bonus", 0), 3),
        scarcest_position=row.get("scarcest_position", ""),
        schedule_adjusted_z=round(row.get("schedule_adjusted_z", 0), 3),
        ros_value=round(row.get("ros_value", 0), 3),
        consistency_rating=round(row.get("consistency_rating", 0), 3),
        games_remaining=int(row.get("games_remaining", 0)),
        games_this_week=int(row.get("games_this_week", 0)),
        playoff_games=int(row.get("playoff_games", 0)),
    )
