"""Matchup prediction endpoints: real opponents, category analysis, scouting."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class CategoryMatchupResponse(BaseModel):
    category: str
    my_z: float
    opp_z: float
    diff: float
    win_prob: float
    recommendation: str


class MatchupPredictionResponse(BaseModel):
    period: int
    opponent_name: str
    expected_wins: float
    win_probability: float
    target_cats: list[str]
    concede_cats: list[str]
    swing_cats: list[str]
    my_total_z: float
    opp_total_z: float
    categories: list[CategoryMatchupResponse]


class OpponentScoutResponse(BaseModel):
    team_name: str
    team_id: str
    period: int | None
    team_total_z: float
    strategy: str
    target_cats: list[str]
    concede_cats: list[str]
    swing_cats: list[str]
    my_advantages: int
    my_disadvantages: int
    categories: list[CategoryMatchupResponse]


class MyScheduleResponse(BaseModel):
    period: int
    opponent_name: str
    opponent_id: str
    home_away: str


@router.get("/schedule", response_model=list[MyScheduleResponse],
            description="Get your full matchup schedule for the season.")
def get_my_schedule(state: LeagueState = Depends(get_state)):
    if not state.league_rules:
        raise HTTPException(400, "League rules not loaded. Start with FANTASY_FULL=1")

    from fantasy_engine.ingestion.league_rules import get_my_matchups
    matchups = get_my_matchups(state.league_rules, state.team_id)
    return [MyScheduleResponse(**m) for m in matchups]


@router.get("/predict/{period}", response_model=MatchupPredictionResponse,
            description="Predict your matchup for a specific period against the real opponent.")
def predict_period(
    period: int,
    state: LeagueState = Depends(get_state),
):
    if not state.league_rules or not state.all_teams:
        raise HTTPException(400, "Full league data needed. Start with FANTASY_FULL=1")

    from fantasy_engine.ingestion.league_rules import get_current_matchup
    from fantasy_engine.analytics.matchup_real import predict_real_matchup

    matchup = get_current_matchup(state.league_rules, state.team_id, period)
    if not matchup:
        raise HTTPException(404, f"No matchup found for period {period}")

    opp_id = matchup["opponent_id"]
    opp_data = state.all_teams.get(opp_id)
    if not opp_data or opp_data.get("roster_z") is None:
        raise HTTPException(404, f"Opponent data not found for {matchup['opponent_name']}")

    pred = predict_real_matchup(
        state.z_df, opp_data["roster_z"],
        matchup["opponent_name"], opp_id, period,
    )

    return MatchupPredictionResponse(
        period=pred.period,
        opponent_name=pred.opponent_name,
        expected_wins=pred.expected_wins,
        win_probability=pred.win_probability,
        target_cats=pred.target_cats,
        concede_cats=pred.concede_cats,
        swing_cats=pred.swing_cats,
        my_total_z=pred.my_total_z,
        opp_total_z=pred.opp_total_z,
        categories=[
            CategoryMatchupResponse(
                category=c.category, my_z=c.my_z, opp_z=c.opp_z,
                diff=c.diff, win_prob=c.win_prob, recommendation=c.recommendation,
            ) for c in pred.categories
        ],
    )


@router.get("/current", response_model=MatchupPredictionResponse,
            description="Predict your current period's matchup.")
def predict_current(state: LeagueState = Depends(get_state)):
    if not state.current_period:
        raise HTTPException(400, "Current period not determined. Start with FANTASY_FULL=1")
    return predict_period(state.current_period, state)


@router.get("/scout", response_model=list[OpponentScoutResponse],
            description="Category focus analysis for every opponent. Shows what to target/concede against each team.")
def scout_all(state: LeagueState = Depends(get_state)):
    if not state.all_teams:
        raise HTTPException(400, "Full league data needed. Start with FANTASY_FULL=1")

    from fantasy_engine.analytics.matchup_real import scout_all_opponents

    schedule = state.league_rules.matchup_schedule if state.league_rules else None
    scouting = scout_all_opponents(state.z_df, state.all_teams, state.team_id, schedule)

    return [
        OpponentScoutResponse(
            team_name=s.team_name, team_id=s.team_id, period=s.period,
            team_total_z=s.team_total_z, strategy=s.strategy,
            target_cats=s.target_cats, concede_cats=s.concede_cats,
            swing_cats=s.swing_cats, my_advantages=s.my_advantages,
            my_disadvantages=s.my_disadvantages,
            categories=[
                CategoryMatchupResponse(
                    category=c.category, my_z=c.my_z, opp_z=c.opp_z,
                    diff=c.diff, win_prob=c.win_prob, recommendation=c.recommendation,
                ) for c in s.categories
            ],
        ) for s in scouting
    ]


@router.get("/scout/{team_id}", response_model=OpponentScoutResponse,
            description="Category focus analysis for a specific opponent.")
def scout_team(team_id: str, state: LeagueState = Depends(get_state)):
    if not state.all_teams:
        raise HTTPException(400, "Full league data needed")

    from fantasy_engine.analytics.matchup_real import predict_real_matchup

    opp_data = state.all_teams.get(team_id)
    if not opp_data:
        raise HTTPException(404, f"Team {team_id} not found")

    pred = predict_real_matchup(state.z_df, opp_data["roster_z"], opp_data["name"], team_id)

    adv = len(pred.target_cats)
    disadv = len(pred.concede_cats)
    if adv >= 5:
        strategy = f"Dominant matchup. Target {adv} categories."
    elif adv >= 3:
        strategy = f"Favorable. Focus on swing cats: {', '.join(pred.swing_cats)}"
    elif disadv >= 5:
        strategy = f"Tough matchup. Target: {', '.join(pred.target_cats)}"
    else:
        strategy = f"Even matchup. Swing: {', '.join(pred.swing_cats)}"

    return OpponentScoutResponse(
        team_name=opp_data["name"], team_id=team_id, period=None,
        team_total_z=pred.opp_total_z, strategy=strategy,
        target_cats=pred.target_cats, concede_cats=pred.concede_cats,
        swing_cats=pred.swing_cats, my_advantages=adv, my_disadvantages=disadv,
        categories=[
            CategoryMatchupResponse(
                category=c.category, my_z=c.my_z, opp_z=c.opp_z,
                diff=c.diff, win_prob=c.win_prob, recommendation=c.recommendation,
            ) for c in pred.categories
        ],
    )
