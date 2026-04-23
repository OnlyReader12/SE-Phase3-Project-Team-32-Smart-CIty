"""
BaseEngine — Template Method Pattern
--------------------------------------
Defines the fixed analysis pipeline.
Subclasses override `get_rules()` only — the core loop never changes.

Open/Closed Principle:
  - Closed: This file is never modified to add new analysis capabilities.
  - Open:   New engines extend BaseEngine; new rules extend AnalysisRule.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .middleware_client import MiddlewareClient
from .threshold_store import ThresholdStore

logger = logging.getLogger(__name__)


class AlertPayload:
    """Standardised alert object produced by any AnalysisRule."""
    def __init__(
        self,
        rule_id: str,
        severity: str,        # INFO | WARNING | CRITICAL
        message: str,
        node_id: Optional[str],
        zone_id: Optional[str],
        domain: str,          # 'energy' | 'ehs'
        metric_key: str,
        metric_value: float,
        threshold_value: float,
    ):
        self.rule_id        = rule_id
        self.severity       = severity
        self.message        = message
        self.node_id        = node_id
        self.zone_id        = zone_id
        self.domain         = domain
        self.metric_key     = metric_key
        self.metric_value   = metric_value
        self.threshold_value = threshold_value
        self.triggered_at   = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return self.__dict__


class AnalysisRule(ABC):
    """
    Strategy interface — every Q1/Q2/Q3 etc. implements this.
    Adding a new question = subclass this, drop the file in rules/.
    """
    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier, e.g. 'power_balance'."""

    @property
    @abstractmethod
    def domain(self) -> str:
        """'energy' or 'ehs'"""

    @abstractmethod
    def analyse(
        self,
        readings: list[dict],
        thresholds: dict,
    ) -> list[AlertPayload]:
        """
        Run this rule against the latest batch of node readings.
        Returns a (possibly empty) list of AlertPayload objects.
        """

    def get_default_thresholds(self) -> dict:
        """Return sensible defaults. Overridden by analyst sliders."""
        return {}


class BaseEngine(ABC):
    """
    Template Method — defines the immutable analysis pipeline.
    
    Pipeline:
      1. Fetch latest node readings from PersistentMiddleware
      2. For each registered rule, run analyse()
      3. For each alert produced, POST to UserService
      4. Store latest readings for /metrics/* endpoints
    """

    def __init__(
        self,
        middleware_url: str,
        userservice_url: str,
        internal_api_key: str,
        poll_interval_sec: int = 30,
    ):
        self._middleware     = MiddlewareClient(middleware_url)
        self._userservice_url = userservice_url
        self._api_key        = internal_api_key
        self._poll_interval  = poll_interval_sec
        self._thresholds     = ThresholdStore()
        self._latest_readings: list[dict] = []
        self._recent_alerts: list[dict]   = []

        # Seed threshold store with each rule's defaults
        for rule in self.get_rules():
            self._thresholds.seed(rule.rule_id, rule.get_default_thresholds())

        logger.info(f"[{self.engine_name}] Initialised with {len(self.get_rules())} rules.")

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Human-readable engine label, e.g. 'EnergyManagementEngine'."""

    @abstractmethod
    def get_rules(self) -> list[AnalysisRule]:
        """Return the ordered list of AnalysisRule strategies for this engine."""

    @abstractmethod
    def node_filter(self) -> dict:
        """
        Query params for PersistentMiddleware to filter relevant nodes.
        e.g. {'engine_type': 'energy'} or {'engine_type': 'ehs'}
        """

    # ── Fixed Pipeline (Template Method — do NOT override) ──────────────────

    async def start(self):
        """Kick off the continuous background analysis loop."""
        logger.info(f"[{self.engine_name}] Starting analysis loop (every {self._poll_interval}s).")
        while True:
            try:
                await self._run_cycle()
            except Exception as exc:
                logger.error(f"[{self.engine_name}] Cycle error: {exc}")
            await asyncio.sleep(self._poll_interval)

    async def _run_cycle(self):
        """Single analysis tick: fetch → analyse → alert."""
        readings = await self._middleware.fetch_latest(self.node_filter())
        self._latest_readings = readings
        logger.debug(f"[{self.engine_name}] Fetched {len(readings)} node readings.")

        for rule in self.get_rules():
            thresholds = self._thresholds.get(rule.rule_id)
            try:
                alerts = rule.analyse(readings, thresholds)
                for alert in alerts:
                    await self._dispatch_alert(alert)
            except Exception as exc:
                logger.error(f"[{self.engine_name}][{rule.rule_id}] Rule error: {exc}")

    async def _dispatch_alert(self, alert: AlertPayload):
        """POST alert to UserService /internal/alerts."""
        import httpx
        payload = alert.to_dict()
        self._recent_alerts.append(payload)
        # Keep last 200 in memory
        if len(self._recent_alerts) > 200:
            self._recent_alerts = self._recent_alerts[-200:]
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self._userservice_url}/internal/alerts",
                    json=payload,
                    headers={"X-API-Key": self._api_key},
                    timeout=5,
                )
            logger.info(f"[{self.engine_name}] Alert dispatched: [{alert.severity}] {alert.message}")
        except Exception as exc:
            logger.warning(f"[{self.engine_name}] Alert dispatch failed: {exc}")

    # ── Accessors for /metrics/* endpoints ─────────────────────────────────

    def get_latest_readings(self) -> list[dict]:
        return self._latest_readings

    def get_recent_alerts(self, limit: int = 100) -> list[dict]:
        return self._recent_alerts[-limit:]

    def get_thresholds(self) -> dict:
        return self._thresholds.get_all()

    def update_threshold(self, rule_id: str, key: str, value: float) -> bool:
        return self._thresholds.update(rule_id, key, value)
