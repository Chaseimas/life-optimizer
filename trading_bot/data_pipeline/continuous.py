"""Continuous futures series construction (MNQ contract rollovers).

Individual futures contracts expire quarterly (MNQ: Mar/Jun/Sep/Dec). For
research you need one continuous series, which requires two decisions:

1. WHEN to roll: here, volume crossover — roll when the next contract's
   daily volume exceeds the expiring contract's for ``confirm_days``
   consecutive days (the liquidity actually migrates a few days before
   expiry).
2. HOW to splice: difference ("Panama") back-adjustment — at each roll, the
   price gap between new and old contract at the roll moment is added to all
   EARLIER data, so P&L across the roll is correct. Absolute price levels in
   the distant past become synthetic (documented, expected); returns/P&L are
   what research consumes.

If your vendor already provides a back-adjusted continuous contract
(e.g. Databento's continuous symbology), prefer that and skip this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_bot.data_pipeline.frames import DataError, ensure_canonical


@dataclass(frozen=True)
class RollEvent:
    ts: pd.Timestamp          # first bar traded on the NEW contract
    from_contract: str
    to_contract: str
    price_offset: float       # new_price - old_price at the roll moment


def detect_roll_ts(
    front: pd.DataFrame,
    back: pd.DataFrame,
    *,
    confirm_days: int = 2,
) -> pd.Timestamp | None:
    """First timestamp at which ``back``'s daily volume has exceeded
    ``front``'s for ``confirm_days`` consecutive overlapping days."""
    f_vol = ensure_canonical(front)["volume"].resample("1D").sum()
    b_vol = ensure_canonical(back)["volume"].resample("1D").sum()
    both = pd.concat({"front": f_vol, "back": b_vol}, axis=1).dropna()
    if both.empty:
        return None
    ahead = both["back"] > both["front"]
    streak = 0
    for day, is_ahead in ahead.items():
        streak = streak + 1 if is_ahead else 0
        if streak >= confirm_days:
            return day + pd.Timedelta(days=1)  # roll from the next day's first bar
    return None


def build_continuous(
    contracts: list[tuple[str, pd.DataFrame]],
    *,
    roll_ts: dict[str, pd.Timestamp] | None = None,
    confirm_days: int = 2,
) -> tuple[pd.DataFrame, list[RollEvent]]:
    """Stitch per-contract frames (ordered by expiry) into one
    difference-back-adjusted continuous frame.

    ``roll_ts`` optionally fixes the roll timestamp per FROM-contract id;
    otherwise volume crossover decides. Returns (frame, roll events).
    """
    if not contracts:
        raise DataError("no contracts supplied")
    frames = [(cid, ensure_canonical(df)) for cid, df in contracts]

    segments: list[pd.DataFrame] = []
    events: list[RollEvent] = []
    cursor_start: pd.Timestamp | None = None

    for i, (cid, df) in enumerate(frames):
        is_last = i == len(frames) - 1
        if is_last:
            seg = df.loc[cursor_start:] if cursor_start is not None else df
            segments.append(seg)
            break

        next_cid, next_df = frames[i + 1]
        rts = (roll_ts or {}).get(cid) or detect_roll_ts(df, next_df, confirm_days=confirm_days)
        if rts is None:
            raise DataError(
                f"cannot determine roll from {cid} to {next_cid}: no overlapping "
                "volume data and no explicit roll_ts provided"
            )
        seg = df.loc[cursor_start:rts]
        seg = seg[seg.index < rts]
        if seg.empty:
            raise DataError(f"contract {cid} contributes no bars before its roll at {rts}")

        old_before = df[df.index < rts]
        new_after = next_df[next_df.index >= rts]
        if new_after.empty:
            raise DataError(f"contract {next_cid} has no bars at/after roll {rts}")
        # The offset is the calendar spread measured at the SAME timestamp on
        # both contracts (the last common bar before the roll) — comparing
        # across different times would fold market drift into the adjustment.
        common = df.index.intersection(next_df.index)
        common_before = common[common < rts]
        if len(common_before):
            t_star = common_before[-1]
            offset = float(next_df.loc[t_star, "close"] - df.loc[t_star, "close"])
        else:
            # No overlap (explicit roll on disjoint data): boundary difference
            # is the only option; it conflates drift with basis — flagged.
            offset = float(new_after["close"].iloc[0] - old_before["close"].iloc[-1])

        events.append(RollEvent(ts=rts, from_contract=cid, to_contract=next_cid,
                                price_offset=offset))
        segments.append(seg)
        cursor_start = rts

    # Difference adjustment: segment i (all data before roll i) is shifted by
    # the sum of the offsets of roll i and every later roll, so the spliced
    # series is jump-free and P&L across every roll is preserved.
    adjusted = [s.copy() for s in segments]
    for i, seg in enumerate(adjusted[:-1]):
        offset_sum = sum(e.price_offset for e in events[i:])
        for col in ("open", "high", "low", "close"):
            seg[col] = seg[col] + offset_sum

    out = pd.concat(adjusted)
    if out.index.has_duplicates:
        raise DataError("continuous series has duplicate timestamps after splicing")
    return ensure_canonical(out, already_sorted=False), events
