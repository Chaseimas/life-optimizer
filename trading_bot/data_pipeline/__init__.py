"""Data pipeline: ingestion (Phase 2), cleaning (Phase 3), features (Phase 4).

Canonical format used everywhere downstream: a pandas DataFrame with a
tz-aware UTC DatetimeIndex named ``ts`` holding the bar CLOSE time, and
float64 columns ``open, high, low, close, volume``. See ``frames.py``.
"""
