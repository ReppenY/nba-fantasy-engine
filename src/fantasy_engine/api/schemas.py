"""Pydantic response models for the API."""
from pydantic import BaseModel


class PlayerZScores(BaseModel):
    name: str
    nba_team: str | None = None
    salary: float = 0
    age: int = 0
    positions: str | None = None
    games_played: int = 0
    z_pts: float = 0
    z_reb: float = 0
    z_ast: float = 0
    z_stl: float = 0
    z_blk: float = 0
    z_tpm: float = 0
    z_fg_pct: float = 0
    z_ft_pct: float = 0
    z_tov: float = 0
    z_total: float = 0
    # Advanced metrics
    schedule_adjusted_z: float = 0
    ros_value: float = 0
    consistency_rating: float = 0
    games_remaining: int = 0
    games_this_week: int = 0
    playoff_games: int = 0


class PlayerValuationResponse(BaseModel):
    name: str
    salary: float = 0
    age: int = 0
    years_remaining: int = 1
    z_total: float = 0
    z_per_dollar: float = 0
    surplus_value: float = 0
    dynasty_value: float = 0
    age_factor: float = 1.0


class CategoryInfo(BaseModel):
    z_sum: float
    rank: int
    strength: str


class TeamProfileResponse(BaseModel):
    categories: dict[str, CategoryInfo]
    strongest_cats: list[str]
    weakest_cats: list[str]
    suggested_punts: list[str]
    total_z: float


class TradeRequest(BaseModel):
    give: list[str]        # Player names to give away
    receive: list[str]     # Player names to receive
    punt_cats: list[str] = []


class TradeSideResponse(BaseModel):
    players: list[str]
    total_salary: float
    total_z: float
    z_per_cat: dict[str, float]
    dynasty_value: float


class TradeResponse(BaseModel):
    verdict: str
    combined_score: float
    z_diff: float
    weighted_score: float
    salary_impact: float
    cap_room_after: float
    dynasty_diff: float
    cat_impact: dict[str, float]
    improves: list[str]
    hurts: list[str]
    explanation: str
    give: TradeSideResponse
    receive: TradeSideResponse


class MatchupCategoryProb(BaseModel):
    category: str
    my_projection: float
    opp_projection: float
    win_probability: float
    outlook: str


class MatchupResponse(BaseModel):
    categories: list[MatchupCategoryProb]
    expected_cats_won: float
    win_probability: float
    loss_probability: float
    swing_categories: list[str]
    lock_categories: list[str]


class LineupSlotResponse(BaseModel):
    slot: str
    player_name: str
    positions: str
    games_this_week: int
    weekly_z: float


class LineupResponse(BaseModel):
    active: list[LineupSlotResponse]
    bench: list[str]
    total_weekly_z: float
    category_projections: dict[str, float]


class AddCandidateResponse(BaseModel):
    name: str
    z_total: float
    need_weighted_z: float
    salary: float
    helps_cats: list[str]


class DropCandidateResponse(BaseModel):
    name: str
    z_total: float
    z_per_dollar: float
    salary: float
    droppability_score: float
    reason: str


class SwapResponse(BaseModel):
    drop: str
    add: str
    net_z_change: float
    net_need_z_change: float
    salary_change: float


class WaiverResponse(BaseModel):
    best_available: list[AddCandidateResponse]
    drop_candidates: list[DropCandidateResponse]
    best_swaps: list[SwapResponse]


class PuntStrategyResponse(BaseModel):
    punted: list[str]
    active_cats: list[str]
    n_competing: int
    team_z_total: float
    avg_z_per_cat: float
    expected_cats_won: float


class RefreshResponse(BaseModel):
    status: str
    players_loaded: int
    active_count: int
    reserve_count: int
