"""
NBA team context analysis.

For each NBA team, analyzes:
- Who's injured and what stats they leave behind (opportunity)
- Who benefits from teammate absences (usage boost)
- Team pace and offensive rating context
- Upcoming opponent strength (strength of schedule)
"""
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS


@dataclass
class TeammateAbsence:
    """A missing player and the opportunity they create."""
    player_name: str
    status: str          # "Out", "Day-To-Day"
    return_date: str
    stats_lost: dict[str, float] = field(default_factory=dict)  # pts, reb, ast they contributed
    minutes_freed: float = 0


@dataclass
class PlayerOpportunity:
    """How a player benefits from team context."""
    player_name: str
    nba_team: str
    # Teammates out
    teammates_out: list[TeammateAbsence] = field(default_factory=list)
    total_minutes_freed: float = 0
    total_usage_freed: float = 0
    # Stat opportunity
    pts_opportunity: float = 0   # Extra points available from injured teammates
    reb_opportunity: float = 0
    ast_opportunity: float = 0
    # Context signals
    opportunity_score: float = 0  # 0-10, higher = more opportunity from context
    context_note: str = ""


@dataclass
class NBATeamContext:
    """Full context for an NBA team."""
    team: str
    injured_players: list[TeammateAbsence] = field(default_factory=list)
    total_minutes_out: float = 0
    total_pts_out: float = 0
    total_ast_out: float = 0
    total_reb_out: float = 0
    pace: float = 0
    off_rating: float = 0
    # Players who benefit
    beneficiaries: list[str] = field(default_factory=list)


def analyze_team_contexts(
    all_nba_stats: pd.DataFrame,
    injuries: list,
    advanced_stats: pd.DataFrame | None = None,
) -> dict[str, NBATeamContext]:
    """
    Analyze every NBA team's context: who's out and who benefits.

    Args:
        all_nba_stats: All NBA player stats (from nba_api LeagueDashPlayerStats)
        injuries: List of injury reports (from ESPN)
        advanced_stats: Advanced stats with usage rate, pace (optional)
    """
    # Build injury lookup by team
    injury_by_team: dict[str, list] = {}
    for inj in injuries:
        name = inj.player_name if hasattr(inj, "player_name") else inj.get("player", "")
        team = inj.team if hasattr(inj, "team") else inj.get("team", "")
        status = inj.status if hasattr(inj, "status") else inj.get("status", "")
        ret = inj.return_date if hasattr(inj, "return_date") else inj.get("return_date", "")

        if not team or status not in ("Out", "Day-To-Day"):
            continue

        injury_by_team.setdefault(team, []).append({
            "name": name, "status": status, "return_date": ret,
        })

    # Build stats lookup by name
    stats_by_name = {}
    for _, row in all_nba_stats.iterrows():
        stats_by_name[row.get("name", "").lower()] = row

    # Advanced stats by team
    team_pace = {}
    if advanced_stats is not None and not advanced_stats.empty:
        for team, group in advanced_stats.groupby("nba_team"):
            team_pace[team] = {
                "pace": group["pace"].mean() if "pace" in group.columns else 0,
                "off_rating": group.get("off_rating", pd.Series([0])).mean(),
            }

    contexts = {}

    # Get all NBA teams from stats
    teams = all_nba_stats["nba_team"].unique() if "nba_team" in all_nba_stats.columns else []

    for team in teams:
        team_str = str(team)
        ctx = NBATeamContext(team=team_str)

        # Pace context
        if team_str in team_pace:
            ctx.pace = round(team_pace[team_str]["pace"], 1)
            ctx.off_rating = round(team_pace[team_str]["off_rating"], 1)

        # Injured players on this team
        team_injuries = injury_by_team.get(team_str, [])
        for inj in team_injuries:
            player_stats = stats_by_name.get(inj["name"].lower())
            stats_lost = {}
            minutes_freed = 0

            if player_stats is not None:
                for stat in ["pts", "reb", "ast", "stl", "blk", "tpm", "tov"]:
                    stats_lost[stat] = round(float(player_stats.get(stat, 0)), 1)
                minutes_freed = float(player_stats.get("minutes", 0))

            absence = TeammateAbsence(
                player_name=inj["name"],
                status=inj["status"],
                return_date=inj.get("return_date", "")[:10] if inj.get("return_date") else "",
                stats_lost=stats_lost,
                minutes_freed=round(minutes_freed, 1),
            )
            ctx.injured_players.append(absence)
            ctx.total_minutes_out += minutes_freed
            ctx.total_pts_out += stats_lost.get("pts", 0)
            ctx.total_ast_out += stats_lost.get("ast", 0)
            ctx.total_reb_out += stats_lost.get("reb", 0)

        # Round totals
        ctx.total_minutes_out = round(ctx.total_minutes_out, 1)
        ctx.total_pts_out = round(ctx.total_pts_out, 1)
        ctx.total_ast_out = round(ctx.total_ast_out, 1)
        ctx.total_reb_out = round(ctx.total_reb_out, 1)

        # Identify beneficiaries: healthy players on this team
        team_players = all_nba_stats[all_nba_stats["nba_team"] == team_str]
        injured_names = {inj["name"].lower() for inj in team_injuries}
        healthy = team_players[~team_players["name"].str.lower().isin(injured_names)]
        # Top players by minutes = most likely to absorb opportunity
        if not healthy.empty and "minutes" in healthy.columns:
            top_healthy = healthy.nlargest(5, "minutes")
            ctx.beneficiaries = top_healthy["name"].tolist()

        contexts[team_str] = ctx

    return contexts


def compute_player_opportunities(
    roster_z_df: pd.DataFrame,
    team_contexts: dict[str, NBATeamContext],
) -> dict[str, PlayerOpportunity]:
    """
    For each player on the roster, compute their opportunity score
    based on their NBA team's context.
    """
    opportunities = {}

    for _, row in roster_z_df.iterrows():
        name = row.get("name", "")
        nba_team = row.get("nba_team", "")
        ctx = team_contexts.get(nba_team)

        opp = PlayerOpportunity(player_name=name, nba_team=nba_team)

        if ctx and ctx.injured_players:
            opp.teammates_out = ctx.injured_players
            opp.total_minutes_freed = ctx.total_minutes_out
            opp.pts_opportunity = ctx.total_pts_out
            opp.reb_opportunity = ctx.total_reb_out
            opp.ast_opportunity = ctx.total_ast_out

            # Usage freed estimate
            if ctx.total_minutes_out > 0:
                opp.total_usage_freed = round(ctx.total_minutes_out / 48 * 100, 1)

            # Opportunity score (0-10)
            score = 0
            score += min(3, ctx.total_minutes_out / 30)  # Up to 3 for minutes freed
            score += min(2, ctx.total_pts_out / 20)       # Up to 2 for points freed
            score += min(2, ctx.total_ast_out / 5)        # Up to 2 for assists freed
            score += min(1, len(ctx.injured_players) / 3) # Up to 1 for number of injuries

            # Is this player likely to benefit? (top of depth chart)
            if name in ctx.beneficiaries[:3]:
                score += 2  # Primary beneficiary bonus

            opp.opportunity_score = round(min(10, score), 1)

            # Context note
            injured_names = [a.player_name for a in ctx.injured_players[:3]]
            if opp.opportunity_score >= 5:
                opp.context_note = f"Big opportunity: {', '.join(injured_names)} out. {ctx.total_minutes_out:.0f} min freed."
            elif opp.opportunity_score >= 2:
                opp.context_note = f"Some upside: {', '.join(injured_names)} out."
            else:
                opp.context_note = ""

        opportunities[name] = opp

    return opportunities
