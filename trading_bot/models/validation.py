"""Validation utilities: look-ahead detection and time-series-aware splits.

``assert_no_lookahead`` is the automated leakage test the whole research
pipeline relies on. The idea: a feature computed at time t may only depend on
data up to t. So recompute the feature on a TRUNCATED copy of the data — if
any already-known value changes when the future is removed, the feature is
leaking and the check raises.

``time_series_splits`` produces ordered train/test windows (with optional
embargo gap) — never random shuffles of market data across time.
"""

from __future__ import annotations

from typing import Callable, Iterable

import numpy as np
import pandas as pd


class LookaheadError(AssertionError):
    """A feature's past values changed when future data was removed."""


def _as_frame(obj) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, pd.Series):
        return obj.to_frame("value")
    raise TypeError(f"feature_fn must return a Series or DataFrame, got {type(obj)}")


def assert_no_lookahead(
    feature_fn: Callable[[pd.DataFrame], pd.Series | pd.DataFrame],
    frame: pd.DataFrame,
    n_checks: int = 8,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> None:
    """Raise ``LookaheadError`` if ``feature_fn`` uses future information.

    ``frame`` must be indexed by time (monotonic increasing). ``feature_fn``
    must return values aligned to ``frame.index``.
    """
    if not frame.index.is_monotonic_increasing:
        raise LookaheadError("input index must be sorted ascending in time")
    n = len(frame)
    if n < 4:
        raise ValueError("need at least 4 rows to check for look-ahead")

    full = _as_frame(feature_fn(frame))
    if not full.index.equals(frame.index):
        raise LookaheadError("feature output index must match the input index")

    positions = sorted(set(np.linspace(n // 2, n - 2, num=min(n_checks, n // 2), dtype=int)))
    for pos in positions:
        truncated = _as_frame(feature_fn(frame.iloc[: pos + 1]))
        expected = full.iloc[: pos + 1]
        if truncated.shape != expected.shape:
            raise LookaheadError(
                f"feature output shape changed when data was truncated at "
                f"{frame.index[pos]!r}: {truncated.shape} vs {expected.shape}"
            )
        a = expected.to_numpy(dtype=float)
        b = truncated.to_numpy(dtype=float)
        both_nan = np.isnan(a) & np.isnan(b)
        close = np.isclose(a, b, rtol=rtol, atol=atol) | both_nan
        if not close.all():
            bad = np.argwhere(~close)
            row = int(bad[0][0])
            raise LookaheadError(
                "LOOK-AHEAD DETECTED: feature values changed when future data "
                f"was removed (truncated at {frame.index[pos]!r}; first "
                f"mismatch at {frame.index[row]!r}: {a[tuple(bad[0])]!r} vs "
                f"{b[tuple(bad[0])]!r}). This feature uses information that "
                "was not available at decision time."
            )


def time_series_splits(
    n_samples: int,
    train_size: int,
    test_size: int,
    step: int | None = None,
    embargo: int = 0,
) -> list[tuple[range, range]]:
    """Ordered walk-forward (train, test) index windows.

    Train always precedes test; ``embargo`` rows between them are dropped to
    limit leakage from overlapping labels. Never shuffles.
    """
    if min(n_samples, train_size, test_size) <= 0 or embargo < 0:
        raise ValueError("sizes must be positive and embargo >= 0")
    step = step or test_size
    splits: list[tuple[range, range]] = []
    start = 0
    while start + train_size + embargo + test_size <= n_samples:
        train = range(start, start + train_size)
        test_start = start + train_size + embargo
        splits.append((train, range(test_start, test_start + test_size)))
        start += step
    return splits
