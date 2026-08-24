"""Feature engineering: every feature must pass the leak detector, and the
label helper must FAIL it (that is its job)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.data_pipeline import features as F
from trading_bot.data_pipeline.frames import bars_to_frame
from trading_bot.models.validation import LookaheadError, assert_no_lookahead
from trading_bot.research.experiments import generate_synthetic_bars


@pytest.fixture(scope="module")
def df():
    return bars_to_frame(generate_synthetic_bars(n=400, seed=21, market_id="SYNTH"))


FEATURE_FNS = [
    ("log_return", lambda d: F.log_return(d)),
    ("momentum", lambda d: F.momentum(d, 5)),
    ("rolling_vol", lambda d: F.rolling_vol(d, 10)),
    ("true_range", lambda d: F.true_range(d)),
    ("atr", lambda d: F.atr(d, 14)),
    ("vol_percentile", lambda d: F.vol_percentile(d, 10, 50)),
    ("rel_volume", lambda d: F.rel_volume(d, 10)),
    ("dist_from_rolling_high", lambda d: F.dist_from_rolling_high(d, 20)),
    ("dist_from_rolling_low", lambda d: F.dist_from_rolling_low(d, 20)),
    ("rolling_vwap_dist", lambda d: F.rolling_vwap_dist(d, 20)),
    ("anchored_vwap_dist", lambda d: F.anchored_vwap_dist(d)),
    ("candle_body_frac", lambda d: F.candle_body_frac(d)),
    ("upper_wick_frac", lambda d: F.upper_wick_frac(d)),
    ("lower_wick_frac", lambda d: F.lower_wick_frac(d)),
    ("efficiency_ratio", lambda d: F.efficiency_ratio(d, 10)),
    ("hour_of_day", lambda d: F.hour_of_day(d)),
    ("day_of_week", lambda d: F.day_of_week(d)),
]


@pytest.mark.parametrize("name,fn", FEATURE_FNS, ids=[n for n, _ in FEATURE_FNS])
def test_every_feature_is_leak_free(df, name, fn):
    assert_no_lookahead(fn, df)


def test_full_feature_matrix_is_leak_free(df):
    params = {**F.DEFAULT_FEATURE_PARAMS, "vol_pctile": (10, 50)}
    assert_no_lookahead(lambda d: F.build_features(d, params), df)


def test_label_correctly_fails_the_leak_detector(df):
    """Forward-return labels contain future info BY DESIGN — the leak
    detector must reject them as features."""
    with pytest.raises(LookaheadError):
        assert_no_lookahead(lambda d: F.make_forward_return_label(d, 5), df)


def test_momentum_hand_computed(df):
    m = F.momentum(df, 5)
    i = 100
    expected = df["close"].iloc[i] / df["close"].iloc[i - 5] - 1.0
    assert m.iloc[i] == pytest.approx(expected)
    assert m.iloc[:5].isna().all()


def test_atr_constant_range():
    idx = pd.date_range("2024-01-01", periods=30, freq="5min", tz="UTC")
    d = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=idx,
    )
    a = F.atr(d, 5)
    assert a.iloc[:4].isna().all()          # warmup respected
    assert a.iloc[-1] == pytest.approx(2.0)  # constant TR of 2.0


def test_dist_from_high_is_nonpositive(df):
    d = F.dist_from_rolling_high(df, 20).dropna()
    assert (d <= 1e-12).all()


def test_calendar_features(df):
    h = F.hour_of_day(df)
    dow = F.day_of_week(df)
    assert h.between(0, 23).all()
    assert dow.between(0, 6).all()
    assert h.iloc[0] == df.index[0].hour


def test_label_alignment():
    idx = pd.date_range("2024-01-01", periods=6, freq="1h", tz="UTC")
    d = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0,
         "close": [100.0, 110.0, 121.0, 133.1, 146.41, 161.051], "volume": 1.0},
        index=idx,
    )
    lab = F.make_forward_return_label(d, 1)
    assert lab.iloc[0] == pytest.approx(0.10)   # 100 -> 110 over the NEXT bar
    assert np.isnan(lab.iloc[-1])               # no future for the last row
