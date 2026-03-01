"""
NBA Fantasy Basketball Analytics Engine - FastAPI Application.

Start with live data (no CSV needed):
    uvicorn fantasy_engine.api.app:app --reload

Or with a CSV:
    FANTASY_CSV_PATH=/path/to/roster.csv uvicorn fantasy_engine.api.app:app --reload

API docs at: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # Load .env file

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fantasy_engine.api.deps import init_state, init_state_live, init_state_full
from fantasy_engine.api.routers import players, teams, trades, matchups, lineup, waiver, dynasty, admin, chat, league, offseason, trade_intelligence, draft_room, metrics, trends, weekly_lineup, insights, strategy

# Default league/team config
DEFAULT_LEAGUE_ID = "z9agcf24meqwg9yw"
DEFAULT_TEAM_ID = "u5koo8ztmeqwg9z7"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup: prefer CSV if set, otherwise pull live from Fantrax + nba_api."""
    import os

    csv_path = os.environ.get("FANTASY_CSV_PATH")
    if csv_path:
        try:
            init_state(csv_path)
            print(f"Loaded data from CSV: {csv_path}")
        except Exception as e:
            print(f"Warning: CSV load failed: {e}")
    else:
        league_id = os.environ.get("FANTASY_LEAGUE_ID", DEFAULT_LEAGUE_ID)
        team_id = os.environ.get("FANTASY_TEAM_ID", DEFAULT_TEAM_ID)
        season = os.environ.get("FANTASY_SEASON", "2025-26")
        full_mode = os.environ.get("FANTASY_FULL", "0") == "1"
        try:
            if full_mode:
                init_state_full(league_id, team_id, season=season)
                print("Loaded FULL league data (all teams, FAs, injuries, schedule)")
            else:
                init_state_live(league_id, team_id, season=season)
                print("Loaded live data (my team only). Set FANTASY_FULL=1 for full league mode.")
        except Exception as e:
            print(f"Warning: Live load failed: {e}")
            print("Use POST /admin/refresh-full to load data manually")
    yield


app = FastAPI(
    title="NBA Fantasy Analytics Engine",
    description=(
        "H2H 9-Cat dynasty salary cap analytics for Fantrax. "
        "Provides z-score rankings, trade evaluation, matchup prediction, "
        "lineup optimization, and dynasty valuations. "
        "Data loaded live from Fantrax API + nba_api — no CSV export needed."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(players.router, prefix="/players", tags=["Players"])
app.include_router(teams.router, prefix="/teams", tags=["Teams"])
app.include_router(trades.router, prefix="/trades", tags=["Trades"])
app.include_router(matchups.router, prefix="/matchups", tags=["Matchups"])
app.include_router(lineup.router, prefix="/lineup", tags=["Lineup"])
app.include_router(waiver.router, prefix="/waiver", tags=["Waiver"])
app.include_router(dynasty.router, prefix="/dynasty", tags=["Dynasty"])
app.include_router(league.router, prefix="/league", tags=["League"])
app.include_router(trade_intelligence.router, prefix="/trade-intel", tags=["Trade Intelligence"])
app.include_router(draft_room.router, prefix="/draft", tags=["Draft Room"])
app.include_router(metrics.router, prefix="/metrics", tags=["Advanced Metrics"])
app.include_router(weekly_lineup.router, prefix="/weekly-lineup", tags=["Weekly Lineup Optimizer"])
app.include_router(insights.router, prefix="/insights", tags=["Insights"])
app.include_router(strategy.router, prefix="/strategy", tags=["Strategy"])
app.include_router(trends.router, prefix="/trends", tags=["Trends & External"])
app.include_router(offseason.router, prefix="/offseason", tags=["Off-Season"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(chat.router, prefix="/chat", tags=["Coach"])


@app.get("/", tags=["Root"])
def root():
    from fantasy_engine.api.deps import _state
    loaded = _state is not None
    return {
        "name": "NBA Fantasy Analytics Engine",
        "version": "0.2.0",
        "data_loaded": loaded,
        "team": _state.team_name if loaded else None,
        "players": len(_state.z_df) if loaded else 0,
        "docs": "/docs",
        "endpoints": {
            "players": "/players/rankings, /players/{name}/zscores, /players/valuations",
            "teams": "/teams/my/profile, /teams/my/roster",
            "trades": "POST /trades/evaluate",
            "matchups": "/matchups/predict",
            "lineup": "/lineup/optimize",
            "waiver": "/waiver/analysis",
            "dynasty": "/dynasty/rankings, /dynasty/punt-strategies",
            "admin": "POST /admin/refresh-live, POST /admin/refresh, /admin/status",
        },
    }
