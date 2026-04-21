"""
evaluator/threshold_evaluator.py — Factory Method targets + Abstract Evaluator.

DESIGN PATTERN: Factory Method
────────────────────────────────
Each metric (AQI, Water pH) has completely different safety scales and thresholds.
Rather than one massive if-else block in the engine, the Factory creates the correct
specialized ThresholdEvaluator object for each metric type. Adding "noise pollution"
in the future = one new class here + one new case in the factory. Zero edits elsewhere.
"""

from abc import ABC, abstractmethod
from models.schemas import SafetyStatus


class ThresholdEvaluator(ABC):
    """Abstract base for all per-metric threshold evaluators."""

    @abstractmethod
    def check(self, value: float) -> SafetyStatus:
        """
        Evaluate a single metric reading against its defined safety thresholds.
        Returns SAFE, WARNING, or CRITICAL.
        """
        pass

    @property
    @abstractmethod
    def critical_threshold(self) -> float:
        """The threshold value that triggers a CRITICAL alert."""
        pass

    @property
    @abstractmethod
    def metric_name(self) -> str:
        pass


# ─────────────────────────────────────────────
# Concrete Evaluator 1: Air Quality Index (AQI)
# ─────────────────────────────────────────────

class AQIThresholdEvaluator(ThresholdEvaluator):
    """
    AQI scale (US EPA standard):
      0–50   → Good (SAFE)
      51–150 → Moderate (SAFE at system level, logged)
      151–300→ Unhealthy (WARNING)
      301+   → Hazardous (CRITICAL — triggers SMS/Email via Member 4)
    """

    def __init__(self, warning_threshold: float = 150, critical_threshold_val: float = 300):
        self._warning   = warning_threshold
        self._critical  = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "aqi"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 2: Water pH
# ─────────────────────────────────────────────

class WaterPhEvaluator(ThresholdEvaluator):
    """
    Water pH scale:
      6.5–8.5  → Safe drinking range (SAFE)
      5.0–6.5 or 8.5–9.5 → Borderline (WARNING)
      <5.0 or >9.5        → Hazardous extreme (CRITICAL)
    """

    def __init__(
        self,
        safe_min: float = 6.5,
        safe_max: float = 8.5,
        danger_min: float = 5.0,
        danger_max: float = 9.5,
    ):
        self._safe_min   = safe_min
        self._safe_max   = safe_max
        self._danger_min = danger_min
        self._danger_max = danger_max

    @property
    def critical_threshold(self) -> float:
        # Return the lower danger bound as the representative threshold
        return self._danger_min

    @property
    def metric_name(self) -> str:
        return "water_ph"

    def check(self, value: float) -> SafetyStatus:
        if value < self._danger_min or value > self._danger_max:
            return SafetyStatus.CRITICAL
        elif value < self._safe_min or value > self._safe_max:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE
