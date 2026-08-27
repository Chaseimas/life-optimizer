"""Rolling walk-forward testing (Phases 8-9).

For each rolling window:
1. Every parameter set in the grid is backtested on the TRAIN slice.
2. The best set BY TRAIN METRIC is chosen (the test slice has no vote).
3. That one set is backtested ONCE on the TEST slice.
4. All test-slice results are aggregated into a single out-of-sample record.

Honesty mechanics:
* Selection uses train data only; each test slice is evaluated exactly once.
* Test slices never overlap (step defaults to the test size) and an optional
  embargo gap separates train from test.
* Indicators warm up on bars BEFORE the evaluation slice via a signal gate:
  the strategy sees the warmup bars but its signals are suppressed until the
  slice begins, so no trade can originate from warmup data and no indicator
  starts cold.
* Chosen-parameter history is reported per window: a strategy whose "best"
  parameters jump around every window is unstable, and the report shows it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine, BacktestResult, Trade
from trading_bot.backtesting.metrics import summarize
from trading_bot.core.config import RiskLimits
from trading_bot.core.events import Bar, Signal
from trading_bot.core.market import MarketSpec
from trading_bot.monitoring.logging import get_logger
from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.strategies.registry import make_strategy

log = get_logger("walkforward")

SELECTION_METRICS = ("sharpe", "trade_net_profit", "sortino", "trade_expectancy")


def expand_grid(grid: dict[str, list]) -> list[dict]:
    """{"a": [1, 2], "b": [3]} -> [{"a": 1, "b": 3}, {"a": 2, "b": 3}]"""
    if not grid:
        return [{}]
    keys = sorted(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


class _WarmupGate(BaseStrategy):
    """Feeds every bar to the inner strategy but suppresses its signals
    before ``live_from``: indicators warm up, trades cannot."""

    name = "warmup_gate"

    def __init__(self, inner: BaseStrategy, live_from: datetime):
        self.inner = inner
        self.live_from = live_from
        self.params = dict(inner.params)

    @property
    def warmup_bars(self) -> int:
        return self.inner.warmup_bars

    def on_bar(self, bar: Bar) -> Signal | None:
        sig = self.inner.on_bar(bar)
        if bar.ts < self.live_from:
            return None
        return sig

    def reset(self) -> None:
        self.inner.reset()


@dataclass
class WindowResult:
    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    chosen_params: dict
    train_metric: float
    test_metrics: dict
    n_test_trades: int


@dataclass
class WalkForwardResult:
    strategy_name: str
    market_id: str
    selection_metric: str
    grid: list[dict]
    windows: list[WindowResult]
    oos_trades: list[Trade]
    oos_daily_pnl: pd.Series
    oos_metrics: dict
    n_experiments: int          # every (window x param) train run counts

    @property
    def chosen_params_history(self) -> list[dict]:
        return [w.chosen_params for w in self.windows]


def _slice_with_warmup(bars: list[Bar], start_idx: int, end_idx: int, warmup: int) -> list[Bar]:
    return bars[max(0, start_idx - warmup): end_idx]


def run_walkforward(
    *,
    spec: MarketSpec,
    strategy_name: str,
    grid: list[dict],
    bars: list[Bar],
    limits: RiskLimits,
    bt_config: BacktestConfig,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    embargo_bars: int = 0,
    selection_metric: str = "sharpe",
    strategy_factory=None,
    funding=None,
) -> WalkForwardResult:
    """``strategy_factory(params) -> BaseStrategy`` overrides registry lookup
    (needed for strategies requiring non-parameter inputs, e.g. a funding
    series). ``funding`` is passed to every engine run (cost accrual)."""
    if selection_metric not in SELECTION_METRICS:
        raise ValueError(f"selection_metric must be one of {SELECTION_METRICS}")
    if not grid:
        raise ValueError("empty parameter grid")
    step = step_bars or test_bars
    n = len(bars)
    if train_bars + embargo_bars + test_bars > n:
        raise ValueError(
            f"not enough bars ({n}) for train={train_bars} + embargo={embargo_bars} "
            f"+ test={test_bars}"
        )

    factory = strategy_factory or (lambda params: make_strategy(strategy_name, params))
    probe = factory(grid[0])
    warmup = max(probe.warmup_bars, bt_config.atr_period) + 5

    def run_slice(params: dict, start_idx: int, end_idx: int) -> BacktestResult:
        inner = factory(params)
        gated = _WarmupGate(inner, live_from=bars[start_idx].ts)
        engine = BacktestEngine(spec, gated, limits, bt_config, funding=funding)
        return engine.run(_slice_with_warmup(bars, start_idx, end_idx, warmup))

    windows: list[WindowResult] = []
    oos_trades: list[Trade] = []
    oos_daily: list[pd.Series] = []
    n_experiments = 0

    start = 0
    w_index = 0
    while start + train_bars + embargo_bars + test_bars <= n:
        tr_a, tr_b = start, start + train_bars
        te_a = tr_b + embargo_bars
        te_b = te_a + test_bars

        best_params: dict | None = None
        best_metric = float("-inf")
        for params in grid:
            result = run_slice(params, tr_a, tr_b)
            n_experiments += 1
            value = result.metrics.get(selection_metric)
            value = float("-inf") if value is None else float(value)
            if value > best_metric:
                best_metric = value
                best_params = params

        test_result = run_slice(best_params, te_a, te_b)
        test_start_ts = bars[te_a].ts
        # Warmup bars belong to the embargo/train region; nothing traded there
        # (gate), but defensively assert it rather than trust it.
        for t in test_result.trades:
            if t.entry_ts < test_start_ts:
                raise AssertionError("walk-forward leak: trade entered before test slice")

        windows.append(
            WindowResult(
                index=w_index,
                train_start=bars[tr_a].ts,
                train_end=bars[tr_b - 1].ts,
                test_start=test_start_ts,
                test_end=bars[te_b - 1].ts,
                chosen_params=dict(best_params),
                train_metric=best_metric,
                test_metrics=dict(test_result.metrics),
                n_test_trades=len(test_result.trades),
            )
        )
        oos_trades.extend(test_result.trades)
        daily = test_result.daily_pnl
        daily = daily[[d >= test_start_ts.date() for d in daily.index]]
        oos_daily.append(daily)

        start += step
        w_index += 1

    if not windows:
        raise ValueError("no walk-forward windows produced — check sizes")

    oos_daily_pnl = pd.concat(oos_daily)
    oos_daily_pnl = oos_daily_pnl.groupby(oos_daily_pnl.index).sum()
    periods = 365 if spec.session.is_24_7 else 252
    oos_metrics = summarize(
        [t.net_pnl for t in oos_trades],
        oos_daily_pnl,
        bt_config.initial_equity,
        periods_per_year=periods,
    )

    log.info(
        "walk-forward: %d windows, %d train experiments, %d OOS trades",
        len(windows), n_experiments, len(oos_trades),
    )
    return WalkForwardResult(
        strategy_name=strategy_name,
        market_id=spec.market_id,
        selection_metric=selection_metric,
        grid=grid,
        windows=windows,
        oos_trades=oos_trades,
        oos_daily_pnl=oos_daily_pnl,
        oos_metrics=oos_metrics,
        n_experiments=n_experiments,
    )


def format_walkforward_report(result: WalkForwardResult) -> str:
    lines = [
        "=" * 72,
        f"WALK-FORWARD REPORT  {result.strategy_name}  on  {result.market_id}",
        f"selection metric (train-only): {result.selection_metric}   "
        f"grid size: {len(result.grid)}   train runs: {result.n_experiments}",
        "-" * 72,
    ]
    for w in result.windows:
        m = w.test_metrics
        lines.append(
            f"window {w.index}: train {w.train_start:%Y-%m-%d}..{w.train_end:%Y-%m-%d} "
            f"-> test {w.test_start:%Y-%m-%d}..{w.test_end:%Y-%m-%d}  "
            f"params={w.chosen_params}  "
            f"test net={m.get('trade_net_profit', 0):,.2f} "
            f"sharpe={m.get('sharpe', 0):.2f} trades={w.n_test_trades}"
        )
    m = result.oos_metrics
    lines += [
        "-" * 72,
        "AGGREGATED OUT-OF-SAMPLE (all test slices, never used for selection):",
        f"  trades: {m['trade_n_trades']}   net: {m['trade_net_profit']:,.2f}   "
        f"profit factor: {m['trade_profit_factor'] if m['trade_profit_factor'] is not None else 'n/a'}",
        f"  sharpe: {m['sharpe']:.3f}   sortino: {m['sortino']:.3f}   "
        f"max DD: {m['max_drawdown_pct']:.2%}",
        f"  daily mean: {m['daily_mean'] if m['daily_mean'] is not None else 'n/a'}   "
        f"median: {m['daily_median'] if m['daily_median'] is not None else 'n/a'}",
        "-" * 72,
        f"parameter stability across windows: {result.chosen_params_history}",
        "=" * 72,
    ]
    return "\n".join(lines)
