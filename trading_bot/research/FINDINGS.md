# Research Findings

# Pass 4 — $400/Day Robustness & Edge Discovery (2026-08-27)

**Overall system verdict: D — no validated edge exists yet.** Conditionally
— IF the strongest candidate survives its pre-registered out-of-sample
evaluation — the answer becomes B: $400/day appears achievable only with
more capital (~$750k at measured performance). $400/day on $100k under
current evidence sits between C and impossible: sizing up the best candidate
DEGRADED it. All Pass-1–3 conclusions stand unmodified.

## The target's mathematics (research/target_math.py, tested)

$400/day on $100k = 0.40%/day average. At 1% daily P&L volatility that is an
annualized Sharpe of 7.6 (no known fund sustains this); at 2% vol, 3.8
(world-class). Per trade: 2 trades/day at 0.5% risk requires +0.40R
expectancy after costs; good validated systematic strategies sustain
+0.05R–0.15R. **The dollar target is fundamentally a Sharpe claim, and the
honest levers are capital and validated trade frequency — never leverage.**

## New families searched (all logged `pass4 exploratory`; 46 experiments)

Three genuinely different return sources were added, tested and controlled
with the standard four-round battery. Same 200-day window as Passes 1–2 —
no new data has arrived — so multiple-comparisons debt now spans ~8
families and the acceptance bar rose accordingly (Bonferroni across ~25
cells roughly triples the required trade count for significance).

* **ETH/BTC spread (market-neutral, two-leg costs): EDGE REJECTED** at
  Round 1 — PF 0.13–0.40, ~−$10k, killed. Relative value cannot pay double
  execution costs at this frequency.
* **Volatility-squeeze breakout: EDGE REJECTED** at Round 2 — BTC OOS
  +$0.8k (Sharpe 0.38 = noise), ETH −$4.0k, SOL −$5.7k, unstable params.
* **Funding-rate carry: the strongest candidate this program has produced**
  (details below) — BTC survives everything except sample size; ETH and SOL
  versions FAILED walk-forward (recorded; 1-of-3 markets is a selection-risk
  flag, not a footnote).

## funding_carry HL:BTC 1h — the surviving candidate

Signal: rank trailing 24h funding within its 30-day history; short beyond
the 90th percentile (fade crowded longs), long below the 10th, flat near
median. ~0.25 trades/day, so costs are almost irrelevant (robust to 2× fees
+ 3× slippage: still +$9.1k full-period).

| test | result |
|---|---|
| Walk-forward OOS (taker) | +$5.6k, PF 1.73, Sharpe 1.70, maxDD 3.8%, 30 trades |
| Walk-forward OOS (maker cons/base) | +$6.1k / +$6.1k, PF 1.82, Sharpe ~1.8 |
| Chosen params per window | **(0.9, 24) in all 5 windows, all 3 exec models** — the only perfectly stable parameters ever observed here |
| Long / short (full period) | +$6.3k / +$5.3k — first candidate profitable on BOTH sides |
| Regime thirds | +$5.4k (flat), **+$7.6k (BTC −13% bear)**, −$0.8k (+25% melt-up) — inverse regime profile to everything else tested |
| Beta control, mixed | **98% (taker), 96% (maker) — SEPARATES** |
| Beta control, per side | long 92%, short 92–94% — below the 95% bar |
| Bootstrap MC (30 OOS trades) | median +$4.6k, p5 −$5.9k, **P(≤0)=29%** |
| Funding actually collected | ~$0.5k of ~$11.6k — the P&L is positioning-fade, not carry income |

**Verdict: INSUFFICIENT EVIDENCE** — 30 OOS trades, one market of three,
per-side controls short of the bar, one 200-day window. Frozen as
`funding_carry_btc_1h_p4` (hash-pinned, source-pinned) with pre-registered
evaluation on **2026-11-30** (min 20 OOS trades; positive under both maker
scenarios; mixed control ≥95% AND each side ≥90%).

## $400/day sizing scenarios (walk-forward OOS streams, per-scenario limits)

Limits scale with risk (daily loss = 3× per-trade risk); every scenario
re-ran the full walk-forward — no linear extrapolation.

| candidate | scenario | OOS mean $/day | median $/day | worst day | maxDD | P(loss 60d) | P(avg≥$400/d, 1y) | capital for $400/d |
|---|---|---|---|---|---|---|---|---|
| funding_carry BTC (taker) | cons 0.25% | 34 | 0 | −752 | 2.0% | 23% | ~0% | $1.17M |
| funding_carry BTC (taker) | base 0.50% | **53** | 0 | −1,501 | 3.8% | 27% | ~0% | **$749k** |
| funding_carry BTC (taker) | aggr 1.00% | **19** | 0 | −2,532 | 5.4% | **44%** | ~0% | $2.07M |
| ORB ETH 15m (maker, beta-suspect) | cons 0.25% | 221 | −263 | −580 | 3.2% | 17% | 6.7% | $181k |
| ORB ETH 15m (maker, beta-suspect) | base 0.50% | 183 | −263 | −1,155 | 3.7% | 25% | 4.8% | $218k |
| ORB ETH 15m (maker, beta-suspect) | aggr 1.00% | 207 | −290 | −1,613 | 3.9% | 22% | 7.1% | $194k |

Two structural findings: **(1) sizing up degrades the defensible candidate**
(aggressive OOS net fell to $2.0k from $5.6k — larger positions interact
with the daily-loss halts; the backtest "supporting" more size
mathematically did not survive actually running it); **(2) the ORB stream's
median day is NEGATIVE** — its average is a few large wins, exactly the
$400-on-lucky-days shape the target explicitly excludes.

## Portfolio

fc-BTC × orb-ETH baseline OOS daily correlation on the 20 overlapping days:
**−0.44** — the first genuinely promising diversification signal in the
program (opposite regime profiles). But 20 days is too short: the formal
verdict on current data is CONCENTRATE (combined Sharpe 1.65 vs 1.61, not
meaningful). Re-test when both frozen streams have months of OOS history.

## Final ranking (every candidate, exactly one verdict)

| # | strategy / market / tf | OOS exp/trade | PF | Sharpe | maxDD | beta ctrl | verdict |
|---|---|---|---|---|---|---|---|
| 1 | funding_carry HL:BTC 1h (all exec) | +$187 | 1.73–1.82 | 1.7–1.8 | 3.8% | mixed 96–98% ✓, sides 92–94% ✗ | **INSUFFICIENT EVIDENCE** (frozen, eval 2026-11-30) |
| 2 | ORB HL:ETH 15m maker | +$122 | 1.46 | 1.9 | 3.7% | mixed 96–98% ✓, long-only 93% ✗ | **INSUFFICIENT EVIDENCE** (frozen, eval 2026-10-01) |
| 3 | vol_breakout (BTC/ETH/SOL 1h) | +$27 BTC / neg | ≤1.09 | ≤0.38 | — | not reached | **EDGE REJECTED** |
| 4 | funding_carry HL:ETH / HL:SOL 1h | −$110 / −$135 | 0.71 / 0.63 | neg | — | not reached | **EDGE REJECTED** |
| 5 | ETH/BTC spread (MR + momentum) | ≈−$95 | 0.13–0.40 | neg | killed | not reached | **EDGE REJECTED** |
| 6 | simple_momentum (all markets/tf) | scenario-unstable | ~0.9 | ~0 | — | n/a | **EDGE REJECTED** (Pass 2) |
| 7 | zscore_mean_reversion, rolling_vwap, regime_gated_momentum, ORB non-ETH | negative | <1 | neg | — | n/a | **EDGE REJECTED** (Passes 1–2) |

## The Most Important Question, answered from the evidence

**"If I gave this system $100,000 today: the most defensible expected NET
daily profit is $0**, because no candidate has cleared every pre-registered
control. The best *unconfirmed* estimate is **+$53/day** (funding-carry
baseline OOS mean) with a ~27% probability of being down over any 60-day
stretch and a median day of $0. **Realistic maximum drawdown: the 10%
kill-switch bound** (measured OOS drawdown 3.8%; bootstrap p95 ≈ $7k on
30 trades). **Distance from a statistically credible $400/day system: two
multiplicative gaps.** Evidence gap: the candidate needs its pre-registered
Nov-30 OOS evaluation passed (~20+ fresh trades, controls ≥ bars) — roughly
3+ months of untouched data, unavoidable at 0.25 trades/day. Economics gap:
even then, $400/day needs ≈**$749k of capital** at this quality, or ~4–8
validated, genuinely uncorrelated streams of similar quality on $100–200k —
of which today there exist zero validated and two candidates with one
promising −0.44 correlation reading. $400/day on $100k alone would require
~0.4%/day = Sharpe ≳ 4–7 at observed volatilities, which nothing in 242
logged experiments comes close to supporting."**

No live trading is authorized.

---

# Pass 3 — Evidence Accumulation Infrastructure (2026-08-27)

**No new performance claims are made in this pass, by design.** Pass 3 built
the machinery for accumulating clean, genuinely independent evidence on the
Pass-2 candidate without contaminating the experiment. The Pass-2 verdict
stands unchanged: **INSUFFICIENT EVIDENCE — no tradeable edge demonstrated.
No live trading is authorized.**

## The frozen candidate (exact definition)

`orb_eth_15m_maker_p2`, defined machine-readably in
`research/frozen.py` and hash-pinned in `research/frozen_hashes.json` plus
the test suite (sha256 `1798a7b1d3482d94…`):

* opening_range_breakout {range_start_hour: 0, range_minutes: 60,
  buffer_frac: 0.0, flat_hour: 23} on HL:ETH @ 15m
* maker entries (both Pass-2 fill scenarios frozen verbatim: conservative =
  through-only + 0.5 bp adverse selection, lifetime 2; baseline = prob 0.5 +
  0.25 bp, lifetime 3), taker exits, ATR(14)×2 stops
* risk limits snapshot frozen (daily loss $1,500; 0.5%/trade; 10% drawdown
  kill switch; $60k exposure cap)
* in-sample boundary: everything through 2026-08-27 19:00 UTC;
  **OOS starts 2026-08-28 00:00 UTC**
* pre-registered evaluation: **2026-10-01** (fallback 2026-11-01 if < 30 OOS
  trades), criteria fixed in advance: positive OOS net under BOTH scenarios,
  ≥ 30 OOS trades, long-only random-entry control ≥ 95th percentile
  (200 reps, seed 2026)

Strategy source (`strategies/breakout.py`) and fill-model source
(`backtesting/maker.py`) are hash-pinned; editing either voids frozen
evaluations until the freeze is explicitly renewed. Every frozen-evaluation
invocation is logged; runs before the evaluation date are labeled EARLY PEEK
in the output and the log, so peeking is visible rather than possible to
deny.

## Paper-trading methodology

`paper_trade.py --frozen orb_eth_15m_maker_p2 --live-data` runs the frozen
candidate on live public 15m data through the SAME engine as every backtest
(simulated maker fills; no orders touch any venue). Overrides are refused —
the frozen definition cannot drift. Each session writes a full audit trail:
`frozen_candidate.json` (the definition it ran), `events.jsonl` (every
order placed / filled / partial / expired-missed / canceled-by-risk /
denied placement, with bar time and wall time), `trades.jsonl` (entries,
exits, stops, fees, slippage, funding, net P&L, reasons), `state.json`, and
`result.json` — all stamped mode=PAPER. Paper fills are simulated fills and
are never presentable as real fills (audited).

## Data-accumulation methodology

The public API retains only ~5,000 candles/interval, so history exists only
if we keep it. `fetch accumulate` merges each fetch append-only:
**previously stored bars are immutable** — if the API later returns
different values for a stored bar, the discrepancy is detected and reported
and the original is kept (tested, including the adversarial case). Every
fetch appends to the dataset's `fetch_history` metadata (when, what span,
new/overlap/mismatch counts, coverage). Duplicates, off-grid timestamps and
gaps are detected; gaps are reported, never filled. Raw and processed stay
separate; contamination of completed experiments is prevented by the
immutability of old rows plus the frozen OOS timestamp boundary.

## MNQ pipeline status

Groundwork only, fully separate from the crypto candidate: Databento-shaped
import path with tick-grid validation and DST-aware CME session filtering
(`fetch mnq --path …`), documented cost assumptions requiring broker
verification, and a session-anchored (08:30 America/Chicago, DST-tested)
opening-range utility for FUTURE exploratory MNQ work — no MNQ strategy has
been run, and the maker fill model's crypto assumptions are explicitly not
assumed valid for CME. Blocked on purchasing Databento history.

## Integrity automation

`python -m trading_bot.research.integrity` audits: frozen definition +
source hashes, experiment-log id uniqueness, post-freeze parameter tuning on
the candidate's market/interval (unlabeled exploratory work is flagged),
early-peek accounting, cost transparency of pass-3+ records, per-strategy
experiment counts (selection-bias denominator), and PAPER stamping of paper
artifacts. The live audit of this repository is itself a test — the suite
fails if the repo stops passing its own integrity checks. Current status:
CLEAN.

## Next evaluation

On or after **2026-10-01**: accumulate data, then
`python -m trading_bot.research.frozen_eval --candidate orb_eth_15m_maker_p2`.
Until then: accumulate (ideally at least weekly, since 15m depth is ~52
days) and let the paper session run. **Do not tune. Do not peek for
comfort. No live trading is authorized.**

---

# Pass 2 — Maker Execution (2026-08-27)

**VERDICT: INSUFFICIENT EVIDENCE.** No tradeable edge has been demonstrated.
One candidate (ORB-15m on ETH under maker execution) survived walk-forward,
scenario stress, and two of three beta controls — but the decisive long-only
control came in at the 93rd percentile, below the pre-declared 95% bar, on
52 days of one parabolic regime in one market. That is a candidate worth
re-testing on more data, not an edge.

## 1. What was built

Maker (limit-order) entry execution in the existing engine
(`backtesting/maker.py` + `BacktestConfig.maker`; `maker=None` keeps the
original taker path bit-for-bit — verified by the untouched existing suite).
Entries become resting limit orders placed at the next bar's open ± a
configurable offset; **exits stay taker by design** (a protective stop that
might not fill is not a stop). Round-trip cost is therefore ~7 bps
(1.5 maker + 4.5 taker + 1 exit slippage), not the 3 bps fee-table fantasy.
20 new tests cover fills, misses, expiry, partials, adverse selection,
same-bar stops, risk/kill-switch interaction, and determinism (277 total).

## 2. How fills are modeled, and what OHLC cannot honestly provide

Documented in full in `backtesting/maker.py`. Three assumptions are
unavoidable with OHLC-only data, and each is an explicit parameter, not a
hidden default: queue position is unknowable (fill modes: "through" = only
when price sweeps past the limit; "touch" = optimistic upper bound, never
used for conclusions; "prob" = seeded coin-flip on touch); adverse selection
beyond the structural effect is charged as an explicit per-fill cost in bps
of notional; intrabar path is unknown (same-bar stop after fill is assumed —
the conservative direction). Three named scenarios: conservative / baseline /
optimistic. All conclusions come from the first two.

## 3. Taker vs maker — broad sweep (all 5 strategies × 5 datasets × 4 models)

**Maker execution does not rescue losing strategies.** 19 of 25 cells stay
negative under both honest scenarios. Fill rates ran 88–100%: at 15m/1h
crypto volatility a passive limit at the open is almost always touched, so
maker ≈ taker − ~4 bps, with a small missed-trade effect. The cost thesis
from Pass 1 ("gross-positive momentum might survive lower fees") is
**rejected**: momentum-1h stayed unprofitable or scenario-unstable
(BTC: +$2.4k conservative but −$1.5k baseline — sign flips with the fill
assumption = noise).

## 4–7. Which strategies improved / survived

Improved but still losing: mean-reversion and VWAP variants (~$1–5k less bad
— fee savings, nothing more). ORB-15m **BTC failed** scenario robustness
(+$2.5k conservative, +$6 baseline: the extra fills granted by generous
assumptions are precisely the adverse-selected ones). **ORB-15m ETH is the
sole survivor**: walk-forward OOS +$5.8k/+$5.9k (conservative/baseline),
PF 1.46, Sharpe ~1.9, 48 OOS trades, stable chosen params (60-min range).

## 8. Does maker execution change the beta-control conclusion?

Partially — and not enough. Full-fidelity random-entry controls (same
engine, maker model, stops, sizing, costs, matched directions and holding
times, 200 reps):

| control | actual percentile | bar |
|---|---|---|
| mixed, maker baseline | 97% | ≥95% |
| mixed, maker conservative | 98% | ≥95% |
| **long-only** (the side with all the P&L) | **93%** | **≥95% — FAILED** |
| hour-matched mixed | 96% | ≥95% |

The mixed controls pass partly because random shorts are destroyed in a
+42.8% window while the strategy's shorts broke even (−$175 on 38 trades).
The long side alone — +$10.8k of the +$10.6k total — does **not** separate
from random long entries at the required level. Pass 1's conclusion
(taker, long-only control at 67%) improves to 93% under maker, but the bar
is 95% and the sample is 45 trades in one regime.

## 9. Sensitivity to worse fills

The ETH result was robust across the stress grid: adverse selection up to
2 bps (net $10.6k → $9.8k), lifetime 1–5 bars, partial fills 50%, fill
probability 0.25–0.75, three RNG seeds — all stayed in the $9.8–11.3k band.
(A 5 bps limit offset *raised* net to $12.1k at an 88% fill rate; noted as
an observation only — selecting it post-hoc is exactly the cherry-picking
this protocol bans.)

## 10. Monte Carlo (bootstrap, OOS trades, maker baseline)

48 OOS trades: median +$4.4k, p5 −$9.6k, p95 +$27.0k,
**P(total ≤ 0) = 33.8%**, p95 drawdown $10.9k, p95 losing streak 16.
Top-3 wins ($16.8k) still exceed total net ($10.6k): outlier-dependent.

## 11. Explicit conclusion

**INSUFFICIENT EVIDENCE. No tradeable edge has been demonstrated.**
For: survived walk-forward under both honest fill scenarios; robust to
execution-assumption stress; 96–98% on mixed/hour-matched controls.
Against: long-only control 93% (< 95% bar); one market; 52 days; one
parabolic +43% regime; outlier-dependent; P(≤0) ≈ 34%.

What would resolve it, in order of value: (1) more 15m history — the public
archive deepens daily, so re-running this exact protocol in 4–8 weeks adds
true out-of-sample data including, eventually, a non-bull regime; (2) the
same protocol on MNQ (Databento) for an uncorrelated venue and a
session-anchored range; (3) forward paper trading of ORB-15m-ETH with maker
entries — zero-risk true out-of-sample evidence via the existing paper
trader. Do NOT trade this live; nothing here meets the bar.

---

# Pass 1 (2026-08-27)

**Verdict: NO TRADEABLE EDGE FOUND YET.** One candidate looked good through
two rounds of testing and was then killed by a beta control. That is the
system working, not failing — the pipeline's job is to kill false positives
before they cost money.

## Data

Real Hyperliquid public market data (taker fees 4.5 bps/side, 1 bp slippage
per side, hourly funding where applicable):

| dataset | span | bars | note |
|---|---|---|---|
| BTC, ETH, SOL @ 1h | 2026-02-08 → 2026-08-27 (200 days) | 4,801 each | API retains ~5,000 candles/interval |
| BTC, ETH @ 15m | 2026-07-06 → 2026-08-27 (~52 days) | 5,012 each | same cap → ~52 days max |

Market context — **everything rose during this window**: BTC +12.8%,
ETH +18.2%, SOL +22.1% (buy-and-hold Sharpe ≈ 0.5–0.6). Every long-side
result below must be read against that drift.

## Round 1 — all 5 baselines × 3 markets, default params (in-sample)

14 of 15 cells at 1h **lost money**; every BTC/ETH/SOL 1h run eventually hit
the 10% drawdown kill switch. At 15m, everything was cost-crushed except
opening-range breakout, positive on both BTC (+$3.2k, PF 1.17) and ETH
(+$6.4k, PF 1.28). Momentum showed gross-positive signal at 1h eaten by
costs (BTC: ~+$8k gross vs ~$14.5k costs).

## Round 2 — walk-forward (train-only selection, aggregated OOS)

- **Momentum 1h: REJECTED.** BTC +$762 OOS (noise), ETH −$3.8k, SOL −$11k.
  Round 1's ETH momentum profit did not survive → parameter luck. Chosen
  lookbacks were unstable across windows (12 ↔ 168).
- **ORB 1h: REJECTED** on all three markets (−$7.4k to −$9k OOS).
- **ORB 15m: survived.** BTC +$2.2k OOS (PF 1.19, Sharpe 1.34, 52 trades),
  ETH +$4.1k OOS (PF 1.31, Sharpe 1.36, 49 trades).

## Round 3 — stressing the ORB-15m candidate

- Parameter surface: broadly positive in the 30–90 min range region
  (17/24 BTC, 13/24 ETH cells positive), negative at ≥120 min on ETH.
  Not a single-spike overfit, but not uniform either.
- **All profit is long-side.** BTC: long +$4.8k / short −$3.1k.
  ETH: long +$6.3k / short −$1.2k. In a rising market, that pattern is the
  signature of beta, not edge.
- **Outlier-dependent:** top-3 wins = 4.6× (BTC) and 2.9× (ETH) of total
  net; median day negative; ~35% profitable days.
- Bootstrap Monte Carlo on OOS trades: **P(total ≤ 0) ≈ 39–41%.**
- BTC/ETH ORB P&L correlation 0.77 → the two markets are ~1.5 pieces of
  evidence, not 2. Portfolio verdict: CONCENTRATE (no diversification gain).

## Round 4 — beta control (the kill shot)

For each actual ORB long trade, 2,000 resamples of random long entries with
identical holding period, size, and costs:

| market | actual long P&L | random-long null (p5 / p50 / p95) | actual percentile |
|---|---|---|---|
| BTC | +$4,795 | −$5.8k / +$0.6k / +$8.6k | **83%** |
| ETH | +$6,329 | −$6.1k / +$3.4k / +$17.1k | **67%** |

Random long entries made comparable money. **ORB-15m's profit is consistent
with market drift, not entry timing.** Candidate rejected as an edge claim.

## ML filter (protocol demonstration on the largest sample)

Gradient boosting as a setup filter on momentum-1h-BTC trades (155 train /
104 test, time-ordered): **REJECT** — keeps only 10% of test trades and the
kept trades still have negative expectancy. The accept/reject machinery
behaves correctly on real data.

## Process findings (already fixed in config)

1. `max_daily_loss` below ~3× per-trade risk halts the day on any single
   loss — it was measuring noise, not risk. Raised to $1,500 on $100k.
2. A global units cap (`max_position_size: 3`) silently shrank ETH to ~$6k
   and SOL to ~$300 notional, invalidating cross-market comparison. The
   dollar exposure cap is now the binding constraint; units cap = backstop.
3. The 10% drawdown kill switch truncates losing backtests early (correct
   for capital, but note it when comparing runs' spans).

## What could actually change the picture (next passes)

1. **Cost structure is the dominant enemy.** Taker round trip ≈ 11 bps.
   Hyperliquid maker fees are 1.5 bps/side → a limit-entry execution model
   could cut round-trip costs ~2–4×, flipping the sign of marginally-losing
   gross-positive strategies (momentum 1h). This requires HONEST fill-risk
   modeling (maker orders don't always fill), which the backtester's Phase-5
   design anticipated but does not yet implement. Highest-value next build.
2. **More history.** The public API caps ~5,000 candles/interval. Longer
   15m/1h history needs an archival source; until then, every conclusion is
   about ONE (bullish) regime. Re-fetch periodically — 15m depth grows daily.
3. **MNQ data** (Databento) for a genuinely uncorrelated asset class and
   session-anchored (not UTC-anchored) opening-range work.
4. Regime conditioning: run the sweeps split by realized-vol regime.
5. Time-of-day: ORB anchored at US equity open instead of UTC midnight.

## $400/day status

Nothing to scale. No positive out-of-sample expectancy survived controls, so
capital-requirement math ($80k–$400k depending on daily return) remains
arithmetic, not a plan. 71 experiments logged to `experiment_records.jsonl`.
