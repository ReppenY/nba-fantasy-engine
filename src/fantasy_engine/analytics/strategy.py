"""
Team strategy engine.

Generates a comprehensive rebuilding/competing strategy including:
- Which 5 categories to build around (category focus)
- Position-by-position needs
- Player archetype targets for draft and trades
- FA auction targets (expiring contracts entering the pool)
- Rookie draft targets
- Trade targets (specific players on other teams)
- Timeline: what to do now, next off-season, and 2-3 years out
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from itertools import combinations

from fantasy_engine.analytics.zscores import ALL_CATS, COUNTING_CATS
from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights


@dataclass
class CategoryBuild:
    """Which categories to dominate."""
    target_5: list[str]        # The 5 categories to build around
    punt_4: list[str]          # The 4 to concede
    expected_weekly_wins: float
    rationale: str


@dataclass
class PositionNeed:
    """What you need at each position."""
    position: str
    current_players: list[str]
    current_best_z: float
    need_level: str           # "critical", "upgrade", "fine", "surplus"
    target_archetype: str     # "elite scorer", "3-and-D wing", "rim protector", etc.
    target_cats: list[str]    # Categories this position should provide


@dataclass
class PlayerTarget:
    """A specific player to target."""
    name: str
    team: str
    why: str
    target_method: str        # "trade", "fa_auction", "rookie_draft", "extend"
    estimated_cost: str       # "$15 at auction" or "your Rd1 pick" or "$10.50/yr extension"
    fits_cats: list[str]
    age: int
    z_total: float


@dataclass
class TeamStrategy:
    """Complete team strategy."""
    # Category build
    category_build: CategoryBuild
    # Position needs
    position_needs: list[PositionNeed]
    # Targets
    extension_targets: list[PlayerTarget]    # Players to extend (3rd year)
    trade_targets: list[PlayerTarget]        # Players to acquire via trade
    fa_auction_targets: list[PlayerTarget]   # Expiring players entering FA auction
    rookie_targets: list[PlayerTarget]       # What to look for in rookie draft
    sell_candidates: list[PlayerTarget]      # Players to trade away
    # Timeline
    immediate_actions: list[str]
    offseason_plan: list[str]
    two_year_outlook: str


def generate_strategy(
    my_roster_z: pd.DataFrame,
    all_teams: dict,
    all_rostered_z: pd.DataFrame,
    my_team_id: str,
    category_scarcity: list | None = None,
    injuries: list | None = None,
    salary_cap: float = 233.0,
) -> TeamStrategy:
    """Generate a comprehensive team strategy."""

    # 1. Find optimal 5-category build
    cat_build = _find_optimal_category_build(my_roster_z, all_teams, my_team_id, category_scarcity)

    # 2. Position needs
    pos_needs = _analyze_position_needs(my_roster_z, cat_build.target_5)

    # 3. Extension targets (3rd year players)
    extensions = _find_extension_targets(my_roster_z, cat_build.target_5)

    # 4. Trade targets (from other teams)
    trade_targets = _find_trade_targets(my_roster_z, all_teams, my_team_id, cat_build.target_5, pos_needs)

    # 5. FA auction targets (expiring contracts league-wide)
    fa_targets = _find_fa_auction_targets(all_rostered_z, my_roster_z, cat_build.target_5)

    # 6. Rookie draft targets (archetypes)
    rookie_targets = _find_rookie_targets(cat_build.target_5, pos_needs)

    # 7. Sell candidates (players that don't fit the build)
    sell_candidates = _find_sell_candidates(my_roster_z, cat_build.target_5, cat_build.punt_4)

    # 8. Timeline
    immediate, offseason, outlook = _build_timeline(
        cat_build, extensions, trade_targets, sell_candidates, my_roster_z, salary_cap,
    )

    return TeamStrategy(
        category_build=cat_build,
        position_needs=pos_needs,
        extension_targets=extensions,
        trade_targets=trade_targets,
        fa_auction_targets=fa_targets,
        rookie_targets=rookie_targets,
        sell_candidates=sell_candidates,
        immediate_actions=immediate,
        offseason_plan=offseason,
        two_year_outlook=outlook,
    )


def _find_optimal_category_build(
    my_roster_z: pd.DataFrame,
    all_teams: dict,
    my_team_id: str,
    category_scarcity: list | None,
) -> CategoryBuild:
    """
    Find the best 5 categories to dominate.

    Strategy: pick 5 categories where:
    1. You already have a foundation (not starting from zero)
    2. The league competition is weakest
    3. Scarcity favors you (easier to corner the market)
    4. Your young core naturally produces these stats
    """
    profile = analyze_team(my_roster_z)

    # Score each category
    cat_scores = {}
    for cat in ALL_CATS:
        cp = profile.categories.get(cat)
        z_sum = cp.z_sum if cp else 0

        # Base: how good am I already?
        score = z_sum * 0.5

        # Scarcity bonus: scarce categories are easier to dominate
        if category_scarcity:
            for s in category_scarcity:
                scat = s.category if hasattr(s, "category") else s.get("category", "")
                sidx = s.scarcity_index if hasattr(s, "scarcity_index") else s.get("scarcity_index", 1.0)
                if scat == cat:
                    score += (sidx - 1.0) * 3  # Scarcity bonus

        # Young core bonus: which categories do my young players produce?
        young = my_roster_z[(my_roster_z.get("age", pd.Series(dtype=float)).fillna(30) <= 25)]
        if not young.empty and f"z_{cat}" in young.columns:
            young_z = young[f"z_{cat}"].sum()
            score += young_z * 0.3  # Young players contributing = sustainable

        # League weakness: which categories do opponents struggle in?
        league_weakness = 0
        for tid, tdata in all_teams.items():
            if tid == my_team_id:
                continue
            rz = tdata.get("roster_z")
            if rz is not None and f"z_{cat}" in rz.columns:
                opp_z = rz[f"z_{cat}"].sum()
                if opp_z < 0:
                    league_weakness += 1
        score += league_weakness * 0.2

        cat_scores[cat] = round(score, 2)

    # Pick top 5
    sorted_cats = sorted(cat_scores.items(), key=lambda x: x[1], reverse=True)
    target_5 = [cat for cat, _ in sorted_cats[:5]]
    punt_4 = [cat for cat, _ in sorted_cats[5:]]

    # Calculate expected wins with this build
    expected = len(target_5) * 0.65 + len(punt_4) * 0.15  # ~65% win rate on targets, 15% on punts

    cat_labels = {
        "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK",
        "tpm": "3PM", "fg_pct": "FG%", "ft_pct": "FT%", "tov": "TO",
    }
    target_names = [cat_labels.get(c, c) for c in target_5]
    punt_names = [cat_labels.get(c, c) for c in punt_4]

    rationale = (
        f"Build around {', '.join(target_names)}. "
        f"Punt {', '.join(punt_names)}. "
        f"This gives you ~{expected:.1f} expected category wins per week. "
        f"Your young core already contributes to {', '.join(target_names[:3])}, "
        f"making this sustainable long-term."
    )

    return CategoryBuild(
        target_5=target_5, punt_4=punt_4,
        expected_weekly_wins=round(expected, 1),
        rationale=rationale,
    )


def _analyze_position_needs(
    my_roster_z: pd.DataFrame,
    target_cats: list[str],
) -> list[PositionNeed]:
    """Analyze what each position needs based on the category build."""
    positions = ["PG", "SG", "SF", "PF", "C"]
    needs = []

    cat_labels = {"pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK",
                  "tpm": "3PM", "fg_pct": "FG%", "ft_pct": "FT%", "tov": "TO"}

    # Position-to-category mapping (what each position typically provides)
    pos_cat_map = {
        "PG": ["ast", "stl", "tpm", "ft_pct"],
        "SG": ["pts", "tpm", "stl", "ft_pct"],
        "SF": ["pts", "reb", "stl", "tpm"],
        "PF": ["reb", "blk", "fg_pct", "pts"],
        "C": ["reb", "blk", "fg_pct", "tov"],
    }

    for pos in positions:
        # Find players eligible for this position
        eligible = my_roster_z[
            my_roster_z["positions"].fillna("").str.contains(pos, case=False)
        ] if "positions" in my_roster_z.columns else pd.DataFrame()

        current_players = eligible["name"].tolist() if not eligible.empty else []
        best_z = eligible["z_total"].max() if not eligible.empty and "z_total" in eligible.columns else 0

        # Determine need level
        if len(current_players) == 0:
            need_level = "critical"
        elif best_z < 0:
            need_level = "critical"
        elif best_z < 2:
            need_level = "upgrade"
        elif len(current_players) >= 4:
            need_level = "surplus"
        else:
            need_level = "fine"

        # Escalate need level if position has a thin replacement pool
        try:
            from fantasy_engine.analytics.positional_scarcity import get_replacement_levels
            rep_levels = get_replacement_levels()
            pos_rep = rep_levels.get(pos, 0)
            if pos_rep < -1.0 and need_level == "upgrade":
                need_level = "critical"
            elif pos_rep < 0 and need_level == "fine":
                need_level = "upgrade"
        except Exception:
            pass

        # What cats should this position provide for our build?
        pos_cats = pos_cat_map.get(pos, [])
        target_cats_for_pos = [c for c in pos_cats if c in target_cats]

        # Archetype description
        if pos == "C" and "blk" in target_cats:
            archetype = "Rim protector with BLK + REB"
        elif pos == "C" and "reb" in target_cats:
            archetype = "High-volume rebounder with good FG%"
        elif pos == "PG" and "ast" in target_cats:
            archetype = "True point guard with high AST + low TO"
        elif pos == "PG":
            archetype = "Scoring guard with STL + 3PM"
        elif pos == "SG" and "tpm" in target_cats:
            archetype = "3-and-D wing with high 3PM + STL"
        elif pos == "SF":
            archetype = "Versatile wing contributing across categories"
        elif pos == "PF" and "blk" in target_cats:
            archetype = "Stretch four with BLK upside"
        else:
            archetype = f"Best available {pos} contributing to {', '.join(cat_labels.get(c, c) for c in target_cats_for_pos)}"

        needs.append(PositionNeed(
            position=pos,
            current_players=current_players[:5],
            current_best_z=round(best_z, 1),
            need_level=need_level,
            target_archetype=archetype,
            target_cats=target_cats_for_pos,
        ))

    needs.sort(key=lambda n: {"critical": 0, "upgrade": 1, "fine": 2, "surplus": 3}[n.need_level])
    return needs


def _find_extension_targets(
    my_roster_z: pd.DataFrame,
    target_cats: list[str],
) -> list[PlayerTarget]:
    """Find 3rd-year players worth extending that fit the build."""
    targets = []
    for _, row in my_roster_z.iterrows():
        if row.get("contract") != "3rd":
            continue
        name = row.get("name", "")
        salary = row.get("salary", 1)
        z = row.get("z_total", 0)
        age = int(row.get("age", 0))

        # Does this player contribute to target categories?
        fits = []
        for cat in target_cats:
            z_val = row.get(f"z_{cat}", 0)
            if z_val > 0.5:
                fits.append(cat)

        if not fits and z < 1:
            continue  # Doesn't fit build

        # Calculate extension cost
        ext_costs = [(i, salary + 3 * i) for i in range(1, 5)]
        best_ext = ""
        for years, cost in reversed(ext_costs):
            if z > 0 or age <= 24:
                best_ext = f"${cost:.0f}/yr for {years} years"
                break

        targets.append(PlayerTarget(
            name=name, team="(your roster)",
            why=f"Contributes {', '.join(fits)} at ${salary:.0f}. Young ({age}) with upside.",
            target_method="extend",
            estimated_cost=best_ext or f"${salary + 3:.0f}/yr for 1 year",
            fits_cats=fits, age=age, z_total=round(z, 1),
        ))

    targets.sort(key=lambda t: t.z_total, reverse=True)
    return targets


def _find_trade_targets(
    my_roster_z: pd.DataFrame,
    all_teams: dict,
    my_team_id: str,
    target_cats: list[str],
    pos_needs: list[PositionNeed],
) -> list[PlayerTarget]:
    """Find specific trade targets on other teams that fit the build."""
    targets = []
    need_positions = {n.position for n in pos_needs if n.need_level in ("critical", "upgrade")}

    for tid, tdata in all_teams.items():
        if tid == my_team_id:
            continue
        rz = tdata.get("roster_z")
        if rz is None or rz.empty:
            continue

        team_name = tdata["name"]

        for _, row in rz.iterrows():
            age = int(row.get("age", 30))
            z = row.get("z_total", 0)
            salary = row.get("salary", 0)
            name = row.get("name", "")

            # Want: young (<=26), productive (z>2), affordable (<$20)
            if age > 26 or z < 2 or salary > 20:
                continue

            # Fits target categories?
            fits = []
            for cat in target_cats:
                if row.get(f"z_{cat}", 0) > 0.5:
                    fits.append(cat)
            if len(fits) < 2:
                continue

            targets.append(PlayerTarget(
                name=name, team=team_name,
                why=f"Young ({age}), productive (z:{z:+.1f}), cheap (${salary:.0f}). Fits {', '.join(fits)}.",
                target_method="trade",
                estimated_cost=f"Trade package",
                fits_cats=fits, age=age, z_total=round(z, 1),
            ))

    targets.sort(key=lambda t: t.z_total, reverse=True)
    return targets[:15]


def _find_fa_auction_targets(
    all_rostered_z: pd.DataFrame,
    my_roster_z: pd.DataFrame,
    target_cats: list[str],
) -> list[PlayerTarget]:
    """Find players with expiring contracts who'll enter the FA auction."""
    targets = []
    my_names = set(my_roster_z["name"].str.lower()) if "name" in my_roster_z.columns else set()

    for _, row in all_rostered_z.iterrows():
        contract = str(row.get("contract", ""))
        name = row.get("name", "")

        if name.lower() in my_names:
            continue

        # Expiring: "2026" or "3rd" year
        is_expiring = contract in ("2026", "2025") or (contract == "3rd")
        if not is_expiring:
            continue

        z = row.get("z_total", 0)
        age = int(row.get("age", 30))
        salary = row.get("salary", 0)

        if z < 1:
            continue  # Not worth targeting

        fits = [cat for cat in target_cats if row.get(f"z_{cat}", 0) > 0.5]
        if not fits:
            continue

        targets.append(PlayerTarget(
            name=name, team=row.get("fantasy_team_name", ""),
            why=f"Expiring contract ({contract}). z:{z:+.1f}, age {age}. Will be in FA auction.",
            target_method="fa_auction",
            estimated_cost=f"~${max(1, z * 2 + 7):.0f} at auction",
            fits_cats=fits, age=age, z_total=round(z, 1),
        ))

    targets.sort(key=lambda t: t.z_total, reverse=True)
    return targets[:15]


def _find_rookie_targets(
    target_cats: list[str],
    pos_needs: list[PositionNeed],
) -> list[PlayerTarget]:
    """Define what archetypes to target in the rookie draft."""
    targets = []
    cat_labels = {"pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK",
                  "tpm": "3PM", "fg_pct": "FG%", "ft_pct": "FT%", "tov": "TO"}

    for need in pos_needs:
        if need.need_level not in ("critical", "upgrade"):
            continue

        cat_str = ", ".join(cat_labels.get(c, c) for c in need.target_cats)
        targets.append(PlayerTarget(
            name=f"Rookie {need.position} ({need.target_archetype})",
            team="Draft",
            why=f"Position {need.position} is {need.need_level}. Need {cat_str}.",
            target_method="rookie_draft",
            estimated_cost=f"Use Rd1 pick if elite prospect, Rd2 for depth",
            fits_cats=need.target_cats,
            age=20, z_total=0,
        ))

    return targets


def _find_sell_candidates(
    my_roster_z: pd.DataFrame,
    target_cats: list[str],
    punt_cats: list[str],
) -> list[PlayerTarget]:
    """Find players to trade away because they don't fit the build."""
    targets = []

    for _, row in my_roster_z.iterrows():
        name = row.get("name", "")
        z = row.get("z_total", 0)
        age = int(row.get("age", 30))
        salary = row.get("salary", 0)

        # Sell if: old (>30) with value, or doesn't fit target cats, or overpaid
        fits = [cat for cat in target_cats if row.get(f"z_{cat}", 0) > 0.5]
        punt_fits = [cat for cat in punt_cats if row.get(f"z_{cat}", 0) > 1.0]

        should_sell = False
        why = ""

        if age >= 31 and z > 2:
            should_sell = True
            why = f"Aging ({age}) with trade value (z:{z:+.1f}). Sell before decline."
        elif len(punt_fits) >= 2 and len(fits) <= 1:
            should_sell = True
            why = f"Produces mostly punted categories ({', '.join(punt_fits)}). Doesn't fit build."
        elif salary > 15 and z < 3:
            should_sell = True
            why = f"Overpaid (${salary:.0f}) for z:{z:+.1f}. Free up cap space."

        if should_sell:
            targets.append(PlayerTarget(
                name=name, team="(your roster)",
                why=why,
                target_method="trade",
                estimated_cost=f"Trade for picks/young players",
                fits_cats=fits, age=age, z_total=round(z, 1),
            ))

    targets.sort(key=lambda t: t.z_total, reverse=True)
    return targets


def _build_timeline(
    cat_build, extensions, trade_targets, sell_candidates,
    my_roster_z, salary_cap,
) -> tuple[list[str], list[str], str]:
    """Build actionable timeline."""
    immediate = []
    offseason = []

    # Immediate: extensions
    for ext in extensions:
        if ext.z_total > 3:
            immediate.append(f"EXTEND {ext.name} — {ext.estimated_cost} (elite value)")
        elif ext.z_total > 0:
            immediate.append(f"Consider extending {ext.name} — {ext.estimated_cost}")

    # Immediate: sell candidates
    for sell in sell_candidates[:3]:
        immediate.append(f"TRADE {sell.name} — {sell.why}")

    # Off-season
    target_cat_str = ", ".join(cat_build.target_5[:3]).upper()
    offseason.append(f"FA Auction: target players strong in {target_cat_str}")
    offseason.append(f"Rookie Draft: prioritize positions with critical needs")
    if trade_targets:
        top_target = trade_targets[0]
        offseason.append(f"Trade target: {top_target.name} from {top_target.team} (z:{top_target.z_total:+.1f})")

    # Cap space
    total_salary = my_roster_z["salary"].sum() if "salary" in my_roster_z.columns else 0
    cap_room = salary_cap - total_salary
    offseason.append(f"Cap room: ${cap_room:.0f} available for FA auction")

    # 2-year outlook
    young_core = my_roster_z[my_roster_z.get("age", pd.Series(dtype=float)).fillna(30) <= 25]
    young_z = young_core["z_total"].sum() if not young_core.empty and "z_total" in young_core.columns else 0
    outlook = (
        f"Young core (age <=25) currently produces z:{young_z:+.1f}. "
        f"With extensions, draft picks, and development, project z:+{young_z * 1.5:.0f} in 2 years. "
        f"Target: dominate {', '.join(cat_build.target_5[:3]).upper()} and compete for championship by 2028."
    )

    return immediate, offseason, outlook
