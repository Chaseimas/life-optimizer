# trading_bot — algorithmic trading research & execution system

A research-first system for discovering, validating and (eventually) trading
statistically defensible edges on **CME Micro E-mini Nasdaq-100 futures (MNQ)**
and — architecture-ready but disabled — **Hyperliquid perpetuals**.

## Read this first

* **~$400/day is a target for capital planning, not a requirement.** Nothing
  in this system sizes positions, forces trades, or tunes strategies to hit a
  dollar number. Risk comes first; the daily target only enters as arithmetic
  ("how much capital would a given edge need").
* **No edge has been found yet.** Nothing here is profitable, and nothing
  will be claimed profitable without out-of-sample evidence. If research
  concludes no edge exists, that is the deliverable.
* **Live trading does not exist in this codebase** (Phase 15, last). It is
  hard-gated behind explicit configuration and unimplemented on purpose.
* **Banned by design:** martingale, revenge trading, loss chasing, increasing
  size after losses, unlimited leverage, backtest manipulation, optimizing
  until history looks good. The risk engine has no API for any of them.
* **Hyperliquid compliance:** assumed unavailable to U.S. users. The executor
  is compliance-gated and disabled. No VPNs, no geo-circumvention, ever. If a
  lawful U.S. path appears, it can be enabled in config without rebuilding
  the research system.

## Architecture

```
                    STRATEGY            (strategies/ — venue-agnostic)
                       |
                SIGNAL ENGINE           (Signal events; direction only)
                       |
                 RISK ENGINE            (risk/ — sizing, hard limits, kill switch)
                       |
              PORTFOLIO ENGINE          (portfolio/ — Phase 12)
                       |
             EXECUTION INTERFACE        (execution/base_executor.py)
                  /         \
               MNQ           HYPERLIQUID
                |                 |
             CME API           HL API    (both: Phase 15, gated, unbuilt)
```

Strategies see normalized `Bar`s and a `MarketSpec` (tick size, point value,
fees, session, funding). They never know the venue, so the same strategy can
be evaluated on MNQ, BTC, ETH or SOL perps and the data decides where the
edge — if any — is strongest.

## Current status (honest)

| Phase | Scope | Status |
|---|---|---|
| 1 | Structure, config, logging, experiment tracking, tests, abstractions | **DONE** |
| 2 | Historical data ingestion (MNQ rollovers/sessions; HL funding/24-7) | next |
| 3 | Data cleaning (bad ticks, gaps, duplicates, timezones, holidays) | — |
| 4 | Feature engineering (timestamp-safe only) | — |
| 5 | Event-driven backtester | — |
| 6 | Fees / slippage / funding in simulation | cost models done; wiring in 5 |
| 7 | Simple baseline strategies (momentum, mean-rev, VWAP, ORB, regimes) | momentum skeleton only |
| 8 | Out-of-sample testing | split machinery done; needs 5+7 |
| 9 | Walk-forward testing | — |
| 10 | Monte Carlo | — |
| 11 | ML experiments (only if baselines earn it) | — |
| 12 | Cross-market comparison / portfolio mode | — |
| 13 | Paper trading (same code path as live) | — |
| 14 | Monitoring | logging done; dashboard/alerts pending |
| 15 | Live execution (explicitly configured, smallest size) | intentionally unbuilt |

What "DONE" means for Phase 1: 112 automated tests cover config gates, market
math, position sizing, risk limits, kill switch, executor gating, metrics,
fee/slippage models, experiment logging, and automated look-ahead detection.

## Setup

### 1. Software required

* **Python 3.11+** (developed on 3.11)
* git
* No database, broker account, or exchange API key is needed for Phases 1–10.

### 2. Create the virtual environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Phase 1 needs only `numpy`, `pandas`, `PyYAML`, `pytest`. Later-phase
dependencies (scikit-learn, LightGBM, data vendors) are listed but commented
out — install them when the phase actually starts.

### 4. Run the tests

```bash
python -m pytest            # from the repo root; 112 tests, < 2 s
```

Run these before and after every change. The look-ahead tests
(`tests/test_lookahead.py`, `tests/test_strategy.py`) are the ones that keep
the research honest — never weaken them to make a strategy "work".

### 5. Run the first research experiment

```bash
python -m trading_bot.research      # or: python trading_bot/research.py
```

This runs the **pipeline smoke experiment**: synthetic random-walk bars →
SimpleMomentum signals → next-bar evaluation → append to the experiment log
(`trading_bot/research/experiment_records.jsonl`). Expected output: a hit
rate near 50% and mean return near zero — the data is random by construction.
It proves the plumbing is look-ahead-safe, not that anything is profitable.

Other entry points (`backtest.py`, `walkforward.py`, `paper_trade.py`) print
their phase status and exit; `live_trade.py` refuses to run.

## Configuration

Everything lives in `trading_bot/config/config.yaml`:

* **Risk limits** (hard, strategy cannot touch them): `max_daily_loss`,
  `max_risk_per_trade`, `max_position_size`, `max_trades_per_day`,
  `max_drawdown`, `max_open_exposure`, `max_consecutive_losses`.
  Daily-loss / streak halts clear only when the engine clock starts a new
  day; a max-drawdown breach trips the kill switch, which only a human reset
  clears. The manual emergency stop is `touch trading_bot/KILL_SWITCH`.
* **Execution** defaults to `paper`. Live mode needs `mode: live`,
  `live.enabled: true` AND an exact confirmation phrase — and still hits
  `NotImplementedError` because Phase 15 is unbuilt.
* **Venues**: CME fee default is an estimate — verify against your broker.
  Hyperliquid is `enabled: false` with `us_compliant_access: false`.

Override the config path with `TRADING_BOT_CONFIG=/path/to/config.yaml`.

## The $400/day arithmetic (expectations, not promises)

Capital theoretically required for $400/day at a given **expected** daily
return on capital:

| Expected daily return | Capital required for ~$400/day |
|---|---|
| 0.10% | $400,000 |
| 0.20% | $200,000 |
| 0.25% | $160,000 |
| 0.50% | $80,000 |

These are **expected values from arithmetic, not guaranteed daily profits**.
A real strategy delivers a distribution: losing days, losing weeks, drawdowns.
Even a genuinely positive edge produces long stretches below its mean, and
sustained daily returns at the upper end of this table are rare and typically
come with drawdowns most people cannot sit through. Reports therefore always
include the daily distribution (median, std, percentiles, worst day, streaks)
next to the mean — a strategy averaging $400/day off a few giant wins is not
the same thing as consistent income, and will be reported as such. No
strategy will be optimized toward this table; it exists only to translate
*measured* out-of-sample edges into capital requirements.

## Research discipline (enforced by code where possible)

* **Every experiment is logged** — append-only JSONL with id, params, data,
  periods, results, git revision. Losers included; the log is the
  denominator for multiple-testing honesty.
* **Look-ahead bias**: tz-aware timestamps mandatory; signals act next-bar;
  `models/validation.py::assert_no_lookahead` recomputes features on
  truncated data and fails if the past changes when the future is removed.
* **Splits**: time-ordered only, with embargo (`time_series_splits`). Never
  shuffle market data across time. Final test years stay untouched.
* **Overfitting**: parameter neighborhoods (`research/parameter_tests.py`) —
  a parameter that only works at exactly one value flags the strategy.
* **ML** waits until baselines exist, answers "is this setup worth taking?",
  and must beat its non-ML baseline out-of-sample or be rejected.

## Next objective

Phase 2: obtain clean historical data — MNQ (contract specs, rollovers,
sessions, holidays; e.g. Databento or broker exports) and Hyperliquid
(public historical data; funding, 24/7) — then begin testing the first
baseline strategies against it with realistic costs.
