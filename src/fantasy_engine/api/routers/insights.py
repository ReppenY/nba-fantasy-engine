"""Insights endpoints: monopolies, rotation alerts, splits."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class MonopolyResponse(BaseModel):
    category: str
    total_elite: int
    you_own: int
    you_own_names: list[str]
    league_control_pct: float
    elite_players: list[dict]


class PlayerMonopolyResponse(BaseModel):
    name: str
    monopoly_cats: list[str]
    monopoly_score: float
    replacement_difficulty: str


class RotationAlertResponse(BaseModel):
    player_name: str
    alert_type: str
    severity: str
    minutes_season: float
    minutes_recent: float
    minutes_change: float
    minutes_change_pct: float
    description: str
    actionable: str


class SplitResponse(BaseModel):
    name: str
    home_stats: dict[str, float]
    away_stats: dict[str, float]
    home_advantage_cats: list[str]
    away_advantage_cats: list[str]
    b2b_dropoff: dict[str, float]


@router.get("/monopolies", response_model=list[MonopolyResponse],
            description="Detect category monopolies: which stats have few elite providers and how many you control.")
def get_monopolies(state: LeagueState = Depends(get_state)):
    if state.all_rostered_z is None:
        raise HTTPException(400, "Full league data needed")

    from fantasy_engine.analytics.monopoly import detect_monopolies
    monopolies = detect_monopolies(state.all_rostered_z, state.z_df)

    return [
        MonopolyResponse(
            category=m.category,
            total_elite=m.total_elite,
            you_own=m.you_own,
            you_own_names=m.you_own_names,
            league_control_pct=m.league_control_pct,
            elite_players=m.elite_players[:10],
        )
        for m in monopolies
    ]


@router.get("/player-monopoly", response_model=list[PlayerMonopolyResponse],
            description="How irreplaceable are your players? Shows which ones provide rare category production.")
def get_player_monopoly(state: LeagueState = Depends(get_state)):
    if state.all_rostered_z is None:
        raise HTTPException(400, "Full league data needed")

    from fantasy_engine.analytics.monopoly import detect_player_monopoly_value
    players = detect_player_monopoly_value(state.all_rostered_z, state.z_df)

    return [
        PlayerMonopolyResponse(
            name=p.name, monopoly_cats=p.monopoly_cats,
            monopoly_score=p.monopoly_score,
            replacement_difficulty=p.replacement_difficulty,
        )
        for p in players if p.monopoly_score > 0
    ]


@router.get("/rotation-alerts", response_model=list[RotationAlertResponse],
            description="Detect rotation changes: who's gaining or losing minutes.")
def get_rotation_alerts(state: LeagueState = Depends(get_state)):
    if not state.player_trends:
        raise HTTPException(400, "Player trends not loaded")

    from fantasy_engine.analytics.rotation_alerts import detect_rotation_changes
    alerts = detect_rotation_changes(state.player_trends, state.team_contexts or None)

    return [
        RotationAlertResponse(
            player_name=a.player_name, alert_type=a.alert_type,
            severity=a.severity, minutes_season=a.minutes_season,
            minutes_recent=a.minutes_recent, minutes_change=a.minutes_change,
            minutes_change_pct=a.minutes_change_pct,
            description=a.description, actionable=a.actionable,
        )
        for a in alerts
    ]


@router.get("/splits/{name}", response_model=SplitResponse,
            description="Get home/away and back-to-back splits for a player.")
def get_player_splits(name: str, state: LeagueState = Depends(get_state)):
    # Try to fetch game log from nba_api for this player
    from fantasy_engine.analytics.splits import compute_splits
    import time

    # Find nba_api_id
    nba_id = None
    player_name = None
    for _, row in state.z_df.iterrows():
        if name.lower() in str(row.get("name", "")).lower():
            pid = row.get("nba_api_id", 0)
            try:
                nba_id = int(float(pid)) if pid and not (isinstance(pid, float) and pid != pid) else None
            except (ValueError, TypeError):
                nba_id = None
            player_name = row.get("name", name)
            break

    if not nba_id:
        raise HTTPException(404, f"No NBA ID found for '{name}'")

    try:
        from nba_api.stats.endpoints import PlayerGameLog
        gl = PlayerGameLog(player_id=nba_id, season="2025-26")
        time.sleep(0.6)
        game_log = gl.get_data_frames()[0]
    except Exception as e:
        raise HTTPException(500, f"Could not fetch game log: {e}")

    if game_log.empty:
        raise HTTPException(404, f"No game log data for '{name}'")

    splits = compute_splits(player_name or name, game_log)

    return SplitResponse(
        name=splits.name,
        home_stats=splits.home_stats,
        away_stats=splits.away_stats,
        home_advantage_cats=splits.home_advantage_cats,
        away_advantage_cats=splits.away_advantage_cats,
        b2b_dropoff=splits.b2b_dropoff,
    )
