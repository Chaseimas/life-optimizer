# Research Findings — Pass 1 (2026-08-27)

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
