"""
ThresholdStore — In-memory analyst-adjustable threshold cache.
Each rule seeds its own defaults. Analyst API calls update values live.
Thread-safe via a simple dict (FastAPI runs single-process async).
"""
import logging

logger = logging.getLogger(__name__)


class ThresholdStore:
    def __init__(self):
        self._store: dict[str, dict] = {}  # {rule_id: {key: value}}

    def seed(self, rule_id: str, defaults: dict):
        """Called once at engine init to set default threshold values."""
        if rule_id not in self._store:
            self._store[rule_id] = defaults
            logger.debug(f"[ThresholdStore] Seeded {rule_id}: {defaults}")

    def get(self, rule_id: str) -> dict:
        """Get current thresholds for a rule. Returns empty dict if not found."""
        return self._store.get(rule_id, {})

    def get_all(self) -> dict:
        """Return a snapshot of all thresholds (for GET /thresholds endpoint)."""
        return {k: dict(v) for k, v in self._store.items()}

    def update(self, rule_id: str, key: str, value: float) -> bool:
        """
        Update a single threshold value (called by Analyst slider PUT request).
        Returns True if rule_id+key exist, False if invalid.
        """
        if rule_id not in self._store:
            logger.warning(f"[ThresholdStore] Unknown rule_id: {rule_id}")
            return False
        if key not in self._store[rule_id]:
            logger.warning(f"[ThresholdStore] Unknown key '{key}' for rule '{rule_id}'")
            return False
        self._store[rule_id][key] = value
        logger.info(f"[ThresholdStore] Updated {rule_id}.{key} = {value}")
        return True
