"""ML models (setup filters).

STATUS: not implemented — Phase 11, and gated: ML only starts AFTER baseline
strategies exist and have been honestly evaluated (Phases 7-10).

Planned design:
* Question the models answer: "given this setup fired, is it worth taking?"
  — a filter on an existing strategy, not a next-candle price predictor.
* Model ladder: logistic regression -> random forest -> gradient boosting
  (LightGBM/XGBoost). No deep nets until something simpler has earned it.
* Validation is time-series-aware only (models.validation.time_series_splits
  with embargo). Random shuffling of observations across time is banned.
* Every model is compared against its non-ML baseline (models/baseline.py);
  no out-of-sample improvement -> rejected.
"""

from __future__ import annotations


class MLFilterModel:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "ML models are scheduled for Phase 11, and only after baseline "
            "strategies have been established. Nothing is implemented yet."
        )
