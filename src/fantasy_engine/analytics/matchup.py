"""
Matchup predictor for H2H 9-Cat leagues.

Two approaches:
1. Analytical: Normal distribution approximation (fast, good for counting stats)
2. Monte Carlo: Simulation-based (accurate for percentage categories)

The Monte Carlo approach is preferred because FG% and FT% are ratios
(total FGM / total FGA), not simple sums.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from scipy.stats import norm

from fantasy_engine.analytics.zscores import ALL_CATS, COUNTING_CATS, NEGATIVE_CATS


# Stats needed for simulation (per-game averages and their variance)
SIM_STATS = ["pts", "reb", "ast", "stl", "blk", "tpm", "fgm", "fga", "ftm", "fta", "tov"]


@dataclass
class MatchupPrediction:
    opponent_name: str
    category_probs: dict[str, float] = field(default_factory=dict)
    expected_cats_won: float = 0.0
    win_probability: float = 0.0
    blowout_probability: float = 0.0
    loss_probability: float = 0.0
    swing_categories: list[str] = field(default_factory=list)
    lock_categories: list[str] = field(default_factory=list)
    my_projections: dict[str, float] = field(default_factory=dict)
    opp_projections: dict[str, float] = field(default_factory=dict)


def predict_matchup_analytical(
    my_team_df: pd.DataFrame,
    opp_team_df: pd.DataFrame,
    my_games: dict[str, int] | None = None,
    opp_games: dict[str, int] | None = None,
) -> MatchupPrediction:
    """
    Predict matchup using normal distribution approximation.

    For each counting stat category:
        my_total ~ N(sum(player_avg * games), sum(player_var * games))
        P(win) = P(my_total > opp_total)

    For TO: P(win) = P(my_total < opp_total) (inverted)

    For FG%/FT%: Uses weighted average approximation (less accurate than MC).

    Args:
        my_team_df: My active roster with per-game stats.
        opp_team_df: Opponent's active roster with per-game stats.
        my_games: Dict of player name -> games this week. If None, assumes 4.
        opp_games: Same for opponent.
    """
    default_games = 4

    cat_probs = {}
    my_proj = {}
    opp_proj = {}

    for cat in COUNTING_CATS + NEGATIVE_CATS:
        my_mean = _team_weekly_mean(my_team_df, cat, my_games, default_games)
        opp_mean = _team_weekly_mean(opp_team_df, cat, opp_games, default_games)
        # Variance: approximate as 40% of mean (reasonable for NBA box scores)
        my_var = max(my_mean * 0.4, 0.1)
        opp_var = max(opp_mean * 0.4, 0.1)

        diff_mean = my_mean - opp_mean
        diff_std = np.sqrt(my_var + opp_var)

        my_proj[cat] = round(my_mean, 1)
        opp_proj[cat] = round(opp_mean, 1)

        if diff_std > 0:
            if cat in NEGATIVE_CATS:
                # Lower is better for TO
                p_win = norm.cdf(0, loc=diff_mean, scale=diff_std)
            else:
                p_win = 1 - norm.cdf(0, loc=diff_mean, scale=diff_std)
        else:
            p_win = 0.5

        cat_probs[cat] = round(float(p_win), 3)

    # FG% and FT%: use volume-weighted approach
    for pct_cat, makes_col, attempts_col in [("fg_pct", "fgm", "fga"), ("ft_pct", "ftm", "fta")]:
        my_makes = _team_weekly_mean(my_team_df, makes_col, my_games, default_games)
        my_att = _team_weekly_mean(my_team_df, attempts_col, my_games, default_games)
        opp_makes = _team_weekly_mean(opp_team_df, makes_col, opp_games, default_games)
        opp_att = _team_weekly_mean(opp_team_df, attempts_col, opp_games, default_games)

        my_pct = my_makes / my_att if my_att > 0 else 0
        opp_pct = opp_makes / opp_att if opp_att > 0 else 0
        my_proj[pct_cat] = round(my_pct, 3)
        opp_proj[pct_cat] = round(opp_pct, 3)

        # Approximate variance using binomial: var(p) ~ p*(1-p)/n
        my_var_pct = (my_pct * (1 - my_pct)) / max(my_att, 1)
        opp_var_pct = (opp_pct * (1 - opp_pct)) / max(opp_att, 1)

        diff_mean = my_pct - opp_pct
        diff_std = np.sqrt(my_var_pct + opp_var_pct) if (my_var_pct + opp_var_pct) > 0 else 0.01

        p_win = 1 - norm.cdf(0, loc=diff_mean, scale=diff_std) if diff_std > 0 else 0.5
        cat_probs[pct_cat] = round(float(p_win), 3)

    return _build_prediction(cat_probs, my_proj, opp_proj, "Opponent")


def predict_matchup_monte_carlo(
    my_team_df: pd.DataFrame,
    opp_team_df: pd.DataFrame,
    my_games: dict[str, int] | None = None,
    opp_games: dict[str, int] | None = None,
    n_simulations: int = 10000,
) -> MatchupPrediction:
    """
    Predict matchup using Monte Carlo simulation.

    More accurate than analytical for FG%/FT% because it simulates
    FGM and FGA separately, then computes the ratio.

    For each simulation:
    1. For each player, sample stats from N(mean, std) * games
    2. Sum across active roster
    3. FG% = total FGM / total FGA (correct ratio!)
    4. Compare team totals, count category wins
    """
    default_games = 4
    rng = np.random.default_rng(42)

    cat_wins = {cat: 0 for cat in ALL_CATS}
    matchup_wins = 0
    blowout_wins = 0

    for _ in range(n_simulations):
        my_totals = _simulate_team_week(my_team_df, my_games, default_games, rng)
        opp_totals = _simulate_team_week(opp_team_df, opp_games, default_games, rng)

        cats_won = 0
        for cat in ALL_CATS:
            my_val = my_totals.get(cat, 0)
            opp_val = opp_totals.get(cat, 0)

            if cat in NEGATIVE_CATS:
                won = my_val < opp_val  # Lower TO is better
            else:
                won = my_val > opp_val

            if won:
                cat_wins[cat] += 1
                cats_won += 1

        if cats_won >= 5:
            matchup_wins += 1
        if cats_won >= 7:
            blowout_wins += 1

    cat_probs = {cat: round(wins / n_simulations, 3) for cat, wins in cat_wins.items()}

    # Projections (use means)
    my_proj = _team_mean_projections(my_team_df, my_games, default_games)
    opp_proj = _team_mean_projections(opp_team_df, opp_games, default_games)

    pred = _build_prediction(cat_probs, my_proj, opp_proj, "Opponent")
    pred.win_probability = round(matchup_wins / n_simulations, 3)
    pred.blowout_probability = round(blowout_wins / n_simulations, 3)
    pred.loss_probability = round(1 - matchup_wins / n_simulations, 3)
    return pred


def _team_weekly_mean(
    team_df: pd.DataFrame, stat: str,
    games_map: dict[str, int] | None, default: int
) -> float:
    """Sum of (player_avg * games_this_week) for a stat."""
    total = 0.0
    for _, row in team_df.iterrows():
        name = row.get("name", "")
        games = games_map.get(name, default) if games_map else default
        total += row.get(stat, 0) * games
    return total


def _simulate_team_week(
    team_df: pd.DataFrame,
    games_map: dict[str, int] | None,
    default_games: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    """Simulate one week of stats for a team."""
    totals = {s: 0.0 for s in SIM_STATS}

    for _, row in team_df.iterrows():
        name = row.get("name", "")
        games = games_map.get(name, default_games) if games_map else default_games

        for stat in SIM_STATS:
            mean = row.get(stat, 0)
            if mean <= 0:
                continue
            # Per-game std ≈ 60% of mean (NBA game-to-game variance)
            std = mean * 0.6
            # Weekly total = sum of `games` independent draws
            weekly = sum(max(0, rng.normal(mean, std)) for _ in range(games))
            totals[stat] += weekly

    # Compute percentage categories from makes/attempts
    totals["fg_pct"] = totals["fgm"] / totals["fga"] if totals["fga"] > 0 else 0
    totals["ft_pct"] = totals["ftm"] / totals["fta"] if totals["fta"] > 0 else 0

    return totals


def _team_mean_projections(
    team_df: pd.DataFrame,
    games_map: dict[str, int] | None,
    default_games: int,
) -> dict[str, float]:
    """Compute mean weekly projections for display."""
    proj = {}
    for cat in COUNTING_CATS + NEGATIVE_CATS:
        proj[cat] = round(_team_weekly_mean(team_df, cat, games_map, default_games), 1)

    # Percentage projections
    for pct, makes, att in [("fg_pct", "fgm", "fga"), ("ft_pct", "ftm", "fta")]:
        total_makes = _team_weekly_mean(team_df, makes, games_map, default_games)
        total_att = _team_weekly_mean(team_df, att, games_map, default_games)
        proj[pct] = round(total_makes / total_att, 3) if total_att > 0 else 0
    return proj


def _build_prediction(
    cat_probs: dict, my_proj: dict, opp_proj: dict, opp_name: str
) -> MatchupPrediction:
    """Build MatchupPrediction from category probabilities."""
    expected = sum(cat_probs.values())
    win_prob = sum(1 for p in cat_probs.values() if p > 0.5) / len(cat_probs)

    swing = [c for c, p in cat_probs.items() if 0.35 <= p <= 0.65]
    locks = [c for c, p in cat_probs.items() if p > 0.8 or p < 0.2]

    return MatchupPrediction(
        opponent_name=opp_name,
        category_probs=cat_probs,
        expected_cats_won=round(expected, 2),
        win_probability=round(win_prob, 3),
        blowout_probability=0.0,
        loss_probability=round(1 - win_prob, 3),
        swing_categories=swing,
        lock_categories=locks,
        my_projections=my_proj,
        opp_projections=opp_proj,
    )


def format_matchup_report(pred: MatchupPrediction) -> str:
    """Format matchup prediction as a readable report."""
    lines = []
    lines.append("=" * 90)
    lines.append(f"MATCHUP PREDICTION vs {pred.opponent_name}")
    lines.append("=" * 90)
    lines.append("")
    lines.append(
        f"  {'Category':>8s}  {'My Proj':>8s}  {'Opp Proj':>8s}  "
        f"{'Win %':>6s}  {'Outlook':12s}"
    )
    lines.append("  " + "-" * 70)

    for cat in ALL_CATS:
        p = pred.category_probs.get(cat, 0.5)
        my_val = pred.my_projections.get(cat, 0)
        opp_val = pred.opp_projections.get(cat, 0)

        if p >= 0.7:
            outlook = "LIKELY WIN"
        elif p >= 0.55:
            outlook = "Lean win"
        elif p >= 0.45:
            outlook = "TOSS-UP"
        elif p >= 0.3:
            outlook = "Lean loss"
        else:
            outlook = "LIKELY LOSS"

        # Format value
        if cat in ("fg_pct", "ft_pct"):
            my_str = f"{my_val:.3f}"
            opp_str = f"{opp_val:.3f}"
        else:
            my_str = f"{my_val:.1f}"
            opp_str = f"{opp_val:.1f}"

        lines.append(
            f"  {cat:>8s}  {my_str:>8s}  {opp_str:>8s}  "
            f"{p * 100:5.1f}%  {outlook}"
        )

    lines.append("")
    lines.append(f"  Expected categories won: {pred.expected_cats_won:.1f} / 9")
    lines.append(f"  Win probability: {pred.win_probability * 100:.1f}%")
    if pred.blowout_probability > 0:
        lines.append(f"  Blowout (7+ cats): {pred.blowout_probability * 100:.1f}%")
    lines.append(f"  Loss probability: {pred.loss_probability * 100:.1f}%")

    if pred.swing_categories:
        lines.append(f"\n  Swing categories (toss-up): {', '.join(pred.swing_categories)}")
    if pred.lock_categories:
        lines.append(f"  Lock categories (>80% either way): {', '.join(pred.lock_categories)}")

    return "\n".join(lines)
