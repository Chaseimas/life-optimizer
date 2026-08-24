"""Live/paper monitoring dashboard.

STATUS: not implemented — scheduled for Phase 14 (Monitoring).

Planned design:
* Read-only view over the paper/live trader state: positions, open orders,
  daily P&L vs. limits, kill-switch state, data-feed heartbeat.
* No controls that can bypass risk limits — the dashboard observes, the risk
  engine decides.
"""

from __future__ import annotations


class Dashboard:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Dashboard is scheduled for Phase 14 (monitoring). Nothing is implemented yet."
        )
