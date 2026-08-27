"""Event-driven trading engine (Phases 5-6, refactored for Phase 13).

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

The engine is incremental: ``start()`` -> ``step(bar)`` per completed bar ->
``finalize()``. ``run(bars)`` is exactly that loop, and the PAPER TRADER
drives the same ``step()`` — backtest and paper trading share one code path
by construction, not by promise.

No component ever sees a future bar. ``tests/test_engine.py`` verifies the
mechanics against hand-computed trades and checks truncation invariance
(removing future bars never changes already-closed trades).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

import numpy as np

from trading_bot.backtesting.execution import check_protective_exit, market_fill
from trading_bot.backtesting.fees import fee_for_fill
from trading_bot.backtesting.maker import (
    MakerParams,
    RestingOrder,
    adverse_selection_cost,
    evaluate_fill,
    limit_price_for,
)
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
    # Maker execution for ENTRIES (exits stay taker). None = classic taker
    # entries (fully backward compatible). See backtesting/maker.py for the
    # model, its assumptions, and what OHLC data cannot honestly provide.
    maker: MakerParams | None = None
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
    entry_slippage: float       # taker: informational (already inside gross);
                                # maker: the adverse-selection charge
    entry_reason: str
    funding_paid: float = 0.0
    bars_held: int = 0
    # Cash costs NOT embedded in fill prices (maker adverse-selection charge);
    # subtracted from net P&L at close. Always 0 for taker entries.
    extra_costs: float = 0.0


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
        kill_switch: KillSwitch | None = None,
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
        if self.config.maker is not None:
            self.config.maker.validate()
        self._external_kill_switch = kill_switch
        self._started = False

    # ---------------------------------------------------------------- start --
    def start(self) -> None:
        """Reset all run state. Call once before the first ``step``."""
        self.risk = RiskManager(
            self.limits,
            self._external_kill_switch or KillSwitch(),
            self.config.initial_equity,
        )
        self.strategy.reset()
        self._atr = _StreamingATR(self.config.atr_period)
        self.position: _Position | None = None
        self._pending: Signal | None = None
        self.trades: list[Trade] = []
        self._equity_ts: list[datetime] = []
        self._equity_vals: list[float] = []
        self.halts: list[str] = []
        self.stopped = False
        self._flatten_reason: str | None = None
        self._prev_ts: datetime | None = None
        self._last_close: float | None = None
        self._n_bars = 0
        self._new_trades_this_step: list[Trade] = []
        self._resting: RestingOrder | None = None
        self._maker_rng = (
            np.random.default_rng(self.config.maker.seed)
            if self.config.maker is not None else None
        )
        self._maker_stats = {
            "orders_placed": 0, "filled": 0, "partial_fills": 0,
            "missed_expired": 0, "canceled_by_risk": 0,
            "replaced_by_signal": 0, "unresolved_at_end": 0,
            "placement_denied_risk": 0, "placement_denied_sizing": 0,
        }
        self._started = True

    def _cancel_resting(self, why: str) -> None:
        if self._resting is not None:
            self._maker_stats[why] += 1
            self._resting = None

    # ------------------------------------------------------------- internals --
    def _close_position(self, pos: _Position, ref_price: float, ts: datetime,
                        reason: str) -> None:
        cfg = self.config
        spec = self.spec
        exit_dir = -int(pos.direction)
        fill, slip_out = market_fill(spec, exit_dir, ref_price, pos.size, self.slippage)
        exit_fee = fee_for_fill(spec, fill, pos.size, cfg.liquidity)
        gross = spec.pnl(pos.direction, pos.entry_fill, fill, pos.size)
        fees = pos.entry_fee + exit_fee
        net = gross - fees - pos.funding_paid - pos.extra_costs
        trade = Trade(
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
        self.trades.append(trade)
        self._new_trades_this_step.append(trade)
        self.risk.record_closed_trade(net)

    # ---------------------------------------------------------------- step --
    def step(self, bar: Bar) -> list[Trade]:
        """Process one completed bar. Returns trades CLOSED during this bar
        (for live logging); they are also accumulated in ``self.trades``."""
        if not self._started:
            raise RuntimeError("call start() before step()")
        if bar.market_id != self.spec.market_id:
            raise ValueError(
                f"bar market {bar.market_id!r} does not match engine market "
                f"{self.spec.market_id!r}; all bars must belong to one market"
            )
        if self._prev_ts is not None and bar.ts <= self._prev_ts:
            raise ValueError(f"bars must be strictly increasing in time (at {bar.ts})")

        cfg = self.config
        spec = self.spec
        risk = self.risk
        self._new_trades_this_step = []

        day = bar.ts.date()
        if risk.current_day is None or day > risk.current_day:
            risk.start_new_day(day)

        # 1) forced flatten scheduled by the previous bar
        if self.position is not None and self._flatten_reason is not None:
            self._close_position(self.position, bar.open, bar.ts, self._flatten_reason)
            self.position = None
        self._flatten_reason = None

        # 2) previous bar's signal executes at this bar's open
        if self._pending is not None and not self.stopped:
            desired = self._pending.direction
            if self._resting is not None and desired is not self._resting.direction:
                self._cancel_resting("replaced_by_signal")
            if self.position is not None and desired is not self.position.direction:
                self._close_position(
                    self.position, bar.open, bar.ts,
                    "signal_flat" if desired is Side.FLAT else "signal_flip",
                )
                self.position = None
            if (
                self.position is None
                and self._resting is None
                and desired is not Side.FLAT
                and (cfg.allow_short or desired is Side.LONG)
            ):
                stop_dist = (
                    self._pending.stop_distance
                    or cfg.fixed_stop_points
                    or (cfg.stop_atr_mult * self._atr.value
                        if cfg.stop_atr_mult and self._atr.value else None)
                )
                tp_dist = (
                    cfg.fixed_tp_points
                    or (cfg.tp_atr_mult * self._atr.value
                        if cfg.tp_atr_mult and self._atr.value else None)
                )
                if cfg.maker is None:
                    # ---- taker entry: marketable at this bar's open ----------
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
                            self.position = _Position(
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
                                entry_reason=self._pending.reason,
                            )
                            risk.record_trade_opened()
                else:
                    # ---- maker entry: place a resting limit off this open ----
                    limit = limit_price_for(spec, desired, bar.open, cfg.maker)
                    sizing = compute_position_size(
                        equity=risk.equity,
                        price=limit,
                        stop_distance=stop_dist if stop_dist else 0.0,
                        spec=spec,
                        limits=self.limits,
                        risk_per_trade=cfg.risk_per_trade,
                    )
                    if sizing.size > 0 and stop_dist:
                        decision = risk.pre_trade_check(proposed_notional=sizing.notional)
                        if decision:
                            self._resting = RestingOrder(
                                direction=desired,
                                limit_price=limit,
                                size=sizing.size,
                                stop_distance=stop_dist,
                                tp_distance=tp_dist,
                                placed_ts=bar.ts,
                                reason=self._pending.reason,
                            )
                            self._maker_stats["orders_placed"] += 1
                        else:
                            self._maker_stats["placement_denied_risk"] += 1
                    else:
                        self._maker_stats["placement_denied_sizing"] += 1
        self._pending = None

        # 2b) resting limit order (maker): evaluate against this bar. A fill
        # can happen the same bar the order is placed; a filled position is
        # then subject to this bar's protective-exit check (conservative).
        if self._resting is not None:
            if self.stopped or risk.halted_for_day:
                self._cancel_resting("canceled_by_risk")
            else:
                order = self._resting
                event = evaluate_fill(
                    bar, order.direction, order.limit_price, cfg.maker, self._maker_rng
                )
                filled = False
                if event is not None:
                    fill_size = spec.round_size(order.size * event.fraction)
                    size_ok = fill_size >= spec.min_size and (
                        not spec.min_notional
                        or spec.notional(event.price, fill_size) >= spec.min_notional
                    )
                    if size_ok:
                        decision = risk.pre_trade_check(
                            proposed_notional=spec.notional(event.price, fill_size)
                        )
                        if decision:
                            adverse = adverse_selection_cost(
                                spec, event.price, fill_size, cfg.maker
                            )
                            d = int(order.direction)
                            self.position = _Position(
                                direction=order.direction,
                                size=fill_size,
                                entry_ts=bar.ts,
                                entry_fill=event.price,
                                stop_price=spec.round_price(
                                    event.price - d * order.stop_distance
                                ),
                                tp_price=(
                                    spec.round_price(event.price + d * order.tp_distance)
                                    if order.tp_distance else None
                                ),
                                entry_fee=fee_for_fill(
                                    spec, event.price, fill_size, Liquidity.MAKER
                                ),
                                entry_slippage=adverse,
                                entry_reason=order.reason,
                                extra_costs=adverse,
                            )
                            risk.record_trade_opened()
                            self._maker_stats["filled"] += 1
                            if event.fraction < 1.0:
                                self._maker_stats["partial_fills"] += 1
                            self._resting = None
                            filled = True
                        else:
                            self._cancel_resting("canceled_by_risk")
                if self._resting is not None and not filled:
                    self._resting.bars_alive += 1
                    if self._resting.bars_alive >= cfg.maker.max_lifetime_bars:
                        self._resting = None
                        self._maker_stats["missed_expired"] += 1

        # 3) protective exits against this bar's range
        if self.position is not None:
            hit = check_protective_exit(
                bar, self.position.direction, self.position.stop_price,
                self.position.tp_price,
            )
            if hit is not None:
                ref_exit, reason = hit
                self._close_position(self.position, ref_exit, bar.ts, reason)
                self.position = None

        # 4) funding accrual (perps): events in (prev bar close, this close]
        if (
            self.position is not None
            and self.funding is not None
            and spec.has_funding
            and self._prev_ts is not None
        ):
            window = self.funding[
                (self.funding.index > self._prev_ts) & (self.funding.index <= bar.ts)
            ]
            if len(window):
                notional = spec.notional(bar.close, self.position.size)
                # positive rate: longs pay, shorts receive
                self.position.funding_paid += float(window.sum()) * notional * int(
                    self.position.direction
                )

        # 5) strategy sees the completed bar
        sig = self.strategy.on_bar(bar)
        if sig is not None and not self.stopped:
            if sig.ts != bar.ts:
                raise AssertionError(
                    "strategy emitted a signal whose timestamp is not the "
                    "current bar close — look-ahead guard tripped"
                )
            self._pending = sig

        # 6) risk state effects
        if risk.kill_switch.is_tripped and not self.stopped:
            self.stopped = True
            self._pending = None
            self._cancel_resting("canceled_by_risk")
            self.halts.append(f"{bar.ts.isoformat()} KILL SWITCH — run stopped")
            if self.position is not None:
                self._flatten_reason = "kill_switch"
        elif (
            self.position is not None
            and risk.halted_for_day
            and self._flatten_reason is None
        ):
            self.halts.append(f"{bar.ts.isoformat()} daily halt: {risk.halted_for_day}")
            self._flatten_reason = "risk_halt"

        # 7) mark to market + ATR update (ATR usable from the NEXT bar)
        if self.position is not None:
            self.position.bars_held += 1
            unrealized = spec.pnl(
                self.position.direction, self.position.entry_fill, bar.close,
                self.position.size,
            )
            mtm = (risk.equity + unrealized - self.position.entry_fee
                   - self.position.funding_paid - self.position.extra_costs)
        else:
            mtm = risk.equity
        self._equity_ts.append(bar.ts)
        self._equity_vals.append(mtm)
        self._atr.update(bar)
        self._prev_ts = bar.ts
        self._last_close = bar.close
        self._n_bars += 1
        return self._new_trades_this_step

    # ------------------------------------------------------------- snapshot --
    def snapshot(self) -> dict:
        """Current engine state (paper-trading status/monitoring)."""
        if not self._started:
            return {"started": False}
        pos = self.position
        return {
            "started": True,
            "n_bars": self._n_bars,
            "last_bar_ts": self._prev_ts.isoformat() if self._prev_ts else None,
            "equity_realized": self.risk.equity,
            "equity_mark_to_market": self._equity_vals[-1] if self._equity_vals else None,
            "position": (
                {
                    "direction": pos.direction.name,
                    "size": pos.size,
                    "entry_ts": pos.entry_ts.isoformat(),
                    "entry_price": pos.entry_fill,
                    "stop_price": pos.stop_price,
                    "tp_price": pos.tp_price,
                    "funding_paid": pos.funding_paid,
                    "bars_held": pos.bars_held,
                }
                if pos is not None else None
            ),
            "n_trades": len(self.trades),
            "daily_pnl": self.risk.daily_pnl,
            "trades_today": self.risk.trades_today,
            "halted_for_day": self.risk.halted_for_day,
            "kill_switch_tripped": self.risk.kill_switch.is_tripped,
            "stopped": self.stopped,
            "halts": list(self.halts),
            "resting_order": (
                {
                    "direction": self._resting.direction.name,
                    "limit_price": self._resting.limit_price,
                    "size": self._resting.size,
                    "bars_alive": self._resting.bars_alive,
                }
                if self._resting is not None else None
            ),
            "maker_stats": (
                dict(self._maker_stats) if self.config.maker is not None else None
            ),
        }

    # ------------------------------------------------------------- finalize --
    def finalize(self, close_open_position: bool = True) -> BacktestResult:
        if not self._started or self._n_bars == 0:
            raise ValueError("no bars to backtest")

        if self.position is not None and close_open_position:
            # Force-close at the last seen bar's close price.
            self._close_position(
                self.position, self._last_close, self._prev_ts, "end_of_data"
            )
            self.position = None
            self._equity_vals[-1] = self.risk.equity

        equity = pd.Series(
            self._equity_vals,
            index=pd.DatetimeIndex(self._equity_ts, name="ts"),
            name="equity",
        )
        daily_equity = equity.groupby(equity.index.date).last()
        daily_pnl = daily_equity.diff()
        if len(daily_equity):
            daily_pnl.iloc[0] = daily_equity.iloc[0] - self.config.initial_equity
        daily_pnl.name = "daily_pnl"

        periods = TRADING_DAYS_CRYPTO if self.spec.session.is_24_7 else TRADING_DAYS_FUTURES
        pnls = [t.net_pnl for t in self.trades]
        metrics = summarize(pnls, daily_pnl, self.config.initial_equity,
                            periods_per_year=periods)
        metrics["long"] = trade_stats(
            [t.net_pnl for t in self.trades if t.direction is Side.LONG]
        )
        metrics["short"] = trade_stats(
            [t.net_pnl for t in self.trades if t.direction is Side.SHORT]
        )
        metrics["exit_reasons"] = dict(Counter(t.exit_reason for t in self.trades))
        metrics["total_fees"] = float(sum(t.fees for t in self.trades))
        metrics["total_slippage_cost"] = float(sum(t.slippage_cost for t in self.trades))
        metrics["total_funding"] = float(sum(t.funding for t in self.trades))
        metrics["avg_bars_held"] = (
            float(sum(t.bars_held for t in self.trades)) / len(self.trades)
            if self.trades else None
        )
        metrics["pnl_by_entry_hour_utc"] = _pnl_by_hour(self.trades)
        metrics["execution_model"] = (
            "taker" if self.config.maker is None else "maker_entry_taker_exit"
        )
        if self.config.maker is not None:
            if self._resting is not None:
                self._maker_stats["unresolved_at_end"] += 1
                self._resting = None
            stats = dict(self._maker_stats)
            placed = stats["orders_placed"]
            stats["fill_rate"] = (stats["filled"] / placed) if placed else None
            metrics["maker"] = {**self.config.maker.describe(), **stats}

        return BacktestResult(
            market_id=self.spec.market_id,
            strategy_name=self.strategy.name,
            strategy_params=dict(self.strategy.params),
            config=self.config,
            n_bars=self._n_bars,
            trades=self.trades,
            equity=equity,
            daily_pnl=daily_pnl,
            metrics=metrics,
            halts=self.halts,
        )

    # ------------------------------------------------------------------ run --
    def run(self, bars: list[Bar]) -> BacktestResult:
        if not bars:
            raise ValueError("no bars to backtest")
        self.start()
        for bar in bars:
            self.step(bar)
        return self.finalize(close_open_position=True)


def _pnl_by_hour(trades: list[Trade]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for t in trades:
        hour = t.entry_ts.astimezone(timezone.utc).hour
        slot = out.setdefault(hour, {"n": 0, "net": 0.0})
        slot["n"] += 1
        slot["net"] += t.net_pnl
    return {h: {"n": v["n"], "net": round(v["net"], 2)} for h, v in sorted(out.items())}
