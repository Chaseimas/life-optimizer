"""Alerting (Phase 14).

Alerts OBSERVE; they never control. The kill switch and risk manager halt
trading first — alerts tell humans afterwards. A failing alert sink must
never take the trading loop down, so every send is best-effort.

Sinks:
* ``LogAlertSink`` — always on, writes to the trading_bot log.
* ``WebhookAlertSink`` — optional JSON POST (configure ``alerts.webhook_url``
  in config.yaml; works with Slack-compatible webhook receivers).
* ``CollectingSink`` — in-memory, for tests and dashboards.
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from trading_bot.monitoring.logging import get_logger

log = get_logger("alerts")

LEVELS = ("info", "warning", "critical")


@dataclass(frozen=True)
class Alert:
    ts: str
    level: str
    event: str
    detail: str


class AlertSink(ABC):
    @abstractmethod
    def send(self, alert: Alert) -> None: ...


class LogAlertSink(AlertSink):
    def send(self, alert: Alert) -> None:
        fn = {"info": log.info, "warning": log.warning, "critical": log.critical}[alert.level]
        fn("ALERT [%s] %s", alert.event, alert.detail)


class CollectingSink(AlertSink):
    def __init__(self):
        self.alerts: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.alerts.append(alert)


class WebhookAlertSink(AlertSink):
    def __init__(self, url: str, timeout: float = 5.0):
        if not url.startswith(("http://", "https://")):
            raise ValueError("webhook url must be http(s)")
        self.url = url
        self.timeout = timeout

    def send(self, alert: Alert) -> None:
        body = json.dumps(
            {"ts": alert.ts, "level": alert.level, "event": alert.event,
             "detail": alert.detail,
             "text": f"[{alert.level.upper()}] {alert.event}: {alert.detail}"}
        ).encode()
        req = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=self.timeout,
                               context=ssl.create_default_context())


@dataclass
class AlertManager:
    sinks: list[AlertSink] = field(default_factory=list)

    def notify(self, level: str, event: str, detail: str = "") -> None:
        if level not in LEVELS:
            raise ValueError(f"level must be one of {LEVELS}")
        alert = Alert(
            ts=datetime.now(timezone.utc).isoformat(), level=level,
            event=event, detail=detail,
        )
        for sink in self.sinks:
            try:
                sink.send(alert)
            except Exception as e:  # alerts must never break the trading loop
                log.error("alert sink %s failed: %s", type(sink).__name__, e)


def build_alert_manager(config) -> AlertManager:
    """LogAlertSink always; WebhookAlertSink when configured."""
    sinks: list[AlertSink] = [LogAlertSink()]
    url = str((config.raw.get("alerts") or {}).get("webhook_url") or "").strip()
    if url:
        try:
            sinks.append(WebhookAlertSink(url))
        except ValueError as e:
            log.error("invalid alerts.webhook_url ignored: %s", e)
    return AlertManager(sinks)
