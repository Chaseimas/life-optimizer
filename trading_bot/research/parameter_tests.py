"""Parameter robustness tooling.

Implemented now: ``parameter_neighborhood`` — generates one-at-a-time
perturbations of a parameter set, because a parameter that only works at
exactly one value is a red flag, not a discovery. (If EMA 20 shines while
18/19/21/22 all fail, the strategy is flagged as likely overfit.)

STATUS of the rest: Phase 8+ — sensitivity analysis that runs each neighbor
through the real backtester and compares out-of-sample performance across the
neighborhood, plus experiment-count tracking to keep multiple-testing honest.
"""

from __future__ import annotations

from typing import Iterable


def parameter_neighborhood(params: dict, spreads: dict[str, Iterable]) -> list[dict]:
    """All one-parameter-at-a-time variants of ``params``.

    ``spreads`` maps a parameter name to the alternative values to try, e.g.
    ``{"lookback": [18, 19, 21, 22]}``. The base set is included first.
    """
    unknown = set(spreads) - set(params)
    if unknown:
        raise KeyError(f"spread for unknown parameter(s): {sorted(unknown)}")
    variants: list[dict] = [dict(params)]
    for name, values in spreads.items():
        for v in values:
            if v == params[name]:
                continue
            variant = dict(params)
            variant[name] = v
            variants.append(variant)
    return variants


def sensitivity_report(*args, **kwargs):
    raise NotImplementedError(
        "Parameter sensitivity analysis over real backtests is scheduled for "
        "Phase 8+. Nothing is implemented yet."
    )
