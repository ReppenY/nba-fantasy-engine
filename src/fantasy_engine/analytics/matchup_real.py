"""
Real opponent matchup analysis.

Given the actual matchup schedule, predicts category-by-category
outcomes against the real opponent. Also provides per-opponent
category focus recommendations for every team in the league.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from scipy.stats import norm

from fantasy_engine.analytics.zscores import ALL_CATS, COUNTING_CATS, NEGATIVE_CATS


@dataclass
class CategoryMatchup:
    category: str
    my_z: float
    opp_z: float
    diff: float
    win_prob: float
    recommendation: str  # "target", "concede", "swing"


@dataclass
class RealMatchupPrediction:
    period: int
    opponent_name: str
    opponent_id: str
    categories: list[CategoryMatchup]
    expected_wins: float
    win_probability: float
    target_cats: list[str]     # Categories to focus on
    concede_cats: list[str]    # Categories to give up
    swing_cats: list[str]      # 50/50 — could go either way
    my_total_z: float
    opp_total_z: float


@dataclass
class OpponentScouting:
    """Category focus analysis for a specific opponent."""
    team_name: str
    team_id: str
    period: int | None
    team_total_z: float
    categories: list[CategoryMatchup]
    strategy: str              # Summary recommendation
    target_cats: list[str]
    concede_cats: list[str]
    swing_cats: list[str]
    my_advantages: int         # Categories I'm likely to win
    my_disadvantages: int


def predict_real_matchup(
    my_roster_z: pd.DataFrame,
    opp_roster_z: pd.DataFrame,
    opponent_name: str,
    opponent_id: str = "",
    period: int = 0,
) -> RealMatchupPrediction:
    """
    Predict matchup against a real opponent using z-score comparison.

    For each category, compares the sum of z-scores between teams.
    Uses normal approximation to estimate win probability.
    Adjusts variance by team consistency if available.
    """
    cats = []
    total_expected_wins = 0.0

    # Adjust for schedule: weight by games_this_week if available
    my_sched_factor = 1.0
    opp_sched_factor = 1.0
    if "games_this_week" in my_roster_z.columns:
        avg_games = my_roster_z["games_this_week"].mean()
        my_sched_factor = avg_games / 4.0 if avg_games > 0 else 1.0
    if "games_this_week" in opp_roster_z.columns:
        avg_games = opp_roster_z["games_this_week"].mean()
        opp_sched_factor = avg_games / 4.0 if avg_games > 0 else 1.0

    # Team-level consistency affects variance
    my_consistency = my_roster_z["consistency_rating"].mean() if "consistency_rating" in my_roster_z.columns else 0.5
    opp_consistency = opp_roster_z["consistency_rating"].mean() if "consistency_rating" in opp_roster_z.columns else 0.5

    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        my_z = (my_roster_z[z_col].sum() if z_col in my_roster_z.columns else 0) * my_sched_factor
        opp_z = (opp_roster_z[z_col].sum() if z_col in opp_roster_z.columns else 0) * opp_sched_factor
        diff = my_z - opp_z

        # Std adjusted by consistency: less consistent teams = more variance
        base_std = 3.0
        std_diff = base_std * (2.0 - (my_consistency + opp_consistency) / 2)
        if cat in NEGATIVE_CATS:
            # For TO, higher z = fewer turnovers = better
            # The z-score is already inverted, so positive diff = I'm better
            win_prob = 1 - norm.cdf(0, loc=diff, scale=std_diff) if std_diff > 0 else 0.5
        else:
            win_prob = 1 - norm.cdf(0, loc=diff, scale=std_diff) if std_diff > 0 else 0.5

        win_prob = round(float(win_prob), 3)

        if win_prob >= 0.65:
            rec = "target"
        elif win_prob <= 0.35:
            rec = "concede"
        else:
            rec = "swing"

        total_expected_wins += win_prob
        cats.append(CategoryMatchup(
            category=cat,
            my_z=round(my_z, 2),
            opp_z=round(opp_z, 2),
            diff=round(diff, 2),
            win_prob=win_prob,
            recommendation=rec,
        ))

    target = [c.category for c in cats if c.recommendation == "target"]
    concede = [c.category for c in cats if c.recommendation == "concede"]
    swing = [c.category for c in cats if c.recommendation == "swing"]

    # Overall win probability: need 5+ cats to win
    # Use binomial approximation
    from scipy.stats import binom
    cat_probs = [c.win_prob for c in cats]
    # Monte Carlo for accuracy
    rng = np.random.default_rng(42)
    wins = 0
    n_sims = 10000
    for _ in range(n_sims):
        cat_wins = sum(rng.random() < p for p in cat_probs)
        if cat_wins >= 5:
            wins += 1
    overall_win_prob = round(wins / n_sims, 3)

    return RealMatchupPrediction(
        period=period,
        opponent_name=opponent_name,
        opponent_id=opponent_id,
        categories=cats,
        expected_wins=round(total_expected_wins, 1),
        win_probability=overall_win_prob,
        target_cats=target,
        concede_cats=concede,
        swing_cats=swing,
        my_total_z=round(my_roster_z["z_total"].sum(), 2) if "z_total" in my_roster_z.columns else 0,
        opp_total_z=round(opp_roster_z["z_total"].sum(), 2) if "z_total" in opp_roster_z.columns else 0,
    )


def scout_all_opponents(
    my_roster_z: pd.DataFrame,
    all_teams: dict,
    my_team_id: str,
    matchup_schedule: list | None = None,
) -> list[OpponentScouting]:
    """
    Generate category focus analysis for every opponent in the league.

    Shows which categories to target and concede against each team.
    """
    scouting = []

    for team_id, team_data in all_teams.items():
        if team_id == my_team_id:
            continue

        opp_z = team_data.get("roster_z")
        if opp_z is None or opp_z.empty:
            continue

        opp_name = team_data["name"]

        # Find period for this matchup
        period = None
        if matchup_schedule:
            for m in matchup_schedule:
                mid = m.away_id if hasattr(m, 'away_id') else m.get("opponent_id", "")
                if hasattr(m, 'away_id'):
                    if m.away_id == team_id or m.home_id == team_id:
                        if m.away_id == my_team_id or m.home_id == my_team_id:
                            period = m.period
                            break

        # Predict matchup
        pred = predict_real_matchup(my_roster_z, opp_z, opp_name, team_id, period or 0)

        # Strategy summary
        adv = len(pred.target_cats)
        disadv = len(pred.concede_cats)
        if adv >= 5:
            strategy = f"Dominant matchup. Target {adv} categories."
        elif adv >= 3 and disadv <= 3:
            strategy = f"Favorable. Focus on swing cats: {', '.join(pred.swing_cats)}"
        elif adv < 3 and disadv >= 5:
            strategy = f"Tough matchup. Minimize losses, target: {', '.join(pred.target_cats)}"
        else:
            strategy = f"Even matchup. Swing categories will decide it: {', '.join(pred.swing_cats)}"

        scouting.append(OpponentScouting(
            team_name=opp_name,
            team_id=team_id,
            period=period,
            team_total_z=round(opp_z["z_total"].sum(), 2) if "z_total" in opp_z.columns else 0,
            categories=pred.categories,
            strategy=strategy,
            target_cats=pred.target_cats,
            concede_cats=pred.concede_cats,
            swing_cats=pred.swing_cats,
            my_advantages=adv,
            my_disadvantages=disadv,
        ))

    scouting.sort(key=lambda s: s.my_advantages, reverse=True)
    return scouting
