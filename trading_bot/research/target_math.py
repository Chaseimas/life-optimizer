"""$400/day target mathematics (Pass 4).

Pure arithmetic connecting the dollar target to the statistics a strategy
must actually exhibit. Nothing here is a forecast; it is the yardstick
against which measured results are judged — and it cuts both ways: it says
what the target REQUIRES, and it converts measured performance into the
capital that target would need.

Key identity to keep in view: $400/day average on $100k is a 0.40% average
daily return. At an (excellent) 1.0% daily P&L volatility that is an
annualized Sharpe of ~7.6; at 2.0% daily volatility, ~3.8. World-class
funds live near 2; retail strategies with defensible evidence rarely clear
1.5. The dollar target is therefore, first and foremost, a SHARPE claim —
and the honest routes to it are more capital, not more leverage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

TRADING_DAYS_CRYPTO = 365
TRADING_DAYS_FUTURES = 252


def required_daily_return_frac(target_per_day: float, account: float) -> float:
    if account <= 0:
        raise ValueError("account must be > 0")
    return target_per_day / account


def implied_annual_sharpe(daily_mean_frac: float, daily_vol_frac: float,
                          periods_per_year: int = TRADING_DAYS_CRYPTO) -> float:
    """The Sharpe ratio a return stream with this mean and volatility has —
    i.e. what the target implicitly claims, given a volatility level."""
    if daily_vol_frac <= 0:
        raise ValueError("daily_vol_frac must be > 0")
    return daily_mean_frac / daily_vol_frac * np.sqrt(periods_per_year)


def required_expectancy(target_per_day: float, trades_per_day: float,
                        risk_per_trade: float, account: float) -> dict:
    """Per-trade expectancy needed, in dollars and in R (risk units)."""
    if trades_per_day <= 0 or risk_per_trade <= 0:
        raise ValueError("trades_per_day and risk_per_trade must be > 0")
    per_trade_usd = target_per_day / trades_per_day
    risk_usd = account * risk_per_trade
    return {
        "expectancy_usd": per_trade_usd,
        "risk_usd_per_trade": risk_usd,
        "expectancy_R": per_trade_usd / risk_usd,
    }


def expectancy_from_profile(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Expectancy per trade from a win-rate / payoff profile. avg_loss is a
    NEGATIVE number (a loss)."""
    if not (0 <= win_rate <= 1):
        raise ValueError("win_rate must be in [0, 1]")
    if avg_loss > 0:
        raise ValueError("avg_loss must be <= 0 (losses are negative)")
    return win_rate * avg_win + (1 - win_rate) * avg_loss


def required_capital(target_per_day: float, measured_daily_pnl: float,
                     measured_account: float) -> float | None:
    """Capital needed for the target, scaling the MEASURED daily P&L
    linearly with account size (valid while exposure caps don't bind and
    market impact is negligible). None if the measured stream loses money —
    no amount of capital turns a negative edge positive."""
    if measured_daily_pnl <= 0:
        return None
    return measured_account * target_per_day / measured_daily_pnl


def trades_for_significance(expectancy: float, per_trade_std: float,
                            alpha: float = 0.05, n_comparisons: int = 1) -> float | None:
    """Trades needed for a one-sided t-test of positive expectancy at
    ``alpha``, Bonferroni-corrected for the number of strategy/market cells
    examined. None if expectancy <= 0. This is the price of evidence: every
    extra strategy family tested on the same data raises n_comparisons."""
    if expectancy <= 0:
        return None
    if per_trade_std <= 0:
        raise ValueError("per_trade_std must be > 0")
    z = norm.ppf(1 - alpha / n_comparisons)
    return float((z * per_trade_std / expectancy) ** 2)


@dataclass(frozen=True)
class HorizonOutcome:
    horizon_days: int
    mean_total: float
    p5_total: float
    p50_total: float
    p95_total: float
    prob_loss: float                 # P(total <= 0 over the horizon)
    prob_avg_ge_target: float        # P(average daily P&L >= target)

    def as_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "mean_total": round(self.mean_total, 2),
            "p5_total": round(self.p5_total, 2),
            "p50_total": round(self.p50_total, 2),
            "p95_total": round(self.p95_total, 2),
            "prob_loss": round(self.prob_loss, 4),
            "prob_avg_ge_target": round(self.prob_avg_ge_target, 4),
        }


def horizon_outcomes(
    daily_pnl_sample,
    horizons=(20, 60, 126, 252),
    *,
    target_per_day: float = 400.0,
    n_sims: int = 10_000,
    seed: int = 42,
) -> list[HorizonOutcome]:
    """Bootstrap the observed daily-P&L distribution over longer horizons.

    i.i.d. resampling — real P&L autocorrelates and regimes persist, so tail
    risk here is an UNDERESTIMATE. Stated, not hidden."""
    sample = np.asarray(list(daily_pnl_sample), dtype=float)
    sample = sample[~np.isnan(sample)]
    if len(sample) < 10:
        raise ValueError("need at least 10 daily observations")
    rng = np.random.default_rng(seed)
    out = []
    for h in horizons:
        sims = rng.choice(sample, size=(n_sims, h), replace=True)
        totals = sims.sum(axis=1)
        out.append(HorizonOutcome(
            horizon_days=h,
            mean_total=float(totals.mean()),
            p5_total=float(np.percentile(totals, 5)),
            p50_total=float(np.percentile(totals, 50)),
            p95_total=float(np.percentile(totals, 95)),
            prob_loss=float((totals <= 0).mean()),
            prob_avg_ge_target=float((totals >= target_per_day * h).mean()),
        ))
    return out


def format_target_requirements(account: float = 100_000.0,
                               target: float = 400.0) -> str:
    """The requirements table: what $target/day on $account demands."""
    frac = required_daily_return_frac(target, account)
    lines = [
        "=" * 76,
        f"WHAT ${target:,.0f}/DAY ON ${account:,.0f} REQUIRES",
        "=" * 76,
        f"average daily return: {frac:.2%}  "
        f"(~{(1 + frac) ** TRADING_DAYS_CRYPTO - 1:.0%} compounded/365d)",
        "",
        "Implied annualized Sharpe at a given daily P&L volatility:",
    ]
    for vol in (0.005, 0.01, 0.02, 0.04):
        s = implied_annual_sharpe(frac, vol)
        note = ("(no known fund sustains this)" if s > 6 else
                "(world-class, rare)" if s > 3 else
                "(elite)" if s > 2 else "(excellent)")
        lines.append(f"  daily vol {vol:.1%} -> Sharpe {s:4.1f}  {note}")
    lines += ["", "Required per-trade expectancy (in R = risk units) by activity:"]
    for tpd in (1, 2, 4, 8):
        for rpt in (0.0025, 0.005, 0.01):
            r = required_expectancy(target, tpd, rpt, account)
            lines.append(
                f"  {tpd} trades/day @ {rpt:.2%} risk (${r['risk_usd_per_trade']:,.0f}):"
                f" need {r['expectancy_R']:+.2f}R (${r['expectancy_usd']:,.0f}) per trade"
            )
    lines += [
        "",
        "Context: a GOOD validated systematic strategy sustains +0.05R to "
        "+0.15R per trade after costs. The table above shows the target needs "
        "+0.10R to +1.60R depending on activity and risk — the honest levers "
        "are capital and (validated) trade frequency, never optimism.",
        "=" * 76,
    ]
    return "\n".join(lines)
