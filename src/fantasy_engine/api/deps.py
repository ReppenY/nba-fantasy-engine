"""
Shared dependencies for the API layer.

Loads roster data and computes z-scores once at startup.
Supports two modes:
  1. CSV: Load from a Fantrax CSV export
  2. Live: Pull from Fantrax Beta API + nba_api (no CSV needed)
"""
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field

from fantasy_engine.config import Settings
from fantasy_engine.ingestion.fantrax_csv import parse_roster_csv
from fantasy_engine.analytics.zscores import compute_zscores, ALL_CATS


@dataclass
class LeagueState:
    """Holds the current league data and computed analytics."""
    settings: Settings
    raw_df: pd.DataFrame
    z_df: pd.DataFrame
    team_name: str = ""
    team_id: str = ""
    roster_names: list[str] = field(default_factory=list)
    active_names: list[str] = field(default_factory=list)
    reserve_names: list[str] = field(default_factory=list)
    # Full league data (populated by init_state_full)
    all_teams: dict = field(default_factory=dict)
    free_agents_z: pd.DataFrame | None = None
    all_rostered_z: pd.DataFrame | None = None
    team_names: dict = field(default_factory=dict)
    injuries: list = field(default_factory=list)
    games_this_week: dict = field(default_factory=dict)
    league_rules: object = None  # LeagueRules instance
    current_period: int = 0
    trade_intelligence: object = None  # TradeIntelligence instance
    advanced_metrics: dict = field(default_factory=dict)  # name -> PlayerAdvancedMetrics
    category_scarcity: list = field(default_factory=list)  # CategoryScarcity list
    schedule_info: dict = field(default_factory=dict)  # team -> ScheduleInfo
    player_trends: dict = field(default_factory=dict)  # name -> PlayerTrend
    external_rankings: list = field(default_factory=list)  # RankingComparison list
    nba_advanced: pd.DataFrame | None = None  # Usage rate, pace, etc.
    team_contexts: dict = field(default_factory=dict)  # team -> NBATeamContext
    player_opportunities: dict = field(default_factory=dict)  # name -> PlayerOpportunity
    team_strategy: object = None  # TeamStrategy — target/punt categories


_state: LeagueState | None = None


def get_state() -> LeagueState:
    if _state is None:
        raise RuntimeError("League state not initialized. Call init_state() or init_state_live() first.")
    return _state


def init_state(csv_path: str, settings: Settings | None = None) -> LeagueState:
    """Initialize league state from a Fantrax CSV export."""
    global _state
    if settings is None:
        settings = Settings()

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = parse_roster_csv(path)
    _estimate_shooting_volume(df)

    _state = _build_state(df, settings)
    return _state


def init_state_live(
    league_id: str,
    team_id: str,
    settings: Settings | None = None,
    season: str = "2025-26",
) -> LeagueState:
    """
    Initialize league state from Fantrax API + nba_api.

    No CSV needed — pulls everything live:
      - Fantrax API: roster, salaries, contracts, status, positions
      - nba_api: per-game stats (pts, reb, ast, etc.)
    """
    global _state
    if settings is None:
        settings = Settings()

    print(f"Fetching roster from Fantrax API (league: {league_id}, team: {team_id})...")
    from fantasy_engine.ingestion.fantrax_api import FantraxAPIClient, merge_with_nba_stats

    client = FantraxAPIClient(league_id)

    # Get team name
    team_names = client.get_team_names()
    team_name = team_names.get(team_id, team_id)
    print(f"  Team: {team_name}")

    # Get roster from Fantrax
    roster_df = client.get_team_roster_df(team_id)
    print(f"  Roster: {len(roster_df)} players")

    # Get NBA stats
    print(f"Fetching NBA stats from nba_api (season: {season})...")
    from fantasy_engine.ingestion.nba_stats import NBAStatsClient
    nba_client = NBAStatsClient()
    nba_stats = nba_client.get_all_player_averages(season)
    print(f"  NBA players: {len(nba_stats)}")

    # Merge
    print("Merging roster with NBA stats...")
    df = merge_with_nba_stats(roster_df, nba_stats)

    # Check how many matched
    matched = df[df["games_played"] > 0]
    print(f"  Matched: {len(matched)}/{len(df)} players have stats")
    unmatched = df[df["games_played"] == 0]["name"].tolist()
    if unmatched:
        print(f"  No stats for: {', '.join(unmatched[:10])}")

    _state = _build_state(df, settings, team_name=team_name, team_id=team_id)

    # Load injuries (always, even in single-team mode)
    print("Fetching injuries from ESPN...")
    try:
        from fantasy_engine.ingestion.injuries import fetch_all_injuries
        _state.injuries = fetch_all_injuries()
        print(f"  Injuries loaded: {len(_state.injuries)}")
    except Exception as e:
        print(f"  Injuries failed: {e}")

    return _state


def init_state_full(
    league_id: str,
    team_id: str,
    settings: Settings | None = None,
    season: str = "2025-26",
) -> LeagueState:
    """
    Full league load: all 12 teams, free agents, injuries, schedule.

    This is the most complete mode — powers all features including
    trade finder, real opponent matchups, and alerts.
    """
    global _state
    if settings is None:
        settings = Settings()

    # Load full league
    from fantasy_engine.ingestion.league_loader import load_full_league
    league = load_full_league(league_id, team_id, season=season)

    my_team_z = league["my_team"]
    df = my_team_z.copy()

    # Build base state
    _state = _build_state(df, settings, team_name=league["team_names"].get(team_id, ""), team_id=team_id)

    # Attach full league data
    _state.all_teams = league["teams"]
    _state.free_agents_z = league["free_agents"]
    _state.all_rostered_z = league["all_rostered"]
    _state.team_names = league["team_names"]

    # Load league rules (matchup schedule, position eligibility, roster constraints)
    print("Loading league rules...")
    try:
        from fantasy_engine.ingestion.league_rules import load_league_rules
        rules = load_league_rules(league_id)
        _state.league_rules = rules
        _state.team_names = rules.team_names

        # Fix position eligibility from league rules (more accurate)
        for _, row in _state.z_df.iterrows():
            fid = row.get("fantrax_id", "")
            if fid and fid in rules.player_eligibility:
                _state.z_df.loc[_state.z_df["fantrax_id"] == fid, "positions"] = rules.player_eligibility[fid]

        # Determine current period (latest with matchups)
        my_matchups = [m for m in rules.matchup_schedule
                       if m.away_id == team_id or m.home_id == team_id]
        if my_matchups:
            _state.current_period = max(m.period for m in my_matchups)
        print(f"  Rules loaded: {len(rules.matchup_schedule)} matchups, "
              f"{len(rules.player_eligibility)} player positions, "
              f"current period: {_state.current_period}")
    except Exception as e:
        print(f"  League rules failed: {e}")

    # Load injuries from ESPN
    print("Fetching injuries from ESPN...")
    try:
        from fantasy_engine.ingestion.injuries import fetch_all_injuries
        _state.injuries = fetch_all_injuries()
        print(f"  Injuries loaded: {len(_state.injuries)}")
    except Exception as e:
        print(f"  Injuries failed: {e}")

    # Load schedule
    print("Fetching weekly schedule...")
    try:
        from fantasy_engine.ingestion.schedule import get_weekly_games
        _state.games_this_week = get_weekly_games(season=season)
        print(f"  Schedule loaded: {len(_state.games_this_week)} teams")
    except Exception as e:
        print(f"  Schedule failed: {e}")

    # Analyze team contexts (injuries creating opportunity)
    print("Analyzing team contexts...")
    try:
        from fantasy_engine.analytics.team_context import analyze_team_contexts, compute_player_opportunities
        nba_stats = league.get("nba_stats")
        if nba_stats is not None and _state.injuries:
            _state.team_contexts = analyze_team_contexts(nba_stats, _state.injuries, _state.nba_advanced)
            _state.player_opportunities = compute_player_opportunities(_state.z_df, _state.team_contexts)
            high_opp = [p for p in _state.player_opportunities.values() if p.opportunity_score >= 3]
            print(f"  Team contexts: {len(_state.team_contexts)} teams, {len(high_opp)} players with high opportunity")
    except Exception as e:
        print(f"  Team context failed: {e}")

    # Save snapshot for history
    try:
        from fantasy_engine.analytics.history import save_snapshot
        snapshot_date = save_snapshot(league["all_rostered"])
        print(f"  History snapshot saved: {snapshot_date}")
    except Exception as e:
        print(f"  History snapshot failed: {e}")

    # Compute advanced metrics (schedule, consistency, scarcity)
    print("Computing advanced metrics...")
    try:
        from fantasy_engine.analytics.advanced_metrics import (
            compute_schedule_info, compute_consistency,
            compute_scarcity, compute_advanced_metrics,
        )

        sched = compute_schedule_info(season=season)
        _state.schedule_info = sched
        print(f"  Schedule: {len(sched)} teams")

        cons = compute_consistency(_state.z_df)
        print(f"  Consistency: {len(cons)} players")

        scarcity = compute_scarcity(_state.all_rostered_z if _state.all_rostered_z is not None else _state.z_df)
        _state.category_scarcity = scarcity
        # Set global scarcity cache so all modules auto-use it
        from fantasy_engine.analytics.category_analysis import set_scarcity_cache
        set_scarcity_cache(scarcity)
        top_scarce = sorted(scarcity, key=lambda s: s.scarcity_index, reverse=True)[:3]
        print(f"  Scarcity: most scarce = {', '.join(s.category.upper() for s in top_scarce)}")

        # Compute positional scarcity (within-position z vs pool-wide z)
        try:
            from fantasy_engine.analytics.positional_scarcity import (
                compute_positional_scarcity, set_position_scarcity_cache,
            )
            pos_source = _state.all_rostered_z if _state.all_rostered_z is not None else _state.z_df
            pos_result = compute_positional_scarcity(pos_source, num_teams=12)
            pos_stats = pos_result.attrs.get("pos_stats", {})

            # Set global cache
            name_to_bonus = dict(zip(pos_source["name"], pos_result["pos_scarcity_bonus"]))
            set_position_scarcity_cache(name_to_bonus, pos_stats)

            # Inject columns into all DataFrames
            name_to_pos = dict(zip(pos_source["name"], pos_result["scarcest_position"]))
            for target_df in [_state.z_df, _state.all_rostered_z]:
                if target_df is not None and "name" in target_df.columns:
                    target_df["pos_scarcity_bonus"] = target_df["name"].map(name_to_bonus).fillna(0.0)
                    target_df["scarcest_position"] = target_df["name"].map(name_to_pos).fillna("")

            for tid_inner, tdata_inner in _state.all_teams.items():
                rz_inner = tdata_inner.get("roster_z")
                if rz_inner is not None and "name" in rz_inner.columns:
                    rz_inner["pos_scarcity_bonus"] = rz_inner["name"].map(name_to_bonus).fillna(0.0)
                    rz_inner["scarcest_position"] = rz_inner["name"].map(name_to_pos).fillna("")

            parts = [f"{p}: n={d['count']} starter={d.get('starter_avg',0):.1f} repl={d.get('replacement_avg',0):.1f} drop={d.get('dropoff',0):.1f} bonus={d.get('bonus',0):+.2f}"
                     for p, d in sorted(pos_stats.items())]
            print(f"  Position scarcity: {'; '.join(parts)}")
        except Exception as e:
            print(f"  Positional scarcity failed: {e}")

        adv = compute_advanced_metrics(_state.z_df, sched, cons, scarcity)
        _state.advanced_metrics = adv
        print(f"  Advanced metrics: {len(adv)} players (my roster)")

        # Inject into my roster z_df
        for name, m in adv.items():
            mask = _state.z_df["name"] == name
            if mask.any():
                _state.z_df.loc[mask, "schedule_adjusted_z"] = m.schedule_adjusted_z
                _state.z_df.loc[mask, "ros_value"] = m.ros_value
                _state.z_df.loc[mask, "consistency_rating"] = m.consistency_rating
                _state.z_df.loc[mask, "games_remaining"] = m.games_remaining
                _state.z_df.loc[mask, "games_this_week"] = m.games_this_week
                _state.z_df.loc[mask, "playoff_games"] = m.playoff_games

        # Compute for ALL rostered players (league-wide) using estimated consistency
        if _state.all_rostered_z is not None:
            all_cons = compute_consistency(_state.all_rostered_z)
            all_adv = compute_advanced_metrics(_state.all_rostered_z, sched, all_cons, scarcity)
            print(f"  League-wide metrics: {len(all_adv)} players")

            # Inject into all_rostered_z
            for name, m in all_adv.items():
                mask = _state.all_rostered_z["name"] == name
                if mask.any():
                    _state.all_rostered_z.loc[mask, "schedule_adjusted_z"] = m.schedule_adjusted_z
                    _state.all_rostered_z.loc[mask, "ros_value"] = m.ros_value
                    _state.all_rostered_z.loc[mask, "consistency_rating"] = m.consistency_rating
                    _state.all_rostered_z.loc[mask, "games_remaining"] = m.games_remaining
                    _state.all_rostered_z.loc[mask, "games_this_week"] = m.games_this_week
                    _state.all_rostered_z.loc[mask, "playoff_games"] = m.playoff_games

            # Also inject into per-team roster_z DataFrames
            for team_id, team_data in _state.all_teams.items():
                rz = team_data.get("roster_z")
                if rz is not None:
                    for name, m in all_adv.items():
                        mask = rz["name"] == name
                        if mask.any():
                            rz.loc[mask, "schedule_adjusted_z"] = m.schedule_adjusted_z
                            rz.loc[mask, "ros_value"] = m.ros_value
                            rz.loc[mask, "consistency_rating"] = m.consistency_rating
                            rz.loc[mask, "games_remaining"] = m.games_remaining
                            rz.loc[mask, "games_this_week"] = m.games_this_week
                            rz.loc[mask, "playoff_games"] = m.playoff_games
    except Exception as e:
        print(f"  Advanced metrics failed: {e}")
        import traceback
        traceback.print_exc()

    # Fetch NBA advanced stats (usage rate, pace)
    print("Fetching NBA advanced stats...")
    try:
        from fantasy_engine.ingestion.nba_advanced import get_advanced_stats, merge_advanced_stats
        adv_stats = get_advanced_stats(season=season)
        if not adv_stats.empty:
            _state.nba_advanced = adv_stats
            _state.z_df = merge_advanced_stats(_state.z_df, adv_stats)
            print(f"  Advanced stats: {len(adv_stats)} players (usage rate, pace)")
    except Exception as e:
        print(f"  NBA advanced stats failed: {e}")

    # Fetch game logs and compute trends (limited to roster players to avoid rate limits)
    print("Fetching game logs for trends...")
    try:
        from fantasy_engine.analytics.trends import fetch_game_logs_batch, compute_all_trends

        # Get nba_api IDs for roster players
        player_ids = {}
        for _, row in _state.z_df.iterrows():
            pid = row.get("nba_api_id", 0)
            name = row.get("name", "")
            try:
                pid_int = int(float(pid)) if pid and not pd.isna(pid) else 0
                if pid_int > 0 and name:
                    player_ids[name] = pid_int
            except (ValueError, TypeError):
                pass

        # Also check all_rostered for IDs
        if not player_ids and _state.all_rostered_z is not None:
            for _, row in _state.all_rostered_z.iterrows():
                pid = row.get("nba_api_id", 0)
                name = row.get("name", "")
                try:
                    pid_int = int(float(pid)) if pid and not pd.isna(pid) else 0
                    if pid_int > 0 and name:
                        player_ids[name] = pid_int
                except (ValueError, TypeError):
                    pass

        if player_ids:
            game_logs = fetch_game_logs_batch(player_ids, season=season, max_players=35)
            _state.player_trends = compute_all_trends(game_logs)
            hot = [t for t in _state.player_trends.values() if t.trending in ("hot", "rising")]
            cold = [t for t in _state.player_trends.values() if t.trending in ("cold", "cooling")]
            print(f"  Trends: {len(_state.player_trends)} players ({len(hot)} hot, {len(cold)} cold)")
    except Exception as e:
        print(f"  Game log trends failed: {e}")

    # Fetch external rankings (Hashtag Basketball)
    print("Fetching Hashtag Basketball rankings...")
    try:
        from fantasy_engine.ingestion.external import fetch_hashtag_rankings, compare_rankings
        ext = fetch_hashtag_rankings()
        if ext:
            source_df = _state.all_rostered_z if _state.all_rostered_z is not None else _state.z_df
            _state.external_rankings = compare_rankings(source_df, ext)
            buy_low = len([c for c in _state.external_rankings if c.signal == "buy_low"])
            sell_high = len([c for c in _state.external_rankings if c.signal == "sell_high"])
            print(f"  External rankings: {len(ext)} players, {buy_low} buy-low, {sell_high} sell-high signals")
    except Exception as e:
        print(f"  External rankings failed: {e}")

    # Initialize Trade Intelligence
    print("Building trade intelligence...")
    try:
        import os
        from fantasy_engine.analytics.trade_intelligence import TradeIntelligence
        from fantasy_engine.ingestion.trade_history import (
            parse_trades_csv, parse_lineup_changes_csv, analyze_lineup_patterns,
        )
        from fantasy_engine.ingestion.transactions import parse_transactions_csv, analyze_team_activity

        # Load trade history CSV
        trades_csv = os.environ.get(
            "FANTASY_TRADES_CSV",
            os.path.expanduser("~/Downloads/Fantrax-Transaction-History-Trades-Black Mamba Snake Pit.csv"),
        )
        completed_trades = []
        if Path(trades_csv).exists():
            completed_trades = parse_trades_csv(trades_csv)
            print(f"  Trades loaded: {len(completed_trades)}")

        # Load waiver activity
        waivers_csv = os.environ.get(
            "FANTASY_WAIVERS_CSV",
            os.path.expanduser("~/Downloads/Fantrax-Transaction-History-Claims+Drops-Black Mamba Snake Pit.csv"),
        )
        waiver_activity = {}
        if Path(waivers_csv).exists():
            waiver_df = parse_transactions_csv(waivers_csv)
            waiver_activity = analyze_team_activity(waiver_df)
            print(f"  Waiver activity loaded: {len(waiver_activity)} teams")

        # Load lineup patterns
        lineup_csv = os.environ.get(
            "FANTASY_LINEUP_CSV",
            os.path.expanduser("~/Downloads/Fantrax-Transaction-History-Lineup Changes-Black Mamba Snake Pit.csv"),
        )
        lineup_patterns = {}
        if Path(lineup_csv).exists():
            lineup_df = parse_lineup_changes_csv(lineup_csv)
            lineup_patterns = analyze_lineup_patterns(lineup_df)
            print(f"  Lineup patterns loaded: {len(lineup_patterns)} teams")

        print(f"  Trade Intel team_id: {team_id}, state.team_id: {_state.team_id}")
        _state.trade_intelligence = TradeIntelligence(
            all_teams=_state.all_teams,
            my_team_id=_state.team_id,  # Use state's team_id, not the parameter
            my_roster_z=_state.z_df,
            salary_cap=settings.salary_cap,
            completed_trades=completed_trades,
            waiver_activity=waiver_activity,
            lineup_patterns=lineup_patterns,
            injuries=_state.injuries,
            all_rostered_z=_state.all_rostered_z,
        )
        print(f"  Trade intelligence ready")
    except Exception as e:
        print(f"  Trade intelligence failed: {e}")
        import traceback
        traceback.print_exc()

    # Compute team strategy (target categories, position needs, etc.)
    print("Computing team strategy...")
    try:
        from fantasy_engine.analytics.strategy import generate_strategy
        _state.team_strategy = generate_strategy(
            _state.z_df, _state.all_teams, _state.all_rostered_z,
            _state.team_id, _state.category_scarcity, _state.injuries,
            settings.salary_cap,
        )
        # Set strategy punt cache so ALL modules auto-apply the build
        from fantasy_engine.analytics.category_analysis import set_strategy_punt_cache
        set_strategy_punt_cache(_state.team_strategy.category_build.punt_4)
        print(f"  Strategy: target {_state.team_strategy.category_build.target_5}, "
              f"punt {_state.team_strategy.category_build.punt_4}")
    except Exception as e:
        print(f"  Strategy failed: {e}")

    return _state


def _build_state(
    df: pd.DataFrame,
    settings: Settings,
    team_name: str = "",
    team_id: str = "",
) -> LeagueState:
    """Build LeagueState from a prepared DataFrame."""
    z_df = compute_zscores(df)

    # Carry forward all useful columns
    carry = [
        "salary", "age", "years_remaining", "is_expiring", "status",
        "nba_team", "positions", "games_played", "fantrax_id", "name",
        "nba_api_id", "contract", "roster_slot",
        "pts", "reb", "ast", "stl", "blk", "tpm", "tov",
        "fgm", "fga", "fg_pct", "ftm", "fta", "ft_pct",
    ]
    for col in carry:
        if col in df.columns:
            z_df[col] = df[col].values

    roster_names = z_df["name"].tolist()
    active_names = z_df[z_df["status"] == "Act"]["name"].tolist()
    reserve_names = z_df[z_df["status"] == "Res"]["name"].tolist()

    return LeagueState(
        settings=settings,
        raw_df=df,
        z_df=z_df,
        team_name=team_name,
        team_id=team_id,
        roster_names=roster_names,
        active_names=active_names,
        reserve_names=reserve_names,
    )


def _estimate_shooting_volume(df: pd.DataFrame):
    """Estimate FGM, FGA, FTM, FTA from available stats (for CSV-only mode)."""
    if "fgm" in df.columns and df["fgm"].sum() > 0:
        return  # Already has real shooting data
    df["fta"] = df["pts"] * 0.25
    df["ftm"] = df["fta"] * df["ft_pct"]
    fg_pts = (df["pts"] - df["ftm"]).clip(lower=0)
    df["fgm"] = ((fg_pts - df["tpm"]) / 2).clip(lower=0)
    df["fga"] = (df["fgm"] / df["fg_pct"].replace(0, float("nan"))).fillna(0)
