"""
Advanced fantasy basketball metrics beyond z-scores.

- Schedule-Adjusted Value: z-score weighted by games remaining/this week
- Consistency Rating: game-to-game reliability (coefficient of variation)
- Category Scarcity Index: how rare above-average production is per category
- Minutes Trend: recent vs season average minutes
- Weekly Ceiling/Floor: best/worst weekly outcome estimates
- Rest-of-Season Value: forward-looking schedule-weighted projection
"""
import time
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import date, timedelta

from fantasy_engine.analytics.zscores import ALL_CATS, COUNTING_CATS, NEGATIVE_CATS


# ── Data Models ──

@dataclass
class PlayerAdvancedMetrics:
    name: str
    # Schedule
    games_remaining: int = 0
    games_this_week: int = 0
    playoff_games: int = 0          # Games during fantasy playoff weeks
    schedule_factor: float = 1.0     # games_remaining / league_avg_remaining
    # Consistency
    consistency_rating: float = 0.5  # 0 = very volatile, 1 = very consistent
    category_consistency: dict[str, float] = field(default_factory=dict)  # per-cat CV
    weekly_ceiling: float = 0.0      # Estimated best weekly z-total
    weekly_floor: float = 0.0        # Estimated worst weekly z-total
    # Minutes
    minutes_season: float = 0.0
    minutes_recent: float = 0.0      # Last 10 games
    minutes_trend: float = 0.0       # recent - season (positive = gaining minutes)
    # Combined
    schedule_adjusted_z: float = 0.0 # z_total * schedule_factor * consistency
    ros_value: float = 0.0           # Rest-of-season projected value


@dataclass
class CategoryScarcity:
    category: str
    scarcity_index: float    # Higher = rarer/more valuable
    above_avg_count: int     # How many players are above average
    elite_count: int         # z > 1.5
    league_avg: float


@dataclass
class ScheduleInfo:
    team: str
    games_remaining: int
    games_this_week: int
    games_by_week: dict[int, int] = field(default_factory=dict)  # period -> games
    playoff_games: int = 0
    back_to_backs: int = 0


# ── Schedule System ──

def compute_schedule_info(
    season: str = "2025-26",
    season_end: str = "2026-03-22",
    playoff_start_period: int = 15,
) -> dict[str, ScheduleInfo]:
    """
    Compute remaining schedule for every NBA team.

    Uses nba_api LeagueGameLog to get the full season schedule,
    then counts remaining games, games per week, playoff games.
    """
    try:
        from nba_api.stats.endpoints import LeagueGameLog
        log = LeagueGameLog(season=season, season_type_all_star="Regular Season")
        time.sleep(0.6)
        df = log.get_data_frames()[0]
    except Exception:
        return _default_schedule_info()

    if df.empty:
        return _default_schedule_info()

    df["GAME_DATE_PARSED"] = pd.to_datetime(df["GAME_DATE"]).dt.date
    today = date.today()

    # All games from today onward
    future = df[df["GAME_DATE_PARSED"] >= today]
    season_end_date = date.fromisoformat(season_end)

    # Also get past games for back-to-back analysis
    all_games = df.copy()

    schedule = {}
    for team, group in future.groupby("TEAM_ABBREVIATION"):
        games_remaining = len(group)

        # Games this week (Mon-Sun)
        week_start = today
        week_end = today + timedelta(days=(6 - today.weekday()) % 7 + 1)
        this_week = group[(group["GAME_DATE_PARSED"] >= week_start) & (group["GAME_DATE_PARSED"] <= week_end)]

        # Games by period (approximate: 7 days per period)
        games_by_week = {}
        for _, row in group.iterrows():
            gd = row["GAME_DATE_PARSED"]
            days_from_start = (gd - date(2025, 10, 21)).days
            period = max(1, days_from_start // 7 + 1)
            games_by_week[period] = games_by_week.get(period, 0) + 1

        # Playoff games (periods 15-17)
        playoff_games = sum(games_by_week.get(p, 0) for p in range(playoff_start_period, playoff_start_period + 3))

        # Back-to-backs in remaining schedule
        dates = sorted(group["GAME_DATE_PARSED"].unique())
        b2b = sum(1 for i in range(1, len(dates)) if (dates[i] - dates[i-1]).days == 1)

        schedule[str(team)] = ScheduleInfo(
            team=str(team),
            games_remaining=games_remaining,
            games_this_week=len(this_week),
            games_by_week=games_by_week,
            playoff_games=playoff_games,
            back_to_backs=b2b,
        )

    return schedule


def _default_schedule_info() -> dict[str, ScheduleInfo]:
    """Fallback when API fails."""
    teams = [
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN",
        "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
        "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX",
        "POR", "SAC", "SA", "TOR", "UTA", "WAS",
    ]
    return {t: ScheduleInfo(team=t, games_remaining=20, games_this_week=4, playoff_games=12) for t in teams}


# ── Consistency Ratings ──

def compute_consistency(
    player_stats_df: pd.DataFrame,
    game_logs: dict[str, pd.DataFrame] | None = None,
) -> dict[str, dict]:
    """
    Compute consistency ratings for all players.

    If game_logs are provided, uses actual game-by-game variance.
    Otherwise, estimates from season stats using heuristics.

    Returns dict of player_name -> {
        consistency_rating, category_consistency, ceiling, floor, minutes_trend
    }
    """
    results = {}

    for _, row in player_stats_df.iterrows():
        name = row.get("name", "")
        gp = int(row.get("games_played", 0))
        if gp < 5:
            results[name] = _default_consistency(row)
            continue

        if game_logs and name in game_logs:
            # Real game-by-game variance
            gl = game_logs[name]
            results[name] = _compute_from_game_logs(row, gl)
        else:
            # Estimate from season averages
            results[name] = _estimate_consistency(row)

    return results


def _compute_from_game_logs(season_row, game_log_df: pd.DataFrame) -> dict:
    """Compute consistency from actual game logs."""
    cat_cv = {}
    cat_stds = {}

    for cat in COUNTING_CATS + NEGATIVE_CATS:
        col = cat.upper() if cat != "tpm" else "FG3M"
        col_map = {"pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL",
                    "blk": "BLK", "tpm": "FG3M", "tov": "TOV"}
        c = col_map.get(cat, cat)

        if c in game_log_df.columns:
            vals = game_log_df[c].dropna()
            mean = vals.mean()
            std = vals.std()
            cv = std / mean if mean > 0 else 1.0
            cat_cv[cat] = round(min(cv, 2.0), 3)
            cat_stds[cat] = std
        else:
            cat_cv[cat] = 0.5

    # Overall consistency = inverse of average CV (lower CV = more consistent)
    avg_cv = np.mean(list(cat_cv.values())) if cat_cv else 0.5
    consistency = round(max(0.0, min(1.0, 1.0 - avg_cv)), 3)

    # Ceiling/floor: z-total ± 1.5 * combined std
    z_total = season_row.get("z_total", 0)
    combined_std = np.sqrt(sum(s**2 for s in cat_stds.values())) if cat_stds else 2.0
    ceiling = round(z_total + 1.5 * combined_std * 0.3, 2)  # Scale down for weekly
    floor = round(z_total - 1.5 * combined_std * 0.3, 2)

    # Minutes trend
    minutes_col = "MIN" if "MIN" in game_log_df.columns else None
    if minutes_col and len(game_log_df) >= 10:
        recent = game_log_df[minutes_col].head(10).mean()  # Head = most recent
        season = game_log_df[minutes_col].mean()
        minutes_trend = round(recent - season, 1)
        minutes_recent = round(recent, 1)
    else:
        minutes_trend = 0.0
        minutes_recent = season_row.get("minutes", 0)

    return {
        "consistency_rating": consistency,
        "category_consistency": cat_cv,
        "weekly_ceiling": ceiling,
        "weekly_floor": floor,
        "minutes_season": round(season_row.get("minutes", 0), 1),
        "minutes_recent": minutes_recent,
        "minutes_trend": minutes_trend,
    }


def _estimate_consistency(row) -> dict:
    """Estimate consistency when game logs aren't available."""
    # Heuristic: higher-usage, higher-minute players tend to be more consistent
    minutes = row.get("minutes", 0)
    pts = row.get("pts", 0)
    gp = int(row.get("games_played", 0))

    # Players with more minutes/games tend to be more consistent
    min_factor = min(1.0, minutes / 35) if minutes > 0 else 0.3
    gp_factor = min(1.0, gp / 50)
    consistency = round(0.3 + 0.4 * min_factor + 0.3 * gp_factor, 3)

    z_total = row.get("z_total", 0)
    # Estimate ceiling/floor based on consistency
    spread = (1.0 - consistency) * 5
    ceiling = round(z_total + spread, 2)
    floor = round(z_total - spread, 2)

    return {
        "consistency_rating": consistency,
        "category_consistency": {},
        "weekly_ceiling": ceiling,
        "weekly_floor": floor,
        "minutes_season": round(minutes, 1),
        "minutes_recent": round(minutes, 1),
        "minutes_trend": 0.0,
    }


def _default_consistency(row) -> dict:
    return {
        "consistency_rating": 0.3,
        "category_consistency": {},
        "weekly_ceiling": row.get("z_total", 0) + 3,
        "weekly_floor": row.get("z_total", 0) - 3,
        "minutes_season": 0, "minutes_recent": 0, "minutes_trend": 0,
    }


# ── Category Scarcity Index ──

def compute_scarcity(all_player_z: pd.DataFrame) -> list[CategoryScarcity]:
    """
    Compute scarcity index for each category.

    Scarcity = how hard it is to find above-average production.
    Categories where fewer players contribute positively are more scarce
    and thus more valuable.
    """
    qualified = all_player_z[all_player_z.get("games_played", pd.Series(dtype=float)) >= 10]
    if qualified.empty:
        qualified = all_player_z

    scarcity = []
    scarcity_values = {}

    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col not in qualified.columns:
            continue

        values = qualified[z_col]
        above_avg = (values > 0).sum()
        elite = (values > 1.5).sum()
        total = len(values)

        # Scarcity = inverse of availability
        # Fewer above-average players = higher scarcity
        availability = above_avg / max(total, 1)
        scarcity_idx = round(1.0 / max(availability, 0.01), 2)

        scarcity_values[cat] = scarcity_idx
        scarcity.append(CategoryScarcity(
            category=cat,
            scarcity_index=scarcity_idx,
            above_avg_count=int(above_avg),
            elite_count=int(elite),
            league_avg=round(float(values.mean()), 3),
        ))

    # Normalize so average scarcity = 1.0
    avg_scarcity = np.mean(list(scarcity_values.values())) if scarcity_values else 1.0
    for s in scarcity:
        s.scarcity_index = round(s.scarcity_index / avg_scarcity, 2)

    scarcity.sort(key=lambda s: s.scarcity_index, reverse=True)
    return scarcity


# ── Combined: Schedule-Adjusted Player Values ──

def compute_advanced_metrics(
    player_z_df: pd.DataFrame,
    schedule: dict[str, ScheduleInfo] | None = None,
    consistency: dict[str, dict] | None = None,
    scarcity: list[CategoryScarcity] | None = None,
) -> dict[str, PlayerAdvancedMetrics]:
    """
    Compute all advanced metrics for each player.

    Combines z-scores with schedule, consistency, and scarcity
    into a single schedule-adjusted value.
    """
    if schedule is None:
        schedule = {}
    if consistency is None:
        consistency = {}

    # Build scarcity weight map
    scarcity_weights = {}
    if scarcity:
        for s in scarcity:
            scarcity_weights[s.category] = s.scarcity_index

    # Average games remaining across all teams (for normalization)
    if schedule:
        avg_remaining = np.mean([s.games_remaining for s in schedule.values()])
        avg_this_week = np.mean([s.games_this_week for s in schedule.values()])
        avg_playoff = np.mean([s.playoff_games for s in schedule.values()])
    else:
        avg_remaining = 20
        avg_this_week = 4
        avg_playoff = 12

    results = {}
    for _, row in player_z_df.iterrows():
        name = row.get("name", "")
        nba_team = row.get("nba_team", "")
        z_total = row.get("z_total", 0)

        # Schedule
        team_sched = schedule.get(nba_team, ScheduleInfo(team=nba_team, games_remaining=int(avg_remaining), games_this_week=int(avg_this_week), playoff_games=int(avg_playoff)))
        schedule_factor = team_sched.games_remaining / max(avg_remaining, 1)

        # Consistency
        cons = consistency.get(name, _default_consistency(row))
        cons_rating = cons["consistency_rating"]

        # Scarcity-adjusted z-score
        scarcity_z = 0.0
        for cat in ALL_CATS:
            z_col = f"z_{cat}"
            if z_col in row.index:
                w = scarcity_weights.get(cat, 1.0)
                scarcity_z += row[z_col] * w

        # Schedule-adjusted value
        # Formula: scarcity_z × schedule_factor × (0.7 + 0.3 * consistency)
        consistency_factor = 0.7 + 0.3 * cons_rating
        schedule_adjusted = scarcity_z * schedule_factor * consistency_factor

        # Rest-of-season value: schedule-adjusted + playoff bonus
        playoff_factor = team_sched.playoff_games / max(avg_playoff, 1)
        ros_value = schedule_adjusted * 0.7 + scarcity_z * playoff_factor * 0.3

        results[name] = PlayerAdvancedMetrics(
            name=name,
            games_remaining=team_sched.games_remaining,
            games_this_week=team_sched.games_this_week,
            playoff_games=team_sched.playoff_games,
            schedule_factor=round(schedule_factor, 3),
            consistency_rating=cons_rating,
            category_consistency=cons.get("category_consistency", {}),
            weekly_ceiling=cons.get("weekly_ceiling", z_total + 3),
            weekly_floor=cons.get("weekly_floor", z_total - 3),
            minutes_season=cons.get("minutes_season", 0),
            minutes_recent=cons.get("minutes_recent", 0),
            minutes_trend=cons.get("minutes_trend", 0),
            schedule_adjusted_z=round(schedule_adjusted, 2),
            ros_value=round(ros_value, 2),
        )

    return results
