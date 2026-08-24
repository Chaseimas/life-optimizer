"""Plain-text backtest report. Every number comes straight from the result —
no editorializing, no hiding losers."""

from __future__ import annotations

from trading_bot.backtesting.engine import BacktestResult


def _fmt(v, money: bool = False, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    if pct:
        return f"{v:.2%}"
    if money:
        return f"{v:,.2f}"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def format_report(result: BacktestResult) -> str:
    m = result.metrics
    lines = [
        "=" * 72,
        f"BACKTEST REPORT  {result.strategy_name}  on  {result.market_id}",
        f"params: {result.strategy_params}",
        f"bars: {result.n_bars}   period: "
        f"{result.equity.index[0]} .. {result.equity.index[-1]}",
        "-" * 72,
        f"trades:            {m['trade_n_trades']}   "
        f"(long {m['long']['n_trades']}, short {m['short']['n_trades']})",
        f"net profit:        {_fmt(m['trade_net_profit'], money=True)}   "
        f"(gross +{_fmt(m['trade_gross_profit'], money=True)} / "
        f"-{_fmt(m['trade_gross_loss'], money=True)})",
        f"profit factor:     {_fmt(m['trade_profit_factor'])}",
        f"win rate:          {_fmt(m['trade_win_rate'], pct=True)}   "
        f"avg win {_fmt(m['trade_avg_win'], money=True)} / "
        f"avg loss {_fmt(m['trade_avg_loss'], money=True)}",
        f"expectancy/trade:  {_fmt(m['trade_expectancy'], money=True)}",
        f"max consec:        {m['trade_max_consecutive_wins']} wins / "
        f"{m['trade_max_consecutive_losses']} losses",
        "-" * 72,
        f"sharpe (daily):    {_fmt(m['sharpe'])}      sortino: {_fmt(m['sortino'])}      "
        f"calmar: {_fmt(m['calmar'])}",
        f"max drawdown:      {_fmt(m['max_drawdown_abs'], money=True)} "
        f"({_fmt(m['max_drawdown_pct'], pct=True)})",
        f"final equity:      {_fmt(m['final_equity'], money=True)}   "
        f"annualized return: {_fmt(m['annualized_return_pct'], pct=True)}",
        "-" * 72,
        f"daily P&L:  mean {_fmt(m['daily_mean'], money=True)}  "
        f"median {_fmt(m['daily_median'], money=True)}  "
        f"std {_fmt(m['daily_std'], money=True)}",
        f"            best {_fmt(m['daily_best_day'], money=True)}  "
        f"worst {_fmt(m['daily_worst_day'], money=True)}  "
        f"p5 {_fmt(m['daily_p5'], money=True)}  p95 {_fmt(m['daily_p95'], money=True)}",
        f"            profitable days {_fmt(m['daily_pct_profitable_days'], pct=True)}  "
        f"losing days {_fmt(m['daily_pct_losing_days'], pct=True)}  "
        f"({m['daily_n_days']} days)",
        "-" * 72,
        f"costs: fees {_fmt(m['total_fees'], money=True)}   "
        f"slippage {_fmt(m['total_slippage_cost'], money=True)}   "
        f"funding {_fmt(m['total_funding'], money=True)}",
        f"exits: {m['exit_reasons']}",
        f"avg bars held: {_fmt(m['avg_bars_held'])}",
    ]
    if m.get("pnl_by_entry_hour_utc"):
        lines.append(f"P&L by entry hour (UTC): {m['pnl_by_entry_hour_utc']}")
    if result.halts:
        lines.append("-" * 72)
        lines.append("RISK EVENTS:")
        lines.extend(f"  {h}" for h in result.halts)
    lines.append("=" * 72)
    return "\n".join(lines)
