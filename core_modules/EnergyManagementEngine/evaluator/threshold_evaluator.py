"""
evaluator/threshold_evaluator.py — Factory Method targets + Abstract Evaluator.

DESIGN PATTERN: Factory Method
────────────────────────────────
Each metric (Solar Power, Power Factor, Battery SoC, Grid Load, Occupancy,
Water Leak, AC Overload) has completely different safety scales and thresholds.
Rather than one massive if-else block in the engine, the Factory creates the
correct specialized ThresholdEvaluator object for each metric type.

Adding new metrics in the future = one new class here + one new case in the factory.
Zero edits elsewhere.

7 evaluators covering all Energy Management metrics.
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
# Concrete Evaluator 1: Solar Power Efficiency
# ─────────────────────────────────────────────

class SolarEfficiencyEvaluator(ThresholdEvaluator):
    """
    Solar panel efficiency assessment (during daylight hours):
      ≥200W   → Good generation (SAFE)
      50–200W → Low output, cloud cover or degradation (WARNING)
      <50W    → Panel failure or severe obstruction (CRITICAL)

    Note: At night (0W), this evaluator should not be invoked.
    The engine handles day/night logic before calling check().
    """

    def __init__(self, warning_threshold: float = 200, critical_threshold_val: float = 50):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "solar_power_w"

    def check(self, value: float) -> SafetyStatus:
        if value <= self._critical:
            return SafetyStatus.CRITICAL
        elif value <= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 2: Power Factor
# ─────────────────────────────────────────────

class PowerFactorEvaluator(ThresholdEvaluator):
    """
    Power factor assessment (IEEE / utility standards):
      ≥0.90 → Efficient power usage (SAFE)
      0.80–0.90 → Inefficient, utility penalties apply (WARNING)
      <0.80 → Severely inefficient, equipment risk (CRITICAL)
    """

    def __init__(self, warning_threshold: float = 0.90, critical_threshold_val: float = 0.80):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "power_factor"

    def check(self, value: float) -> SafetyStatus:
        if value < self._critical:
            return SafetyStatus.CRITICAL
        elif value < self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 3: Battery State of Charge
# ─────────────────────────────────────────────

class BatterySoCEvaluator(ThresholdEvaluator):
    """
    Battery State of Charge assessment:
      ≥40% → Adequate reserve (SAFE)
      20–40% → Low battery, consider load shedding (WARNING)
      <20% → Critically low, risk of blackout (CRITICAL)
    """

    def __init__(self, warning_threshold: float = 40, critical_threshold_val: float = 20):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "battery_soc_pct"

    def check(self, value: float) -> SafetyStatus:
        if value < self._critical:
            return SafetyStatus.CRITICAL
        elif value < self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 4: Grid / Transformer Load
# ─────────────────────────────────────────────

class GridLoadEvaluator(ThresholdEvaluator):
    """
    Grid transformer load assessment:
      <70%  → Normal operating range (SAFE)
      70–90% → Elevated load, monitor closely (WARNING)
      >90%  → Overload risk, trip/fault imminent (CRITICAL)
    """

    def __init__(self, warning_threshold: float = 70, critical_threshold_val: float = 90):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "grid_load_pct"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 5: Occupancy / Overcrowding
# ─────────────────────────────────────────────

class OccupancyEvaluator(ThresholdEvaluator):
    """
    Occupancy/footfall assessment (fire code / energy optimization):
      <50 persons  → Normal occupancy (SAFE)
      50–100 persons → High density, increase HVAC (WARNING)
      >100 persons  → Overcrowded, fire code risk (CRITICAL)
    """

    def __init__(self, warning_threshold: float = 50, critical_threshold_val: float = 100):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "person_count"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 6: Water Leak Detection
# ─────────────────────────────────────────────

class WaterLeakEvaluator(ThresholdEvaluator):
    """
    Water flow / leak assessment:
      <50 LPM & no leak → Normal (SAFE)
      ≥50 LPM or suspicious flow → Possible leak (WARNING)
      Leak detected flag → Confirmed leak (CRITICAL)

    For this evaluator, value encoding:
      0 = normal, 1 = warning (high flow), 2 = leak detected (critical)
    The engine pre-processes leak_detected + flow_rate into a single score.
    """

    def __init__(self, warning_threshold: float = 50, critical_threshold_val: float = 100):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "flow_rate_lpm"

    def check(self, value: float) -> SafetyStatus:
        # value is flow_rate_lpm; leak_detected is handled separately in engine
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 7: AC Unit Overload
# ─────────────────────────────────────────────

class ACOverloadEvaluator(ThresholdEvaluator):
    """
    AC unit power consumption assessment:
      <2000W  → Normal operation (SAFE)
      2000–3500W → High load, consider setpoint adjustment (WARNING)
      >3500W   → Overload, risk of circuit trip (CRITICAL)
    """

    def __init__(self, warning_threshold: float = 2000, critical_threshold_val: float = 3500):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "ac_power_w"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE
