"""Event-driven backtest engine (Phases 5-6).

One strictly chronological pass over completed bars. Per bar, in order:

1. Forced flatten at the open (risk halt or kill switch from the previous bar).
2. Execute the PREVIOUS bar's signal at THIS bar's open (never earlier) —
   close/flip first, then size a new entry through the risk engine.
3. Protective stop / take-profit checks against this bar's range
   (gap-aware, stop-before-target: see backtesting.execution).
4. Funding accrual for perps (events in (previous close, this close]).
5. Feed the strategy this completed bar; store any signal for the NEXT bar.
6. Risk state effects: kill switch stops the run; a daily halt schedules a
   flatten at the next open.
7. Mark-to-market equity record; streaming ATR update (used for sizing
   stops from the NEXT bar on — never the current one).

No component ever sees a future bar. ``tests/test_engine.py`` verifies the
mechanics against hand-computed trades and checks truncation invariance
(removing future bars never changes already-closed trades).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from trading_bot.backtesting.execution import check_protective_exit, market_fill
from trading_bot.backtesting.fees import fee_for_fill
from trading_bot.backtesting.metrics import (
    TRADING_DAYS_CRYPTO,
    TRADING_DAYS_FUTURES,
    summarize,
    trade_stats,
)
from trading_bot.backtesting.slippage import BpsSlippage, FixedTicksSlippage, SlippageModel
from trading_bot.core.config import RiskLimits
from trading_bot.core.events import Bar, Signal
from trading_bot.core.market import FeeMode, MarketSpec
from trading_bot.core.types import Liquidity, Side
from trading_bot.monitoring.logging import get_logger
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.risk.position_sizing import compute_position_size
from trading_bot.risk.risk_manager import RiskManager
from trading_bot.strategies.base_strategy import BaseStrategy

log = get_logger("backtest.engine")


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 100_000.0
    risk_per_trade: float | None = None      # None -> use limits.max_risk_per_trade
    # Stop sizing, first match wins: signal.stop_distance -> fixed_stop_points
    # -> stop_atr_mult * ATR. No resolvable stop => no trade.
    fixed_stop_points: float | None = None
    fixed_tp_points: float | None = None
    stop_atr_mult: float | None = 2.0
    tp_atr_mult: float | None = None
    atr_period: int = 14
    slippage: SlippageModel | None = None    # None -> venue-appropriate default
    liquidity: Liquidity = Liquidity.TAKER
    allow_short: bool = True
    label: str = ""


@dataclass
class Trade:
    """One closed round trip. ``entry_ts``/``exit_ts`` are the CLOSE times of
    the bars in which the fills occurred (fills happen at those bars' opens,
    or at stop/target levels within them)."""

    market_id: str
    direction: Side
    entry_ts: datetime
    entry_price: float
    exit_ts: datetime
    exit_price: float
    size: float
    stop_price: float | None
    tp_price: float | None
    entry_reason: str
    exit_reason: str
    gross_pnl: float          # from actual fills (slippage already inside)
    fees: float
    funding: float            # >0 = paid, <0 = received
    slippage_cost: float      # informational: fills vs reference prices
    net_pnl: float
    bars_held: int


@dataclass
class _Position:
    direction: Side
    size: float
    entry_ts: datetime
    entry_fill: float
    stop_price: float | None
    tp_price: float | None
    entry_fee: float
    entry_slippage: float
    entry_reason: str
    funding_paid: float = 0.0
    bars_held: int = 0


@dataclass
class BacktestResult:
    market_id: str
    strategy_name: str
    strategy_params: dict
    config: BacktestConfig
    n_bars: int
    trades: list[Trade]
    equity: pd.Series             # mark-to-market at each bar close
    daily_pnl: pd.Series          # per UTC date
    metrics: dict
    halts: list[str] = field(default_factory=list)

    @property
    def trade_pnls(self) -> list[float]:
        return [t.net_pnl for t in self.trades]


class _StreamingATR:
    """Wilder ATR computed incrementally — value after bar t is available for
    decisions from bar t+1 on."""

    def __init__(self, period: int):
        self.period = period
        self.value: float | None = None
        self._prev_close: float | None = None
        self._warmup_sum = 0.0
        self._warmup_n = 0

    def update(self, bar: Bar) -> None:
        if self._prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self._prev_close),
                abs(bar.low - self._prev_close),
            )
        if self.value is None:
            self._warmup_sum += tr
            self._warmup_n += 1
            if self._warmup_n >= self.period:
                self.value = self._warmup_sum / self.period
        else:
            self.value = (self.value * (self.period - 1) + tr) / self.period
        self._prev_close = bar.close


class BacktestEngine:
    def __init__(
        self,
        spec: MarketSpec,
        strategy: BaseStrategy,
        limits: RiskLimits,
        config: BacktestConfig | None = None,
        funding: pd.Series | None = None,
    ):
        self.spec = spec
        self.strategy = strategy
        self.limits = limits
        self.config = config or BacktestConfig()
        self.funding = funding
        if self.funding is not None:
            if self.funding.index.tz is None:
                raise ValueError("funding series index must be tz-aware")
            self.funding = self.funding.sort_index()
        self.slippage: SlippageModel = self.config.slippage or (
            FixedTicksSlippage(1.0)
            if spec.fees.mode is FeeMode.PER_CONTRACT
            else BpsSlippage(1.0)
        )

    # ------------------------------------------------------------------ run --
    def run(self, bars: list[Bar]) -> BacktestResult:
        cfg = self.config
        spec = self.spec
        if not bars:
            raise ValueError("no bars to backtest")
        for b in bars:
            if b.market_id != bars[0].market_id:
                raise ValueError("all bars must belong to one market")
        for a, b in zip(bars, bars[1:]):
            if b.ts <= a.ts:
                raise ValueError(f"bars must be strictly increasing in time (at {b.ts})")

        risk = RiskManager(self.limits, KillSwitch(), cfg.initial_equity)
        self.strategy.reset()
        atr = _StreamingATR(cfg.atr_period)

        position: _Position | None = None
        pending: Signal | None = None
        trades: list[Trade] = []
        equity_ts: list[datetime] = []
        equity_vals: list[float] = []
        halts: list[str] = []
        stopped = False
        flatten_reason: str | None = None
        prev_ts: datetime | None = None

        def close_position(pos: _Position, ref_price: float, ts: datetime, reason: str) -> None:
            exit_dir = -int(pos.direction)
            fill, slip_out = market_fill(spec, exit_dir, ref_price, pos.size, self.slippage)
            exit_fee = fee_for_fill(spec, fill, pos.size, cfg.liquidity)
            gross = spec.pnl(pos.direction, pos.entry_fill, fill, pos.size)
            fees = pos.entry_fee + exit_fee
            net = gross - fees - pos.funding_paid
            trades.append(
                Trade(
                    market_id=spec.market_id,
                    direction=pos.direction,
                    entry_ts=pos.entry_ts,
                    entry_price=pos.entry_fill,
                    exit_ts=ts,
                    exit_price=fill,
                    size=pos.size,
                    stop_price=pos.stop_price,
                    tp_price=pos.tp_price,
                    entry_reason=pos.entry_reason,
                    exit_reason=reason,
                    gross_pnl=gross,
                    fees=fees,
                    funding=pos.funding_paid,
                    slippage_cost=pos.entry_slippage + slip_out,
                    net_pnl=net,
                    bars_held=pos.bars_held,
                )
            )
            risk.record_closed_trade(net)

        for bar in bars:
            day = bar.ts.date()
            if risk.current_day is None or day > risk.current_day:
                risk.start_new_day(day)

            # 1) forced flatten scheduled by the previous bar
            if position is not None and flatten_reason is not None:
                close_position(position, bar.open, bar.ts, flatten_reason)
                position = None
            flatten_reason = None

            # 2) previous bar's signal executes at this bar's open
            if pending is not None and not stopped:
                desired = pending.direction
                if position is not None and desired is not position.direction:
                    close_position(
                        position, bar.open, bar.ts,
                        "signal_flat" if desired is Side.FLAT else "signal_flip",
                    )
                    position = None
                if (
                    position is None
                    and desired is not Side.FLAT
                    and (cfg.allow_short or desired is Side.LONG)
                ):
                    stop_dist = (
                        pending.stop_distance
                        or cfg.fixed_stop_points
                        or (cfg.stop_atr_mult * atr.value
                            if cfg.stop_atr_mult and atr.value else None)
                    )
                    sizing = compute_position_size(
                        equity=risk.equity,
                        price=bar.open,
                        stop_distance=stop_dist if stop_dist else 0.0,
                        spec=spec,
                        limits=self.limits,
                        risk_per_trade=cfg.risk_per_trade,
                    )
                    if sizing.size > 0:
                        decision = risk.pre_trade_check(proposed_notional=sizing.notional)
                        if decision:
                            entry_dir = int(desired)
                            fill, slip_in = market_fill(
                                spec, entry_dir, bar.open, sizing.size, self.slippage
                            )
                            tp_dist = (
                                cfg.fixed_tp_points
                                or (cfg.tp_atr_mult * atr.value
                                    if cfg.tp_atr_mult and atr.value else None)
                            )
                            position = _Position(
                                direction=desired,
                                size=sizing.size,
                                entry_ts=bar.ts,
                                entry_fill=fill,
                                stop_price=spec.round_price(fill - entry_dir * stop_dist),
                                tp_price=(
                                    spec.round_price(fill + entry_dir * tp_dist)
                                    if tp_dist else None
                                ),
                                entry_fee=fee_for_fill(spec, fill, sizing.size, cfg.liquidity),
                                entry_slippage=slip_in,
                                entry_reason=pending.reason,
                            )
                            risk.record_trade_opened()
            pending = None

            # 3) protective exits against this bar's range
            if position is not None:
                hit = check_protective_exit(
                    bar, position.direction, position.stop_price, position.tp_price
                )
                if hit is not None:
                    ref_exit, reason = hit
                    close_position(position, ref_exit, bar.ts, reason)
                    position = None

            # 4) funding accrual (perps): events in (prev bar close, this close]
            if (
                position is not None
                and self.funding is not None
                and spec.has_funding
                and prev_ts is not None
            ):
                window = self.funding[
                    (self.funding.index > prev_ts) & (self.funding.index <= bar.ts)
                ]
                if len(window):
                    notional = spec.notional(bar.close, position.size)
                    # positive rate: longs pay, shorts receive
                    position.funding_paid += float(window.sum()) * notional * int(
                        position.direction
                    )

            # 5) strategy sees the completed bar
            sig = self.strategy.on_bar(bar)
            if sig is not None and not stopped:
                if sig.ts != bar.ts:
                    raise AssertionError(
                        "strategy emitted a signal whose timestamp is not the "
                        "current bar close — look-ahead guard tripped"
                    )
                pending = sig

            # 6) risk state effects
            if risk.kill_switch.is_tripped and not stopped:
                stopped = True
                pending = None
                halts.append(f"{bar.ts.isoformat()} KILL SWITCH — run stopped")
                if position is not None:
                    flatten_reason = "kill_switch"
            elif position is not None and risk.halted_for_day and flatten_reason is None:
                halts.append(f"{bar.ts.isoformat()} daily halt: {risk.halted_for_day}")
                flatten_reason = "risk_halt"

            # 7) mark to market + ATR update (ATR usable from the NEXT bar)
            if position is not None:
                position.bars_held += 1
                unrealized = spec.pnl(
                    position.direction, position.entry_fill, bar.close, position.size
                )
                mtm = risk.equity + unrealized - position.entry_fee - position.funding_paid
            else:
                mtm = risk.equity
            equity_ts.append(bar.ts)
            equity_vals.append(mtm)
            atr.update(bar)
            prev_ts = bar.ts

        # end of data: force-close any open position at the last close
        if position is not None:
            close_position(position, bars[-1].close, bars[-1].ts, "end_of_data")
            position = None
            equity_vals[-1] = risk.equity

        equity = pd.Series(
            equity_vals, index=pd.DatetimeIndex(equity_ts, name="ts"), name="equity"
        )
        daily_equity = equity.groupby(equity.index.date).last()
        daily_pnl = daily_equity.diff()
        if len(daily_equity):
            daily_pnl.iloc[0] = daily_equity.iloc[0] - cfg.initial_equity
        daily_pnl.name = "daily_pnl"

        periods = TRADING_DAYS_CRYPTO if spec.session.is_24_7 else TRADING_DAYS_FUTURES
        pnls = [t.net_pnl for t in trades]
        metrics = summarize(pnls, daily_pnl, cfg.initial_equity, periods_per_year=periods)
        metrics["long"] = trade_stats([t.net_pnl for t in trades if t.direction is Side.LONG])
        metrics["short"] = trade_stats([t.net_pnl for t in trades if t.direction is Side.SHORT])
        metrics["exit_reasons"] = dict(Counter(t.exit_reason for t in trades))
        metrics["total_fees"] = float(sum(t.fees for t in trades))
        metrics["total_slippage_cost"] = float(sum(t.slippage_cost for t in trades))
        metrics["total_funding"] = float(sum(t.funding for t in trades))
        metrics["avg_bars_held"] = (
            float(sum(t.bars_held for t in trades)) / len(trades) if trades else None
        )
        metrics["pnl_by_entry_hour_utc"] = _pnl_by_hour(trades)

        return BacktestResult(
            market_id=spec.market_id,
            strategy_name=self.strategy.name,
            strategy_params=dict(self.strategy.params),
            config=cfg,
            n_bars=len(bars),
            trades=trades,
            equity=equity,
            daily_pnl=daily_pnl,
            metrics=metrics,
            halts=halts,
        )


def _pnl_by_hour(trades: list[Trade]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for t in trades:
        hour = t.entry_ts.astimezone(timezone.utc).hour
        slot = out.setdefault(hour, {"n": 0, "net": 0.0})
        slot["n"] += 1
        slot["net"] += t.net_pnl
    return {h: {"n": v["n"], "net": round(v["net"], 2)} for h, v in sorted(out.items())}
