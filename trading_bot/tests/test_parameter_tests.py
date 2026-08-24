"""Parameter neighborhood generation for overfitting checks."""

from __future__ import annotations

import pytest

from trading_bot.research.parameter_tests import parameter_neighborhood


def test_neighborhood_includes_base_and_variants():
    base = {"lookback": 20, "threshold": 0.0}
    variants = parameter_neighborhood(base, {"lookback": [18, 19, 21, 22]})
    assert variants[0] == base
    lookbacks = sorted(v["lookback"] for v in variants)
    assert lookbacks == [18, 19, 20, 21, 22]
    # threshold untouched in every variant
    assert all(v["threshold"] == 0.0 for v in variants)


def test_one_at_a_time_perturbation():
    base = {"a": 1, "b": 2}
    variants = parameter_neighborhood(base, {"a": [3], "b": [4]})
    # base + one 'a' variant + one 'b' variant; never both changed at once
    assert len(variants) == 3
    assert {"a": 3, "b": 2} in variants
    assert {"a": 1, "b": 4} in variants
    assert {"a": 3, "b": 4} not in variants


def test_duplicate_of_base_value_skipped():
    variants = parameter_neighborhood({"a": 1}, {"a": [1, 2]})
    assert len(variants) == 2


def test_unknown_parameter_rejected():
    with pytest.raises(KeyError, match="unknown parameter"):
        parameter_neighborhood({"a": 1}, {"zzz": [1]})
