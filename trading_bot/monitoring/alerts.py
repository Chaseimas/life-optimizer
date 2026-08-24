"""Alerting (kill-switch trips, risk-limit hits, data-feed failures).

STATUS: not implemented — scheduled for Phase 14 (Monitoring).

Planned design:
* Alert sinks (log, email, webhook) behind one ``AlertSink`` interface.
* The kill switch and risk manager publish events; sinks fan out.
* Alerts are best-effort and NEVER a substitute for the kill switch —
  trading halts first, humans get told second.
"""

from __future__ import annotations


class AlertSink:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Alerting is scheduled for Phase 14 (monitoring). Nothing is implemented yet."
        )
