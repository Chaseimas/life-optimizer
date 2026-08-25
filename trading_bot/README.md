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
| 2 | Historical data ingestion | **DONE** (framework + Hyperliquid client + CSV/Databento import + futures roll handling; real data pull needs a networked machine — see below) |
| 3 | Data cleaning (bad ticks, gaps, duplicates, timezones, sessions) | **DONE** (audited `CleanReport`, CME session filter, gaps reported never filled) |
| 4 | Feature engineering (timestamp-safe only) | **DONE** (17 features, every one passes the leak detector; labels quarantined) |
| 5 | Event-driven backtester | **DONE** (next-bar fills, gap-aware stops, stop-before-target, truncation-invariance tested) |
| 6 | Fees / slippage / funding in simulation | **DONE** (per-contract + bps fees, tick/bps slippage, hourly funding) |
| 7 | Simple baseline strategies | **DONE** as code (momentum, z-score mean reversion, rolling VWAP fade/trend, opening-range breakout, regime-gated momentum — all leak-tested); their *evaluation* awaits real data |
| 8 | Out-of-sample testing | machinery done (embargoed splits, warmup gating); verdicts need real data |
| 9 | Walk-forward testing | **DONE** (train-only selection, per-window OOS, param-stability report) |
| 10 | Monte Carlo | **DONE** (shuffle + bootstrap resampling: drawdown/streak/ruin distributions; `backtest.py --mc N`) |
| 11 | ML experiments (only if baselines earn it) | **DONE** as machinery (setup-filter ladder: logistic/RF/HistGB; time-ordered splits; accept/reject protocol that finds a planted edge AND rejects pure noise — both tested); real verdicts need real data |
| 12 | Cross-market comparison / portfolio mode | **DONE** as machinery (strategy-P&L correlation incl. rolling; DIVERSIFY/CONCENTRATE/NO-BASIS verdicts) |
| 13 | Paper trading (same code path as live) | **DONE** (drives the same engine via `step(bar)` — equivalence to backtest is a test, not a promise; replay feed + Hyperliquid polling feed; trades.jsonl/state.json per session) |
| 14 | Monitoring | **DONE** at v1 (UTC logging, alert sinks incl. optional webhook, read-only status dashboard; alerts observe, the risk engine decides) |
| 15 | Live execution (explicitly configured, smallest size) | intentionally unbuilt — requires a proven out-of-sample edge and completed paper trading first |

~200 automated tests cover config gates, market math, position sizing, risk
limits, kill switch, executor gating, metrics, cost models, data ingestion
and cleaning, feature leak detection, hand-computed backtest scenarios, and
walk-forward honesty mechanics. The whole pipeline has been validated
end-to-end on labeled synthetic random-walk data — where it correctly
reports that the baseline strategy loses roughly its trading costs, which is
the truthful outcome on edge-free data. **No real-market results exist yet.**

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

### 6. Get data, backtest, walk-forward

```bash
# See what's stored:
python -m trading_bot.data_pipeline.fetch catalog

# Hyperliquid public candles + funding (research data; needs normal internet —
# this repo's development sandbox blocks market-data hosts, a laptop won't):
python -m trading_bot.data_pipeline.fetch hyperliquid --coin BTC --interval 1h \
    --days 200 --funding

# Import MNQ from a CSV (Databento or broker export; see --help for options):
python -m trading_bot.data_pipeline.fetch csv --path mnq_1m.csv --market MNQ \
    --interval 1m --ts-col ts_event --ts-semantics open

# Synthetic random-walk data (machinery validation only, clearly labeled):
python -m trading_bot.data_pipeline.fetch synthetic --market SYNTH --interval 5m

# Backtest a stored dataset (full report + experiment log entry):
python trading_bot/backtest.py --market HL:BTC --interval 1h \
    --strategy simple_momentum --params '{"lookback": 24}' --stop-atr 2.0 --funding

# Rolling walk-forward (params chosen on train only; aggregated OOS report):
python trading_bot/walkforward.py --market HL:BTC --interval 1h \
    --strategy simple_momentum --grid '{"lookback": [12, 24, 48]}' \
    --train-bars 2000 --test-bars 500
```

Data notes:
* **MNQ**: high-quality intraday history is commercial. Databento is the
  recommended source (their continuous-contract symbology handles rollovers;
  otherwise `data_pipeline/continuous.py` builds volume-rolled,
  difference-back-adjusted series from per-contract files). Free sources do
  not provide research-grade MNQ intraday data — do not pretend otherwise.
* **Hyperliquid**: the public info API serves recent candles (~5000 per
  interval, no key needed) and hourly funding history — enough to start, not
  enough for multi-year out-of-sample verdicts. Longer crypto history needs
  an archive source; treat any cross-exchange proxy data with suspicion.
* Raw data is stored untouched in `data/raw/`; cleaning writes an audited
  copy to `data/processed/` and every drop/flag/gap is counted in the
  `CleanReport` printed at fetch time.

### 7. Paper trading (simulated fills — no orders are routed anywhere)

```bash
# Replay a stored dataset through the paper loop (works offline):
python trading_bot/paper_trade.py --market SYNTH --interval 5m \
    --strategy simple_momentum --replay

# Live public market data with simulated fills (HL markets; needs internet):
python trading_bot/paper_trade.py --market HL:BTC --interval 1m \
    --strategy simple_momentum --live-data

# Watch a running/finished session:
python -m trading_bot.monitoring.dashboard --run-dir trading_bot/paper_runs/<ts>

# Emergency stop from outside the process:
touch trading_bot/KILL_SWITCH
```

The paper trader drives the exact same engine as the backtester
(`engine.step(bar)` per completed bar) — signal logic, risk engine, sizing,
stops and cost models are the same objects, and
`tests/test_paper.py::test_paper_equals_backtest_on_identical_bars` proves
it. Each session writes `trades.jsonl` (signal reason, intended vs simulated
entry, stop, target, size, exit, fees, slippage, funding, net P&L),
`state.json` (live status) and `result.json`. A stale data feed trips the
kill switch. Optional webhook alerts: set `alerts.webhook_url` in config.

`live_trade.py` still refuses to run — live execution is Phase 15 and only
becomes relevant after a real edge survives Phases 7-10 on real data plus a
paper-trading period.

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
