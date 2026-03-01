"""Off-season planning endpoints."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fantasy_engine.api.deps import get_state, LeagueState

router = APIRouter()


class ContractResponse(BaseModel):
    name: str
    salary: float
    contract: str
    years_remaining: int
    is_expiring: bool
    z_total: float
    z_per_dollar: float
    age: int
    recommendation: str
    reason: str


class CapProjectionResponse(BaseModel):
    current_salary_total: float
    salary_cap: float
    cap_room: float
    expiring_salary: float
    committed_salary: float
    projected_cap_room: float
    num_expiring: int
    num_kept: int


class OffseasonResponse(BaseModel):
    cap_projection: CapProjectionResponse
    must_keep: list[ContractResponse]
    keep: list[ContractResponse]
    tradeable: list[ContractResponse]
    drop_candidates: list[ContractResponse]
    expiring: list[ContractResponse]


class TransactionSummaryResponse(BaseModel):
    total_transactions: int
    total_claims: int
    total_drops: int
    most_claimed: dict[str, int]
    most_dropped: dict[str, int]
    most_active_teams: dict[str, int]
    recently_hot: dict[str, int]


@router.get("/contracts", response_model=OffseasonResponse,
            description="Off-season contract analysis: keepers, drops, cap projection.")
def get_contract_analysis(state: LeagueState = Depends(get_state)):
    from fantasy_engine.analytics.offseason import analyze_contracts

    analysis = analyze_contracts(state.z_df, state.settings.salary_cap)
    cap = analysis["cap_projection"]

    def _to_response(c):
        return ContractResponse(
            name=c.name, salary=c.salary, contract=c.contract,
            years_remaining=c.years_remaining, is_expiring=c.is_expiring,
            z_total=c.z_total, z_per_dollar=c.z_per_dollar,
            age=c.age, recommendation=c.recommendation, reason=c.reason,
        )

    return OffseasonResponse(
        cap_projection=CapProjectionResponse(
            current_salary_total=cap.current_salary_total,
            salary_cap=cap.salary_cap, cap_room=cap.cap_room,
            expiring_salary=cap.expiring_salary,
            committed_salary=cap.committed_salary,
            projected_cap_room=cap.projected_cap_room,
            num_expiring=cap.num_expiring, num_kept=cap.num_kept,
        ),
        must_keep=[_to_response(c) for c in analysis["keepers"] if c.recommendation == "must_keep"],
        keep=[_to_response(c) for c in analysis["keepers"] if c.recommendation == "keep"],
        tradeable=[_to_response(c) for c in analysis["tradeable"]],
        drop_candidates=[_to_response(c) for c in analysis["drop_candidates"]],
        expiring=[_to_response(c) for c in analysis["expiring"]],
    )


@router.post("/transactions", response_model=TransactionSummaryResponse,
             description="Analyze transaction history from a Fantrax CSV export.")
def analyze_transactions(
    csv_path: str = Query(..., description="Path to transaction history CSV"),
):
    from fantasy_engine.ingestion.transactions import parse_transactions_csv, get_league_transaction_summary

    df = parse_transactions_csv(csv_path)
    summary = get_league_transaction_summary(df)

    return TransactionSummaryResponse(
        total_transactions=summary["total_transactions"],
        total_claims=summary["total_claims"],
        total_drops=summary["total_drops"],
        most_claimed=summary["most_claimed_players"],
        most_dropped=summary["most_dropped_players"],
        most_active_teams=summary["most_active_teams"],
        recently_hot=summary["recently_hot_pickups"],
    )


# --- Auction Values ---

class AuctionValueResponse(BaseModel):
    name: str
    nba_team: str
    z_total: float
    z_above_replacement: float
    auction_value: float
    current_salary: float
    value_diff: float
    tier: str
    age: int


@router.get("/auction-values", response_model=list[AuctionValueResponse],
            description="Compute fair auction/draft values for all players based on z-scores and replacement level.")
def get_auction_values(
    top: int = Query(50),
    state: LeagueState = Depends(get_state),
):
    from fantasy_engine.analytics.draft import compute_auction_values

    # Need all NBA stats for league-wide calculation
    if state.all_rostered_z is not None:
        values = compute_auction_values(state.all_rostered_z, state.settings.salary_cap)
    else:
        values = compute_auction_values(state.raw_df, state.settings.salary_cap)

    return [
        AuctionValueResponse(
            name=v.name, nba_team=v.nba_team, z_total=v.z_total,
            z_above_replacement=v.z_above_replacement,
            auction_value=v.auction_value, current_salary=v.current_salary,
            value_diff=v.value_diff, tier=v.tier, age=v.age,
        )
        for v in values[:top]
    ]


# --- Keeper Optimizer ---

class KeeperDecisionResponse(BaseModel):
    name: str
    salary: float
    auction_value: float
    surplus: float
    z_total: float
    age: int
    contract: str
    is_injured: bool
    injury_return: str
    decision: str
    reason: str
    priority: int


class KeeperPlanResponse(BaseModel):
    keeps: list[KeeperDecisionResponse]
    lets_walk: list[KeeperDecisionResponse]
    total_kept_salary: float
    cap_room_after: float
    roster_spots_opened: int


@router.get("/keeper-plan", response_model=KeeperPlanResponse,
            description="Optimized keeper decisions: which expiring players to re-sign vs let walk.")
def get_keeper_plan(state: LeagueState = Depends(get_state)):
    from fantasy_engine.analytics.draft import compute_auction_values
    from fantasy_engine.analytics.keeper import optimize_keepers

    # Compute auction values for reference
    if state.all_rostered_z is not None:
        values = compute_auction_values(state.all_rostered_z, state.settings.salary_cap)
    else:
        values = compute_auction_values(state.raw_df, state.settings.salary_cap)

    av_map = {v.name: v.auction_value for v in values}

    plan = optimize_keepers(
        state.z_df, av_map,
        injuries=state.injuries,
        salary_cap=state.settings.salary_cap,
    )

    def _to_resp(d):
        return KeeperDecisionResponse(
            name=d.name, salary=d.salary, auction_value=d.auction_value,
            surplus=d.surplus, z_total=d.z_total, age=d.age,
            contract=d.contract, is_injured=d.is_injured,
            injury_return=d.injury_return, decision=d.decision,
            reason=d.reason, priority=d.priority,
        )

    return KeeperPlanResponse(
        keeps=[_to_resp(d) for d in plan.keeps],
        lets_walk=[_to_resp(d) for d in plan.lets_walk],
        total_kept_salary=plan.total_kept_salary,
        cap_room_after=plan.cap_room_after,
        roster_spots_opened=plan.roster_spots_opened,
    )


# --- Trade Simulator ---

class TradeSimRequest(BaseModel):
    player_name: str
    mode: str = "acquire"  # "acquire" or "sell"
    punt_cats: list[str] = []


class TradePackageResponse(BaseModel):
    opponent_team: str
    i_give: list[str]
    i_receive: list[str]
    my_need_score: float
    their_need_score: float
    salary_diff: float
    feasibility: str
    my_cat_changes: dict[str, float]


# --- Pick Valuation ---

class PickAssetResponse(BaseModel):
    year: int
    round: int
    original_team: str
    current_owner: str
    estimated_pick_number: int
    estimated_overall: int
    expected_z: float
    is_lottery: bool
    confidence: str


class PickPortfolioResponse(BaseModel):
    team_name: str
    total_expected_z: float
    num_first_rounders: int
    num_lottery_picks: int
    picks_owned: list[PickAssetResponse]
    picks_traded_away: list[PickAssetResponse]


@router.get("/pick-portfolio", response_model=PickPortfolioResponse,
            description="Get your draft pick portfolio: all picks owned, their estimated value, and picks traded away.")
def get_pick_portfolio(state: LeagueState = Depends(get_state)):
    import requests
    from fantasy_engine.analytics.pick_valuation import build_pick_portfolio

    # Fetch picks from Fantrax
    r = requests.get("https://www.fantrax.com/fxea/general/getDraftPicks",
                     params={"leagueId": "z9agcf24meqwg9yw"}, timeout=15)
    picks_data = r.json().get("futureDraftPicks", [])

    # Build standings for pick position estimation
    standings = []
    if state.all_teams:
        from fantasy_engine.analytics.category_analysis import analyze_team
        for tid, tdata in state.all_teams.items():
            rz = tdata.get("roster_z")
            if rz is not None and not rz.empty and "z_total" in rz.columns:
                total_z = rz["z_total"].sum()
            else:
                total_z = 0
            standings.append({"name": tdata["name"], "total_z": total_z})
        standings.sort(key=lambda t: t["total_z"], reverse=True)

    portfolio = build_pick_portfolio(
        picks_data, state.team_id, state.team_names, standings,
    )

    def _pick_resp(p):
        return PickAssetResponse(
            year=p.year, round=p.round, original_team=p.original_team,
            current_owner=p.current_owner, estimated_pick_number=p.estimated_pick_number,
            estimated_overall=p.estimated_overall, expected_z=p.expected_z,
            is_lottery=p.is_lottery, confidence=p.confidence,
        )

    return PickPortfolioResponse(
        team_name=portfolio.team_name,
        total_expected_z=portfolio.total_expected_z,
        num_first_rounders=portfolio.num_first_rounders,
        num_lottery_picks=portfolio.num_lottery_picks,
        picks_owned=[_pick_resp(p) for p in portfolio.picks_owned],
        picks_traded_away=[_pick_resp(p) for p in portfolio.picks_traded_away],
    )


@router.get("/all-pick-portfolios",
            description="Get draft pick portfolios for all 12 teams.")
def get_all_portfolios(state: LeagueState = Depends(get_state)):
    import requests
    from fantasy_engine.analytics.pick_valuation import build_all_portfolios

    r = requests.get("https://www.fantrax.com/fxea/general/getDraftPicks",
                     params={"leagueId": "z9agcf24meqwg9yw"}, timeout=15)
    picks_data = r.json().get("futureDraftPicks", [])

    standings = []
    if state.all_teams:
        for tid, tdata in state.all_teams.items():
            rz = tdata.get("roster_z")
            total_z = rz["z_total"].sum() if rz is not None and "z_total" in rz.columns else 0
            standings.append({"name": tdata["name"], "total_z": total_z})
        standings.sort(key=lambda t: t["total_z"], reverse=True)

    portfolios = build_all_portfolios(picks_data, state.team_names, standings)

    result = []
    for tid, port in sorted(portfolios.items(), key=lambda x: x[1].total_expected_z, reverse=True):
        result.append({
            "team": port.team_name,
            "total_expected_z": port.total_expected_z,
            "picks_owned": len(port.picks_owned),
            "first_rounders": port.num_first_rounders,
            "lottery_picks": port.num_lottery_picks,
            "picks_traded_away": len(port.picks_traded_away),
        })
    return result


@router.post("/trade-simulator", response_model=list[TradePackageResponse],
             description="Simulate trades: find packages to acquire or sell a specific player across all 12 teams.")
def trade_simulator(
    req: TradeSimRequest,
    state: LeagueState = Depends(get_state),
):
    if not state.all_teams:
        from fastapi import HTTPException
        raise HTTPException(400, "Full league data needed. Start with FANTASY_FULL=1")

    from fantasy_engine.analytics.trade_simulator import simulate_acquire, simulate_sell

    if req.mode == "acquire":
        packages = simulate_acquire(
            req.player_name, state.z_df, state.all_teams,
            state.team_id, req.punt_cats,
        )
    else:
        packages = simulate_sell(
            req.player_name, state.z_df, state.all_teams,
            state.team_id, req.punt_cats,
        )

    return [
        TradePackageResponse(
            opponent_team=p.opponent_team,
            i_give=p.i_give, i_receive=p.i_receive,
            my_need_score=p.my_need_score,
            their_need_score=p.their_need_score,
            salary_diff=p.salary_diff,
            feasibility=p.feasibility,
            my_cat_changes=p.my_cat_changes,
        )
        for p in packages[:15]
    ]
