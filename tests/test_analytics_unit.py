"""
Unit tests for core analytics modules.

These test the algorithms directly without needing a running server.
Run with: pytest tests/test_analytics_unit.py -v
"""
import pytest
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# Z-SCORES
# ═══════════════════════════════════════════════════════════════

class TestZScores:
    def _make_df(self, n=20):
        """Create a sample stats DataFrame."""
        rng = np.random.RandomState(42)
        return pd.DataFrame({
            "name": [f"Player_{i}" for i in range(n)],
            "games_played": [50] * n,
            "minutes": [30.0] * n,
            "pts": rng.normal(15, 5, n).clip(0),
            "reb": rng.normal(5, 2, n).clip(0),
            "ast": rng.normal(3, 1.5, n).clip(0),
            "stl": rng.normal(1, 0.5, n).clip(0),
            "blk": rng.normal(0.5, 0.3, n).clip(0),
            "tpm": rng.normal(1.5, 0.8, n).clip(0),
            "fgm": rng.normal(5, 1.5, n).clip(0),
            "fga": rng.normal(12, 3, n).clip(0),
            "fg_pct": rng.normal(0.45, 0.05, n).clip(0.2, 0.7),
            "ftm": rng.normal(3, 1, n).clip(0),
            "fta": rng.normal(4, 1.2, n).clip(0),
            "ft_pct": rng.normal(0.8, 0.08, n).clip(0.4, 1.0),
            "tov": rng.normal(2, 0.8, n).clip(0),
        })

    def test_zscores_output_shape(self):
        from fantasy_engine.analytics.zscores import compute_zscores
        df = self._make_df()
        z = compute_zscores(df)
        assert len(z) == 20
        assert "z_total" in z.columns
        assert "z_pts" in z.columns
        assert "z_tov" in z.columns

    def test_zscores_mean_near_zero(self):
        """Z-scores should have approximately zero mean across the population."""
        from fantasy_engine.analytics.zscores import compute_zscores
        df = self._make_df(50)
        z = compute_zscores(df)
        assert abs(z["z_pts"].mean()) < 0.3
        assert abs(z["z_reb"].mean()) < 0.3

    def test_tov_inverted(self):
        """Higher turnovers should give lower (more negative) z-score."""
        from fantasy_engine.analytics.zscores import compute_zscores
        df = self._make_df()
        df.loc[0, "tov"] = 10.0  # Very high TO
        df.loc[1, "tov"] = 0.5   # Very low TO
        z = compute_zscores(df)
        assert z.loc[1, "z_tov"] > z.loc[0, "z_tov"]  # Low TO = higher z

    def test_punt_excludes_categories(self):
        """Punted categories should not affect z_total."""
        from fantasy_engine.analytics.zscores import compute_zscores, compute_punt_zscores
        df = self._make_df()
        z_full = compute_zscores(df)
        z_punt = compute_punt_zscores(df, ["ft_pct", "tov"])
        # Punted z_total should differ
        assert not np.allclose(z_full["z_total"].values, z_punt["z_total"].values)

    def test_fg_pct_volume_weighted(self):
        """Player with high FG% but low volume should rank lower than high volume."""
        from fantasy_engine.analytics.zscores import compute_zscores
        df = self._make_df()
        # Player 0: high FG% but few attempts
        df.loc[0, "fg_pct"] = 0.65
        df.loc[0, "fga"] = 3.0
        df.loc[0, "fgm"] = 1.95
        # Player 1: slightly lower FG% but many attempts
        df.loc[1, "fg_pct"] = 0.52
        df.loc[1, "fga"] = 18.0
        df.loc[1, "fgm"] = 9.36
        z = compute_zscores(df)
        assert z.loc[1, "z_fg_pct"] > z.loc[0, "z_fg_pct"]


# ═══════════════════════════════════════════════════════════════
# CATEGORY ANALYSIS
# ═══════════════════════════════════════════════════════════════

class TestCategoryAnalysis:
    def _make_z_df(self):
        return pd.DataFrame({
            "name": ["A", "B", "C"],
            "z_pts": [2.0, 1.0, -1.0],
            "z_reb": [-1.0, -2.0, -3.0],
            "z_ast": [0.5, 0.3, 0.2],
            "z_stl": [1.0, 0.5, -0.5],
            "z_blk": [3.0, 2.0, 1.0],
            "z_tpm": [-0.5, -1.0, -1.5],
            "z_fg_pct": [0.2, 0.1, -0.1],
            "z_ft_pct": [-2.0, -1.5, -1.0],
            "z_tov": [0.8, 0.4, 0.0],
            "z_total": [4.0, 0.3, -5.9],
        })

    def test_analyze_team(self):
        from fantasy_engine.analytics.category_analysis import analyze_team
        df = self._make_z_df()
        profile = analyze_team(df)
        assert len(profile.categories) == 9
        assert profile.strongest_cats[0] == "blk"  # Highest z-sum
        assert profile.weakest_cats[-1] in ("ft_pct", "reb", "tpm")

    def test_need_weights_weak_higher(self):
        from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights
        df = self._make_z_df()
        profile = analyze_team(df)
        weights = get_need_weights(profile)
        # Weak categories should have higher weights
        blk_weight = weights.get("blk", 1.0)  # strong
        reb_weight = weights.get("reb", 1.0)   # weak
        assert reb_weight > blk_weight

    def test_punt_zero_weight(self):
        from fantasy_engine.analytics.category_analysis import analyze_team, get_need_weights
        df = self._make_z_df()
        profile = analyze_team(df)
        weights = get_need_weights(profile, punt_cats=["ft_pct"])
        assert weights["ft_pct"] == 0.0


# ═══════════════════════════════════════════════════════════════
# VALUATION
# ═══════════════════════════════════════════════════════════════

class TestValuation:
    def test_age_curve(self):
        from fantasy_engine.analytics.valuation import age_curve_multiplier
        assert age_curve_multiplier(22) == 1.15
        assert age_curve_multiplier(26) == 1.10
        assert age_curve_multiplier(31) == 0.75
        assert age_curve_multiplier(36) == 0.35

    def test_compute_valuations(self):
        from fantasy_engine.analytics.valuation import compute_valuations
        df = pd.DataFrame({
            "name": ["Young Star", "Old Vet"],
            "z_total": [5.0, 5.0],
            "salary": [2.0, 20.0],
            "age": [23, 35],
            "years_remaining": [3, 1],
        })
        val = compute_valuations(df)
        assert "z_per_dollar" in val.columns
        assert "dynasty_value" in val.columns
        # Young cheap player should have better value
        young = val[val["name"] == "Young Star"].iloc[0]
        old = val[val["name"] == "Old Vet"].iloc[0]
        assert young["z_per_dollar"] > old["z_per_dollar"]
        assert young["dynasty_value"] > old["dynasty_value"]


# ═══════════════════════════════════════════════════════════════
# TRADE EVALUATOR
# ═══════════════════════════════════════════════════════════════

class TestTradeEval:
    def _make_roster(self):
        return pd.DataFrame({
            "name": ["Star Player", "Role Player", "Bench Guy", "Target Player"],
            "z_pts": [3.0, 0.5, -1.0, 2.0],
            "z_reb": [1.0, 0.3, -0.5, 1.5],
            "z_ast": [2.0, 0.2, -0.3, 0.5],
            "z_stl": [0.5, 0.8, -0.2, 1.0],
            "z_blk": [0.3, 0.1, -0.1, 2.0],
            "z_tpm": [1.5, 0.4, -0.8, 0.2],
            "z_fg_pct": [0.2, 0.1, 0.0, 0.5],
            "z_ft_pct": [-0.5, 0.3, 0.1, -1.0],
            "z_tov": [-1.0, 0.2, 0.5, -0.5],
            "z_total": [7.0, 2.9, -2.3, 6.2],
            "salary": [20.0, 5.0, 1.0, 15.0],
            "age": [28, 26, 23, 24],
            "years_remaining": [2, 3, 3, 3],
        })

    def test_evaluate_trade_returns_verdict(self):
        from fantasy_engine.analytics.trade_eval import evaluate_trade
        df = self._make_roster()
        ev = evaluate_trade(
            give_names=["Role Player"],
            receive_names=["Target Player"],
            roster_z_df=df,
        )
        assert ev.verdict in ("strong_accept", "accept", "slight_accept",
                               "slight_decline", "decline", "strong_decline")
        assert len(ev.cat_impact) == 9

    def test_better_trade_has_higher_score(self):
        from fantasy_engine.analytics.trade_eval import evaluate_trade
        df = self._make_roster()
        # Trade bench guy for target = clearly good
        ev1 = evaluate_trade(["Bench Guy"], ["Target Player"], df)
        # Trade star for role player = clearly bad
        ev2 = evaluate_trade(["Star Player"], ["Role Player"], df)
        assert ev1.combined_score > ev2.combined_score


# ═══════════════════════════════════════════════════════════════
# SCARCITY
# ═══════════════════════════════════════════════════════════════

class TestScarcity:
    def test_compute_scarcity(self):
        from fantasy_engine.analytics.advanced_metrics import compute_scarcity
        rng = np.random.RandomState(42)
        df = pd.DataFrame({
            "games_played": [50] * 100,
            "z_pts": rng.normal(0, 1, 100),
            "z_reb": rng.normal(0, 1, 100),
            "z_ast": rng.normal(0, 1, 100),
            "z_stl": rng.normal(0, 0.5, 100),  # Fewer above-avg = more scarce
            "z_blk": rng.normal(-0.5, 0.5, 100),  # Even fewer above avg
            "z_tpm": rng.normal(0, 1, 100),
            "z_fg_pct": rng.normal(0, 1, 100),
            "z_ft_pct": rng.normal(0, 1, 100),
            "z_tov": rng.normal(0, 1, 100),
        })
        scarcity = compute_scarcity(df)
        assert len(scarcity) == 9
        # Average scarcity should be ~1.0 (normalized)
        avg = np.mean([s.scarcity_index for s in scarcity])
        assert 0.8 < avg < 1.2


# ═══════════════════════════════════════════════════════════════
# TRADE HISTORY PARSER
# ═══════════════════════════════════════════════════════════════

class TestTradeHistory:
    def test_parse_trades_csv(self):
        import os
        csv_path = os.path.expanduser(
            "~/Downloads/Fantrax-Transaction-History-Trades-Black Mamba Snake Pit.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("Trades CSV not found")

        from fantasy_engine.ingestion.trade_history import parse_trades_csv
        trades = parse_trades_csv(csv_path)
        assert len(trades) > 0
        # Each trade should have 2 teams and movements
        for t in trades:
            assert len(t.teams) == 2
            assert len(t.movements) == 2

    def test_parse_draft_results(self):
        import os
        csv_path = os.path.expanduser(
            "~/Downloads/Fantrax-Draft-Results-Black Mamba Snake Pit.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("Draft CSV not found")

        from fantasy_engine.ingestion.trade_history import parse_draft_results_csv
        picks = parse_draft_results_csv(csv_path)
        assert len(picks) > 0
        assert picks[0].pick_number == 1
        assert picks[0].bid > 0


# ═══════════════════════════════════════════════════════════════
# WEEKLY OPTIMIZER
# ═══════════════════════════════════════════════════════════════

class TestWeeklyOptimizer:
    def _make_data(self):
        my_roster = pd.DataFrame({
            "name": ["PG1", "SG1", "SF1", "PF1", "C1", "G1", "F1", "Flx1", "Flx2", "Flx3", "Bench1", "Bench2"],
            "nba_team": ["LAL", "BOS", "MIL", "HOU", "DEN", "LAL", "BOS", "MIL", "HOU", "DEN", "LAL", "BOS"],
            "positions": ["PG", "SG", "SF", "PF", "C", "PG,SG", "SF,PF", "PG,SG,SF,PF,C", "PG,SG,SF,PF,C", "PG,SG,SF,PF,C", "PG", "SG"],
            "pts": [20, 18, 15, 12, 10, 8, 7, 6, 5, 4, 3, 2],
            "reb": [3, 2, 5, 8, 10, 2, 6, 4, 7, 3, 1, 1],
            "ast": [7, 3, 2, 1, 3, 5, 1, 2, 1, 1, 1, 0],
            "stl": [1.5, 1, 0.8, 0.5, 0.3, 1.2, 0.4, 0.3, 0.5, 0.2, 0.1, 0.1],
            "blk": [0.2, 0.3, 0.5, 1.0, 2.0, 0.1, 0.8, 0.3, 1.2, 0.5, 0.1, 0.1],
            "tpm": [2, 3, 1.5, 0.5, 0.2, 1, 0.3, 0.8, 0.1, 0.5, 0.3, 0.5],
            "tov": [3, 2, 1.5, 1, 1.5, 2, 0.8, 1, 0.5, 0.5, 0.5, 0.3],
            "fgm": [8, 7, 6, 5, 4, 3, 3, 2, 2, 2, 1, 1],
            "fga": [17, 15, 13, 11, 8, 7, 7, 5, 5, 5, 3, 3],
            "fg_pct": [0.47, 0.47, 0.46, 0.45, 0.50, 0.43, 0.43, 0.40, 0.40, 0.40, 0.33, 0.33],
            "ftm": [3, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0, 0],
            "fta": [4, 3, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0],
            "ft_pct": [0.75, 0.67, 1.0, 0.5, 0.5, 1.0, 1.0, 1.0, 0, 0, 0, 0],
            "games_played": [50] * 12,
            "consistency_rating": [0.8, 0.9, 0.7, 0.6, 0.85, 0.75, 0.65, 0.5, 0.5, 0.5, 0.3, 0.3],
            "z_pts": [3, 2, 1, 0, -1, -1, -2, -2, -3, -3, -4, -4],
            "z_reb": [-1, -2, 0, 2, 3, -2, 1, 0, 2, -1, -3, -3],
            "z_ast": [3, 0, -1, -2, 0, 2, -2, -1, -2, -2, -2, -3],
            "z_stl": [2, 1, 0.5, 0, -0.5, 1, -0.5, -1, 0, -1, -2, -2],
            "z_blk": [-1, -0.5, 0, 1, 3, -1, 0.5, -0.5, 1.5, 0, -1, -1],
            "z_tpm": [1, 2, 0.5, -1, -2, 0, -1, -0.5, -2, -0.5, -1, -0.5],
            "z_fg_pct": [0.5, 0.5, 0.3, 0.2, 1.0, -0.3, -0.3, -0.5, -0.5, -0.5, -1, -1],
            "z_ft_pct": [-0.5, -1, 0.5, -1, -1, 0.5, 0.5, 0.5, -2, -2, 0, 0],
            "z_tov": [-1, 0, 0.5, 1, 0.5, 0, 1, 0.5, 1.5, 1.5, 1.5, 2],
            "z_total": [6, 2, 1.8, 0.2, 3, -0.8, -2.3, -4.5, -4.5, -8.5, -11.5, -12.5],
        })
        opp_roster = my_roster.copy()  # Simplified: same roster for opponent
        opp_roster["nba_team"] = ["CHI", "CLE", "DAL", "MIA", "OKC", "CHI", "CLE", "DAL", "MIA", "OKC", "CHI", "CLE"]

        daily = {
            "2026-03-02": {"LAL", "BOS", "CHI", "CLE"},
            "2026-03-03": {"MIL", "HOU", "DEN", "DAL", "MIA", "OKC"},
            "2026-03-04": {"LAL", "BOS", "MIL", "CHI", "CLE", "DAL"},
            "2026-03-05": {"HOU", "DEN", "MIA", "OKC"},
        }
        return my_roster, opp_roster, daily

    def test_optimizer_returns_plan(self):
        from fantasy_engine.analytics.weekly_optimizer import WeeklyOptimizer
        my, opp, daily = self._make_data()
        opt = WeeklyOptimizer(my, opp, daily, "Test Opponent")
        plan = opt.optimize()
        assert plan.opponent == "Test Opponent"
        assert len(plan.categories) == 9
        assert len(plan.daily_lineups) == 4  # 4 days
        assert plan.expected_wins >= 0

    def test_daily_lineup_respects_slots(self):
        from fantasy_engine.analytics.weekly_optimizer import WeeklyOptimizer
        my, opp, daily = self._make_data()
        opt = WeeklyOptimizer(my, opp, daily)
        plan = opt.optimize()
        for day, lineup in plan.daily_lineups.items():
            assert len(lineup.active) <= 10

    def test_concede_vs_target(self):
        from fantasy_engine.analytics.weekly_optimizer import WeeklyOptimizer
        my, opp, daily = self._make_data()
        opt = WeeklyOptimizer(my, opp, daily)
        plan = opt.optimize()
        # Should have both target and concede
        assert len(plan.target_cats) > 0
        assert len(plan.target_cats) + len(plan.concede_cats) == 9
