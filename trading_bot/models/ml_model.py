"""Setup-filter models (Phase 11).

A ``SetupFilter`` answers one question: given the features at a signal bar,
is this setup worth taking? It is a FILTER on an existing baseline strategy,
never a price predictor, and it is only ever accepted if it beats the
unfiltered baseline out-of-sample (research/ml_experiment.py enforces that).

Model ladder — simplest first, on purpose:
    logistic -> random_forest -> gradient_boosting
No deep networks until something on this ladder has earned the complexity.

Time discipline lives in the experiment runner (time-ordered train/test
splits, never shuffled across time); this class is just the estimator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MODEL_LADDER = ("logistic", "random_forest", "gradient_boosting")


def _build_estimator(model: str, random_state: int):
    # sklearn imported lazily so the rest of the system works without it.
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if model == "logistic":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("clf", LogisticRegression(max_iter=2000, random_state=random_state)),
            ]
        )
    if model == "random_forest":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("clf", RandomForestClassifier(
                    n_estimators=300, min_samples_leaf=20, random_state=random_state,
                    n_jobs=-1,
                )),
            ]
        )
    if model == "gradient_boosting":
        # Handles NaN natively; shallow and regularized by default sizing.
        return HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.1, max_iter=200, random_state=random_state,
        )
    raise ValueError(f"unknown model {model!r}; ladder: {MODEL_LADDER}")


class SetupFilter:
    def __init__(self, model: str = "logistic", threshold: float = 0.55,
                 random_state: int = 42):
        if not (0.0 < threshold < 1.0):
            raise ValueError("threshold must be in (0, 1)")
        self.model_name = model
        self.threshold = threshold
        self.random_state = random_state
        self._est = _build_estimator(model, random_state)
        self._fitted = False
        self._columns: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "SetupFilter":
        if len(X) != len(y):
            raise ValueError("X and y length mismatch")
        if y.nunique() < 2:
            raise ValueError(
                "training labels are single-class (all wins or all losses) — "
                "nothing to learn; do not force a model onto this data"
            )
        self._columns = list(X.columns)
        self._est.fit(X.to_numpy(dtype=float), y.to_numpy(dtype=bool))
        self._fitted = True
        return self

    def _check(self, X: pd.DataFrame) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("SetupFilter used before fit()")
        if list(X.columns) != self._columns:
            raise ValueError("feature columns differ from training columns")
        return X.to_numpy(dtype=float)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """P(setup is a winner) per row."""
        arr = self._check(X)
        proba = self._est.predict_proba(arr)
        classes = list(self._est.classes_)
        return proba[:, classes.index(True)]

    def decide(self, X: pd.DataFrame) -> np.ndarray:
        """True = take the setup."""
        return self.predict_proba(X) >= self.threshold

    def feature_importances(self) -> pd.Series | None:
        """Best-effort interpretability; None when the estimator offers none."""
        if not self._fitted:
            return None
        est = self._est
        clf = est.named_steps["clf"] if hasattr(est, "named_steps") else est
        if hasattr(clf, "feature_importances_"):
            vals = clf.feature_importances_
        elif hasattr(clf, "coef_"):
            vals = np.abs(clf.coef_[0])
        else:
            return None
        return pd.Series(vals, index=self._columns).sort_values(ascending=False)
