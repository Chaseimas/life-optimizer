"""$400/day target mathematics: hand-checked identities and honest edges."""

from __future__ import annotations

import numpy as np
import pytest

from trading_bot.research import target_math as tm


def test_required_daily_return():
    assert tm.required_daily_return_frac(400, 100_000) == pytest.approx(0.004)
    with pytest.raises(ValueError):
        tm.required_daily_return_frac(400, 0)


def test_implied_sharpe_hand_computed():
    # 0.4%/day mean over 1% daily vol -> 0.4 * sqrt(365) ~= 7.64 annualized.
    assert tm.implied_annual_sharpe(0.004, 0.01) == pytest.approx(0.4 * np.sqrt(365))
    assert tm.implied_annual_sharpe(0.004, 0.02) == pytest.approx(0.2 * np.sqrt(365))
    with pytest.raises(ValueError):
        tm.implied_annual_sharpe(0.004, 0)


def test_required_expectancy():
    r = tm.required_expectancy(400, trades_per_day=2, risk_per_trade=0.005,
                               account=100_000)
    assert r["expectancy_usd"] == pytest.approx(200.0)
    assert r["risk_usd_per_trade"] == pytest.approx(500.0)
    assert r["expectancy_R"] == pytest.approx(0.4)


def test_expectancy_from_profile():
    assert tm.expectancy_from_profile(0.5, 100.0, -50.0) == pytest.approx(25.0)
    assert tm.expectancy_from_profile(0.28, 537.0, -234.0) == pytest.approx(
        0.28 * 537 - 0.72 * 234)
    with pytest.raises(ValueError):
        tm.expectancy_from_profile(0.5, 100.0, 50.0)  # losses must be negative


def test_required_capital_scales_linearly():
    assert tm.required_capital(400, measured_daily_pnl=200,
                               measured_account=100_000) == pytest.approx(200_000)
    assert tm.required_capital(400, measured_daily_pnl=100,
                               measured_account=100_000) == pytest.approx(400_000)
    # No amount of capital fixes a losing stream:
    assert tm.required_capital(400, measured_daily_pnl=-50,
                               measured_account=100_000) is None


def test_trades_for_significance():
    # mean $120, std $450, one comparison, one-sided 5%: (1.645*450/120)^2 ~ 38
    n1 = tm.trades_for_significance(120, 450)
    assert n1 == pytest.approx(38.0, rel=0.02)
    # Bonferroni across 25 cells raises the bar sharply:
    n25 = tm.trades_for_significance(120, 450, n_comparisons=25)
    assert n25 > 2.5 * n1
    assert tm.trades_for_significance(-5, 450) is None


def test_horizon_outcomes_deterministic_and_honest():
    steady = tm.horizon_outcomes([400.0] * 30, horizons=(20, 60), n_sims=500)
    for h in steady:
        assert h.prob_loss == 0.0
        assert h.prob_avg_ge_target == 1.0
    losing = tm.horizon_outcomes([-10.0] * 30, horizons=(20,), n_sims=500)
    assert losing[0].prob_loss == 1.0
    a = tm.horizon_outcomes(list(np.random.default_rng(1).normal(50, 700, 60)),
                            horizons=(20, 60), n_sims=1000, seed=7)
    b = tm.horizon_outcomes(list(np.random.default_rng(1).normal(50, 700, 60)),
                            horizons=(20, 60), n_sims=1000, seed=7)
    assert [x.as_dict() for x in a] == [x.as_dict() for x in b]
    with pytest.raises(ValueError):
        tm.horizon_outcomes([1.0] * 5)


def test_requirements_report_renders():
    text = tm.format_target_requirements()
    assert "Sharpe" in text
    assert "no known fund sustains this" in text     # the 0.5%-vol row
    assert "trades/day" in text
