"""Look-ahead / leakage detection: the recompute-on-truncation check must
pass causal features and catch leaky ones."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.models.validation import (
    LookaheadError,
    assert_no_lookahead,
    time_series_splits,
)


@pytest.fixture()
def price_frame():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2024-01-01", periods=200, freq="5min", tz="UTC")
    close = 10_000 * np.exp(np.cumsum(rng.normal(0, 0.001, 200)))
    return pd.DataFrame({"close": close}, index=idx)


def test_causal_feature_passes(price_frame):
    assert_no_lookahead(lambda df: df["close"].pct_change().rolling(5).mean(), price_frame)


def test_lagged_feature_passes(price_frame):
    assert_no_lookahead(lambda df: df["close"].shift(1), price_frame)


def test_future_shift_detected(price_frame):
    with pytest.raises(LookaheadError, match="LOOK-AHEAD"):
        assert_no_lookahead(lambda df: df["close"].shift(-1) / df["close"] - 1, price_frame)


def test_centered_rolling_detected(price_frame):
    with pytest.raises(LookaheadError, match="LOOK-AHEAD"):
        assert_no_lookahead(
            lambda df: df["close"].rolling(5, center=True).mean(), price_frame
        )


def test_full_sample_normalization_detected(price_frame):
    # z-scoring with the FULL-SAMPLE mean/std is a classic subtle leak.
    with pytest.raises(LookaheadError, match="LOOK-AHEAD"):
        assert_no_lookahead(
            lambda df: (df["close"] - df["close"].mean()) / df["close"].std(), price_frame
        )


def test_unsorted_index_rejected(price_frame):
    shuffled = price_frame.sample(frac=1.0, random_state=1)
    with pytest.raises(LookaheadError, match="sorted"):
        assert_no_lookahead(lambda df: df["close"], shuffled)


# ---- time-series splits ---------------------------------------------------------
def test_splits_are_ordered_with_embargo():
    splits = time_series_splits(n_samples=100, train_size=50, test_size=10, embargo=5)
    assert len(splits) == 4  # starts at 0, 10, 20, 30
    for train, test in splits:
        assert max(train) < min(test)
        assert min(test) - max(train) - 1 == 5  # embargo gap
        assert len(train) == 50 and len(test) == 10


def test_splits_never_overlap_train_test():
    for train, test in time_series_splits(500, 200, 50, embargo=10):
        assert set(train).isdisjoint(set(test))


def test_splits_reject_bad_sizes():
    with pytest.raises(ValueError):
        time_series_splits(100, 0, 10)
    with pytest.raises(ValueError):
        time_series_splits(100, 50, 10, embargo=-1)
