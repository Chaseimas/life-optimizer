"""Baseline (non-ML) reference models.

STATUS: not implemented — Phase 11 prerequisite work.

Planned design:
* For every ML experiment there must be a corresponding simple baseline
  (e.g. "always take the setup" / the plain rule-based strategy) evaluated
  on the SAME data splits with the SAME costs.
* An ML model is accepted only if it beats its baseline out-of-sample on
  risk-adjusted performance by a statistically meaningful margin — otherwise
  it is rejected, regardless of how sophisticated it is.
"""

from __future__ import annotations


class BaselineModel:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Baseline reference models are scheduled with Phase 11. "
            "Nothing is implemented yet."
        )
