# Research Findings

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
