"""
Tool executor: maps Claude's tool calls to our analytics functions.
"""
import json

from fantasy_engine.api.deps import get_state
from fantasy_engine.analytics.zscores import compute_zscores, compute_punt_zscores, ALL_CATS
from fantasy_engine.analytics.valuation import compute_valuations
from fantasy_engine.analytics.category_analysis import analyze_team
from fantasy_engine.analytics.trade_eval import evaluate_trade
from fantasy_engine.analytics.lineup import optimize_lineup
from fantasy_engine.analytics.add_drop import best_available, drop_candidates, best_swaps
from fantasy_engine.analytics.punting import find_optimal_punt


def execute_tool(name: str, input: dict) -> str:
    """Execute a tool call and return JSON string result."""
    state = get_state()

    try:
        if name == "get_player_rankings":
            return _get_player_rankings(state, input)
        elif name == "get_player_zscores":
            return _get_player_zscores(state, input)
        elif name == "get_team_profile":
            return _get_team_profile(state, input)
        elif name == "evaluate_trade":
            return _evaluate_trade(state, input)
        elif name == "optimize_lineup":
            return _optimize_lineup(state, input)
        elif name == "get_waiver_analysis":
            return _get_waiver_analysis(state, input)
        elif name == "get_dynasty_rankings":
            return _get_dynasty_rankings(state, input)
        elif name == "get_punt_strategies":
            return _get_punt_strategies(state, input)
        elif name == "get_roster":
            return _get_roster(state, input)
        elif name == "find_trades":
            return _find_trades(state, input)
        elif name == "get_alerts":
            return _get_alerts(state, input)
        elif name == "get_free_agents":
            return _get_free_agents(state, input)
        elif name == "get_league_standings":
            return _get_league_standings(state, input)
        elif name == "get_team_strategy":
            return _get_team_strategy(state, input)
        elif name == "get_monopolies":
            return _get_monopolies(state, input)
        elif name == "get_rotation_alerts":
            return _get_rotation_alerts(state, input)
        elif name == "get_weekly_lineup_plan":
            return _get_weekly_lineup_plan(state, input)
        elif name == "get_team_context":
            return _get_team_context(state, input)
        elif name == "get_player_trends":
            return _get_player_trends(state, input)
        elif name == "compare_vs_experts":
            return _compare_vs_experts(state, input)
        elif name == "get_advanced_metrics":
            return _get_advanced_metrics(state, input)
        elif name == "get_trade_suggestions":
            return _get_trade_suggestions(state, input)
        elif name == "get_manager_profile":
            return _get_manager_profile(state, input)
        elif name == "get_trade_grades":
            return _get_trade_grades(state, input)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _get_player_rankings(state, input):
    punt_cats = input.get("punt_cats", [])
    top = input.get("top", 15)

    if punt_cats:
        z_df = compute_punt_zscores(state.raw_df, punt_cats)
        for col in state.z_df.columns:
            if col not in z_df.columns:
                z_df[col] = state.z_df[col].values
    else:
        z_df = state.z_df

    sorted_df = z_df.sort_values("z_total", ascending=False).head(top)
    players = []
    for _, row in sorted_df.iterrows():
        p = {"name": row.get("name", ""), "salary": row.get("salary", 0),
             "z_total": round(row.get("z_total", 0), 2),
             "nba_team": row.get("nba_team", ""), "status": row.get("status", "")}
        for cat in ALL_CATS:
            p[f"z_{cat}"] = round(row.get(f"z_{cat}", 0), 2)
        players.append(p)
    return json.dumps({"players": players, "punt_cats": punt_cats})


def _get_player_zscores(state, input):
    name = input["name"].lower()
    match = state.z_df[state.z_df["name"].str.lower().str.contains(name)]
    if match.empty:
        return json.dumps({"error": f"Player '{input['name']}' not found on roster"})

    row = match.iloc[0]
    result = {
        "name": row.get("name", ""), "nba_team": row.get("nba_team", ""),
        "salary": row.get("salary", 0), "age": int(row.get("age", 0)),
        "positions": row.get("positions", ""), "status": row.get("status", ""),
        "games_played": int(row.get("games_played", 0)),
        "contract": row.get("contract", ""),
        "years_remaining": int(row.get("years_remaining", 1)),
        "z_total": round(row.get("z_total", 0), 2),
    }
    for cat in ALL_CATS:
        result[f"z_{cat}"] = round(row.get(f"z_{cat}", 0), 2)
    # Raw stats
    for stat in ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "tov"]:
        if stat in row.index:
            result[stat] = round(row[stat], 1)
    # Advanced metrics
    for col in ["schedule_adjusted_z", "ros_value", "consistency_rating",
                "games_remaining", "games_this_week", "playoff_games"]:
        if col in row.index:
            result[col] = round(float(row[col]), 2)
    return json.dumps(result)


def _get_team_profile(state, input):
    active_only = input.get("active_only", False)
    df = state.z_df[state.z_df["status"] == "Act"] if active_only else state.z_df
    profile = analyze_team(df)
    return json.dumps({
        "categories": {
            cat: {"z_sum": cp.z_sum, "rank": cp.rank, "strength": cp.strength}
            for cat, cp in profile.categories.items()
        },
        "strongest": profile.strongest_cats,
        "weakest": profile.weakest_cats,
        "suggested_punts": profile.suggested_punts,
        "total_z": round(profile.total_z, 2),
        "roster_type": "active only" if active_only else "full roster",
    })


def _evaluate_trade(state, input):
    ev = evaluate_trade(
        give_names=input["give"],
        receive_names=input["receive"],
        roster_z_df=state.z_df,
        salary_cap=state.settings.salary_cap,
        punt_cats=input.get("punt_cats", []),
    )
    return json.dumps({
        "verdict": ev.verdict,
        "combined_score": ev.combined_score,
        "z_diff": ev.z_diff,
        "salary_impact": ev.salary_impact,
        "cap_room_after": ev.cap_room_after,
        "dynasty_diff": ev.dynasty_diff,
        "cat_impact": ev.cat_impact,
        "improves": ev.improves_cats,
        "hurts": ev.hurts_cats,
        "give": {"players": ev.give.players, "total_salary": ev.give.total_salary,
                 "total_z": ev.give.total_z, "dynasty_value": ev.give.dynasty_value},
        "receive": {"players": ev.receive.players, "total_salary": ev.receive.total_salary,
                    "total_z": ev.receive.total_z, "dynasty_value": ev.receive.dynasty_value},
    })


def _optimize_lineup(state, input):
    rec = optimize_lineup(
        state.z_df,
        punt_cats=input.get("punt_cats", []),
        injured_players=input.get("injured", []),
    )
    return json.dumps({
        "active": [
            {"slot": s.slot, "player": s.player_name, "positions": s.positions,
             "games": s.games_this_week, "weekly_z": s.weekly_z}
            for s in rec.active
        ],
        "bench": rec.bench[:15],
        "total_weekly_z": rec.total_weekly_z,
        "category_z": rec.category_projections,
    })


def _get_waiver_analysis(state, input):
    punt_cats = input.get("punt_cats", [])
    top = input.get("top", 10)
    active_z = state.z_df[state.z_df["status"] == "Act"]
    reserve_z = state.z_df[state.z_df["status"] == "Res"]

    adds = best_available(active_z, reserve_z, punt_cats, top_n=top)
    drops = drop_candidates(active_z, punt_cats, top_n=top)
    swap_list = best_swaps(active_z, reserve_z, punt_cats, top_n=top)

    return json.dumps({
        "best_available": [
            {"name": a.name, "z_total": a.z_total, "need_z": a.need_weighted_z,
             "salary": a.salary, "helps": a.helps_cats}
            for a in adds
        ],
        "drop_candidates": [
            {"name": d.name, "z_total": d.z_total, "salary": d.salary,
             "score": d.droppability_score, "reason": d.reason}
            for d in drops
        ],
        "best_swaps": [
            {"drop": s.drop, "add": s.add, "net_z": s.net_z_change,
             "net_need_z": s.net_need_z_change, "salary_change": s.salary_change}
            for s in swap_list
        ],
    })


def _get_dynasty_rankings(state, input):
    top = input.get("top", 15)
    val_df = compute_valuations(state.z_df)
    val_df = val_df.sort_values("dynasty_value", ascending=False).head(top)
    return json.dumps({
        "players": [
            {"name": row.get("name", ""), "salary": row.get("salary", 0),
             "age": int(row.get("age", 0)), "years_remaining": int(row.get("years_remaining", 1)),
             "z_total": round(row.get("z_total", 0), 2),
             "z_per_dollar": round(row.get("z_per_dollar", 0), 2),
             "dynasty_value": round(row.get("dynasty_value", 0), 2),
             "age_factor": round(row.get("age_factor", 1), 2)}
            for _, row in val_df.iterrows()
        ]
    })


def _get_punt_strategies(state, input):
    max_punts = input.get("max_punts", 2)
    all_indices = list(range(len(state.raw_df)))
    results = find_optimal_punt(state.raw_df, all_indices, max_punt_cats=max_punts)
    return json.dumps({
        "strategies": results[:15],
    })


def _get_roster(state, input):
    status = input.get("status", "")
    df = state.z_df
    if status:
        df = df[df["status"] == status]

    players = []
    for _, row in df.sort_values("z_total", ascending=False).iterrows():
        players.append({
            "name": row.get("name", ""), "nba_team": row.get("nba_team", ""),
            "salary": row.get("salary", 0), "status": row.get("status", ""),
            "positions": row.get("positions", ""), "contract": row.get("contract", ""),
            "z_total": round(row.get("z_total", 0), 2),
        })
    return json.dumps({"roster": players, "count": len(players)})


def _find_trades(state, input):
    if not state.all_teams:
        return json.dumps({"error": "Full league data not loaded. Need refresh-full first."})

    from fantasy_engine.analytics.trade_finder import find_trades as _find
    proposals = _find(
        my_roster_z=state.z_df,
        all_teams=state.all_teams,
        my_team_id=state.team_id,
        punt_cats=input.get("punt_cats", []),
        top_n=input.get("top", 10),
    )
    return json.dumps({
        "proposals": [
            {"opponent": p.opponent_team, "give": p.give, "receive": p.receive,
             "my_score": p.my_score, "their_score": p.their_score,
             "mutual_score": p.mutual_score, "salary_diff": p.salary_diff,
             "z_diff": p.z_diff, "improves_me": p.improves_me, "improves_them": p.improves_them}
            for p in proposals
        ]
    })


def _get_alerts(state, input):
    from fantasy_engine.analytics.alerts import generate_alerts
    trade_proposals = None
    if state.all_teams:
        try:
            from fantasy_engine.analytics.trade_finder import find_trades as _find
            trade_proposals = _find(
                my_roster_z=state.z_df, all_teams=state.all_teams,
                my_team_id=state.team_id, top_n=3,
            )
        except Exception:
            pass

    alerts = generate_alerts(
        my_roster_z=state.z_df,
        free_agents_z=state.free_agents_z,
        injuries=state.injuries if state.injuries else None,
        trade_proposals=trade_proposals,
    )
    return json.dumps({
        "alerts": [
            {"type": a.type, "priority": a.priority, "title": a.title,
             "detail": a.detail, "player": a.player, "action": a.action}
            for a in alerts
        ]
    })


def _get_free_agents(state, input):
    if state.free_agents_z is None or state.free_agents_z.empty:
        return json.dumps({"error": "Full league data not loaded. Need refresh-full first."})

    top = input.get("top", 20)
    fa = state.free_agents_z.nlargest(top, "z_total")
    return json.dumps({
        "free_agents": [
            {"name": row.get("name", ""), "nba_team": row.get("nba_team", ""),
             "z_total": round(row.get("z_total", 0), 2),
             "pts": round(row.get("pts", 0), 1), "reb": round(row.get("reb", 0), 1),
             "ast": round(row.get("ast", 0), 1), "games": int(row.get("games_played", 0))}
            for _, row in fa.iterrows()
        ]
    })


def _get_league_standings(state, input):
    if not state.all_teams:
        return json.dumps({"error": "Full league data not loaded. Need refresh-full first."})

    teams = []
    for team_id, team_data in state.all_teams.items():
        roster_z = team_data.get("roster_z")
        if roster_z is None or roster_z.empty:
            continue
        profile = analyze_team(roster_z)
        sched_z = roster_z["schedule_adjusted_z"].sum() if "schedule_adjusted_z" in roster_z.columns else profile.total_z
        avg_cons = roster_z["consistency_rating"].mean() if "consistency_rating" in roster_z.columns else 0

        teams.append({
            "name": team_data["name"],
            "total_z": round(profile.total_z, 2),
            "schedule_adjusted_z": round(sched_z, 2),
            "avg_consistency": round(avg_cons, 2),
            "players": len(roster_z),
            "strongest": profile.strongest_cats,
            "weakest": profile.weakest_cats,
            "is_my_team": team_id == state.team_id,
        })
    teams.sort(key=lambda t: t["schedule_adjusted_z"], reverse=True)
    for i, t in enumerate(teams):
        t["power_rank"] = i + 1
    return json.dumps({"teams": teams})


def _get_team_strategy(state, input):
    if not state.all_teams:
        return json.dumps({"error": "Full league data needed"})
    from fantasy_engine.analytics.strategy import generate_strategy
    s = generate_strategy(
        state.z_df, state.all_teams, state.all_rostered_z,
        state.team_id, state.category_scarcity, state.injuries,
        state.settings.salary_cap,
    )
    return json.dumps({
        "category_build": {
            "target_5": s.category_build.target_5,
            "punt_4": s.category_build.punt_4,
            "expected_wins": s.category_build.expected_weekly_wins,
            "rationale": s.category_build.rationale,
        },
        "position_needs": [
            {"position": n.position, "need_level": n.need_level,
             "archetype": n.target_archetype, "current_best_z": n.current_best_z}
            for n in s.position_needs
        ],
        "extensions": [
            {"name": t.name, "cost": t.estimated_cost, "z": t.z_total, "fits": t.fits_cats}
            for t in s.extension_targets
        ],
        "trade_targets": [
            {"name": t.name, "team": t.team, "z": t.z_total, "age": t.age, "why": t.why}
            for t in s.trade_targets[:5]
        ],
        "fa_auction_targets": [
            {"name": t.name, "z": t.z_total, "cost": t.estimated_cost, "why": t.why}
            for t in s.fa_auction_targets[:5]
        ],
        "sell_candidates": [
            {"name": t.name, "z": t.z_total, "why": t.why}
            for t in s.sell_candidates
        ],
        "immediate_actions": s.immediate_actions,
        "offseason_plan": s.offseason_plan,
        "two_year_outlook": s.two_year_outlook,
    })


def _get_monopolies(state, input):
    if state.all_rostered_z is None:
        return json.dumps({"error": "Full league data needed"})
    from fantasy_engine.analytics.monopoly import detect_monopolies, detect_player_monopoly_value
    monopolies = detect_monopolies(state.all_rostered_z, state.z_df)
    player_monopolies = detect_player_monopoly_value(state.all_rostered_z, state.z_df)
    return json.dumps({
        "category_monopolies": [
            {"category": m.category, "total_elite": m.total_elite,
             "you_own": m.you_own, "you_own_names": m.you_own_names,
             "control_pct": m.league_control_pct,
             "top_players": [p["name"] for p in m.elite_players[:5]]}
            for m in monopolies if m.total_elite <= 20
        ],
        "your_irreplaceable_players": [
            {"name": p.name, "monopoly_cats": p.monopoly_cats,
             "score": p.monopoly_score, "difficulty": p.replacement_difficulty}
            for p in player_monopolies if p.monopoly_score > 0
        ],
    })


def _get_rotation_alerts(state, input):
    if not state.player_trends:
        return json.dumps({"error": "Trends not loaded"})
    from fantasy_engine.analytics.rotation_alerts import detect_rotation_changes
    alerts = detect_rotation_changes(state.player_trends, state.team_contexts or None)
    return json.dumps({
        "alerts": [
            {"player": a.player_name, "type": a.alert_type, "severity": a.severity,
             "min_season": a.minutes_season, "min_recent": a.minutes_recent,
             "change": a.minutes_change, "change_pct": a.minutes_change_pct,
             "description": a.description, "action": a.actionable}
            for a in alerts
        ]
    })


def _get_weekly_lineup_plan(state, input):
    view = input.get("view", "strategy")
    try:
        from fantasy_engine.ingestion.league_rules import get_current_matchup
        from fantasy_engine.ingestion.schedule import get_daily_schedule
        from fantasy_engine.analytics.weekly_optimizer import WeeklyOptimizer
        from datetime import date, timedelta

        matchup = get_current_matchup(state.league_rules, state.team_id, state.current_period)
        if not matchup:
            return json.dumps({"error": "No matchup found"})

        opp_data = state.all_teams.get(matchup["opponent_id"])
        if not opp_data:
            return json.dumps({"error": "Opponent data not found"})

        today = date.today()
        mon = today - timedelta(days=today.weekday())
        sun = mon + timedelta(days=6)
        daily = get_daily_schedule(mon, sun)

        optimizer = WeeklyOptimizer(
            my_roster_z=state.z_df,
            opp_roster_z=opp_data["roster_z"],
            daily_schedule=daily,
            opponent_name=matchup["opponent_name"],
            period=state.current_period,
            scarcity=state.category_scarcity,
            trends=state.player_trends,
            opportunities=state.player_opportunities,
            injuries=state.injuries,
        )
        plan = optimizer.optimize()

        if view == "strategy":
            return json.dumps({
                "opponent": plan.opponent,
                "expected_wins": plan.expected_wins,
                "target": plan.target_cats,
                "concede": plan.concede_cats,
                "swing": plan.swing_cats,
                "categories": [
                    {"cat": c.category, "status": c.status, "my": c.my_projected,
                     "opp": c.opp_projected, "margin": c.margin, "action": c.action}
                    for c in plan.categories
                ],
            })
        elif view == "today":
            today_str = today.isoformat()
            dl = plan.daily_lineups.get(today_str)
            if dl:
                return json.dumps({
                    "date": dl.date_str, "day": dl.day_name,
                    "active": [{"name": p["name"], "slot": p["slot"], "plays": p["plays_today"]} for p in dl.active],
                    "target": plan.target_cats, "concede": plan.concede_cats,
                })
            return json.dumps({"error": f"No lineup for {today_str}"})
        else:  # full plan
            return json.dumps({
                "opponent": plan.opponent,
                "expected_wins": plan.expected_wins,
                "target": plan.target_cats, "concede": plan.concede_cats,
                "days": {
                    k: {"day": v.day_name, "available": v.available_count,
                         "active": [p["name"] for p in v.active]}
                    for k, v in plan.daily_lineups.items()
                },
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


def _get_team_context(state, input):
    player_name = input.get("player_name", "")
    nba_team = input.get("nba_team", "")

    # Player-specific opportunity
    if player_name:
        for name, opp in state.player_opportunities.items():
            if player_name.lower() in name.lower():
                return json.dumps({
                    "player": opp.player_name,
                    "nba_team": opp.nba_team,
                    "opportunity_score": opp.opportunity_score,
                    "context_note": opp.context_note,
                    "teammates_out": [
                        {"name": a.player_name, "status": a.status, "return": a.return_date,
                         "minutes_freed": a.minutes_freed, "stats_lost": a.stats_lost}
                        for a in opp.teammates_out
                    ],
                    "total_minutes_freed": opp.total_minutes_freed,
                    "pts_opportunity": opp.pts_opportunity,
                    "ast_opportunity": opp.ast_opportunity,
                    "reb_opportunity": opp.reb_opportunity,
                })
        return json.dumps({"error": f"No context data for '{player_name}'"})

    # Team context
    if nba_team:
        ctx = state.team_contexts.get(nba_team)
        if ctx:
            return json.dumps({
                "team": ctx.team,
                "pace": ctx.pace,
                "total_minutes_out": ctx.total_minutes_out,
                "total_pts_out": ctx.total_pts_out,
                "total_ast_out": ctx.total_ast_out,
                "injured": [
                    {"name": a.player_name, "status": a.status, "return": a.return_date,
                     "minutes": a.minutes_freed, "stats": a.stats_lost}
                    for a in ctx.injured_players
                ],
                "beneficiaries": ctx.beneficiaries,
            })
        return json.dumps({"error": f"No context for team '{nba_team}'"})

    # Overview: teams with most opportunity
    high_opp = sorted(state.team_contexts.values(), key=lambda c: c.total_minutes_out, reverse=True)
    return json.dumps({
        "teams_with_most_opportunity": [
            {"team": c.team, "minutes_out": c.total_minutes_out,
             "pts_out": c.total_pts_out, "injured_count": len(c.injured_players),
             "beneficiaries": c.beneficiaries[:3]}
            for c in high_opp[:10] if c.total_minutes_out > 10
        ]
    })


def _get_player_trends(state, input):
    trends = state.player_trends
    if not trends:
        return json.dumps({"error": "Trends not loaded"})

    player_name = input.get("player_name", "")
    view = input.get("view", "")

    if player_name:
        for name, t in trends.items():
            if player_name.lower() in name.lower():
                return json.dumps({
                    "player": t.name, "trending": t.trending, "score": t.trend_score,
                    "games": t.games_total,
                    "season": t.season, "last_14": t.last_14, "last_7": t.last_7,
                    "cat_trends": t.cat_trends,
                    "minutes_season": t.minutes_season, "minutes_recent": t.minutes_recent,
                    "minutes_trend": t.minutes_trend,
                })
        return json.dumps({"error": f"No trend data for '{player_name}'"})

    if view == "rising":
        from fantasy_engine.analytics.trends import get_rising_players
        players = get_rising_players(trends, 10)
    elif view == "falling":
        from fantasy_engine.analytics.trends import get_falling_players
        players = get_falling_players(trends, 10)
    elif view == "minutes":
        from fantasy_engine.analytics.trends import get_minutes_gainers
        players = get_minutes_gainers(trends, 10)
    else:
        players = sorted(trends.values(), key=lambda t: abs(t.trend_score), reverse=True)[:10]

    return json.dumps({
        "players": [
            {"name": t.name, "trending": t.trending, "score": t.trend_score,
             "pts_14": t.last_14.get("pts", 0), "pts_season": t.season.get("pts", 0),
             "minutes_trend": t.minutes_trend}
            for t in players
        ]
    })


def _compare_vs_experts(state, input):
    comparisons = state.external_rankings
    if not comparisons:
        # Try to fetch live
        from fantasy_engine.ingestion.external import fetch_hashtag_rankings, compare_rankings
        ext = fetch_hashtag_rankings()
        if ext:
            source = state.all_rostered_z if state.all_rostered_z is not None else state.z_df
            comparisons = compare_rankings(source, ext)
        else:
            return json.dumps({"error": "Could not fetch expert rankings"})

    signal_filter = input.get("signal", "")
    if signal_filter:
        comparisons = [c for c in comparisons if c.signal == signal_filter]

    top = input.get("top", 15)
    return json.dumps({
        "comparisons": [
            {"name": c.name, "our_rank": c.our_rank, "our_z": c.our_z,
             "expert_rank": c.external_rank, "expert_z": c.external_z,
             "rank_diff": c.rank_diff, "signal": c.signal}
            for c in comparisons[:top]
        ]
    })


def _get_advanced_metrics(state, input):
    player_name = input.get("player_name", "")
    include_scarcity = input.get("include_scarcity", True)

    result = {}

    # Player-specific metrics
    if player_name:
        metrics = state.advanced_metrics
        for name, m in metrics.items():
            if player_name.lower() in name.lower():
                # Also get z-scores from z_df
                row = state.z_df[state.z_df["name"] == name]
                z_data = {}
                if not row.empty:
                    r = row.iloc[0]
                    z_data = {f"z_{c}": round(r.get(f"z_{c}", 0), 2) for c in ALL_CATS}
                    z_data["z_total"] = round(r.get("z_total", 0), 2)
                    z_data["salary"] = r.get("salary", 0)
                    z_data["age"] = int(r.get("age", 0))

                result["player"] = {
                    "name": m.name,
                    "schedule_adjusted_z": m.schedule_adjusted_z,
                    "ros_value": m.ros_value,
                    "consistency_rating": m.consistency_rating,
                    "games_remaining": m.games_remaining,
                    "games_this_week": m.games_this_week,
                    "playoff_games": m.playoff_games,
                    "schedule_factor": m.schedule_factor,
                    "weekly_ceiling": m.weekly_ceiling,
                    "weekly_floor": m.weekly_floor,
                    "minutes_trend": m.minutes_trend,
                    **z_data,
                }
                break
        if "player" not in result:
            result["error"] = f"Player '{player_name}' not found"
    else:
        # Top 10 by schedule-adjusted z
        sorted_m = sorted(state.advanced_metrics.values(), key=lambda m: m.schedule_adjusted_z, reverse=True)
        result["top_players"] = [
            {"name": m.name, "sched_z": m.schedule_adjusted_z, "ros": m.ros_value,
             "consistency": m.consistency_rating, "games_rem": m.games_remaining,
             "playoff": m.playoff_games, "ceil": m.weekly_ceiling, "floor": m.weekly_floor}
            for m in sorted_m[:10]
        ]

    # Category scarcity
    if include_scarcity and state.category_scarcity:
        result["scarcity"] = [
            {"category": s.category, "scarcity_index": s.scarcity_index,
             "elite_count": s.elite_count}
            for s in state.category_scarcity
        ]

    return json.dumps(result)


def _get_trade_suggestions(state, input):
    if not state.trade_intelligence:
        return json.dumps({"error": "Trade intelligence not loaded"})
    suggestions = state.trade_intelligence.generate_suggestions(
        punt_cats=input.get("punt_cats", []),
        max_suggestions=input.get("top", 10),
    )
    return json.dumps({
        "suggestions": [
            {"rank": s.rank, "give": s.give_players, "receive": s.receive_players,
             "opponent": s.opponent, "my_benefit": s.my_benefit,
             "their_benefit": s.their_benefit,
             "acceptance": s.acceptance_likelihood,
             "rationale": s.strategic_rationale, "salary": s.salary_impact}
            for s in suggestions
        ]
    })


def _get_manager_profile(state, input):
    if not state.trade_intelligence:
        return json.dumps({"error": "Trade intelligence not loaded"})
    name = input.get("team_name", "").lower()
    for tid, p in state.trade_intelligence.manager_profiles.items():
        if name in p.team_name.lower():
            return json.dumps({
                "team": p.team_name, "archetype": p.archetype.value,
                "total_z": p.total_z, "salary": p.total_salary, "cap_room": p.cap_room,
                "strongest": p.strongest_cats, "weakest": p.weakest_cats,
                "trades": p.num_trades, "picks_in": p.picks_acquired, "picks_out": p.picks_traded_away,
                "partners": p.trade_partners, "core": p.core_players,
                "expendable": p.expendable_players, "openness": p.trade_openness,
                "buying_signal": p.buying_signal, "waiver_moves": p.waiver_moves,
            })
    return json.dumps({"error": f"Team '{input.get('team_name')}' not found"})


def _get_trade_grades(state, input):
    if not state.trade_intelligence:
        return json.dumps({"error": "Trade intelligence not loaded"})
    graded = state.trade_intelligence.graded_trades
    return json.dumps({
        "trades": [
            {"date": gt.date, "teams": gt.teams, "winner": gt.winner,
             "fairness": gt.fairness,
             "grades": [
                 {"team": g.team_name, "grade": g.letter_grade, "score": g.numeric_score,
                  "z_change": g.z_change, "players_out": g.players_out,
                  "players_in": g.players_in, "picks_in": g.picks_in, "picks_out": g.picks_out}
                 for g in gt.grades
             ]}
            for gt in graded
        ]
    })
