"""
evaluator/threshold_evaluator.py — Factory Method targets + Abstract Evaluator.

DESIGN PATTERN: Factory Method
────────────────────────────────
Each metric (AQI, Water pH, Noise, PM2.5, UV, VOC, Turbidity) has completely
different safety scales and thresholds. Rather than one massive if-else block
in the engine, the Factory creates the correct specialized ThresholdEvaluator
object for each metric type.

Adding new metrics in the future = one new class here + one new case in the factory.
Zero edits elsewhere.

Expanded from 2 evaluators (AQI, Water pH) to 7 evaluators covering all EHS metrics.
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


# ─────────────────────────────────────────────
# Concrete Evaluator 3: Noise Level (dB)
# ─────────────────────────────────────────────

class NoiseThresholdEvaluator(ThresholdEvaluator):
    """
    Noise level assessment (WHO / OSHA guidelines):
      <70 dB  → Safe (conversation, ambient campus)
      70–85 dB → Warning (elevated, extended exposure risk)
      >85 dB   → Critical (hearing damage risk, construction zone alert)
    """

    def __init__(self, warning_threshold: float = 70, critical_threshold_val: float = 85):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "noise_db"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 4: PM2.5 Particulate Matter
# ─────────────────────────────────────────────

class PM25ThresholdEvaluator(ThresholdEvaluator):
    """
    PM2.5 assessment (WHO Air Quality Guidelines 2021):
      <35 µg/m³   → Safe (good air quality)
      35–150 µg/m³ → Unhealthy (WARNING — sensitive groups at risk)
      >150 µg/m³   → Very unhealthy (CRITICAL — everyone at risk)
    """

    def __init__(self, warning_threshold: float = 35, critical_threshold_val: float = 150):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "pm25"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 5: UV Index
# ─────────────────────────────────────────────

class UVIndexEvaluator(ThresholdEvaluator):
    """
    UV Index assessment (WHO UV Index scale):
      0–5   → Low to moderate (SAFE — normal precautions)
      6–8   → High (WARNING — protection required, limit midday exposure)
      >8    → Very high to extreme (CRITICAL — avoid outdoor activities)
    """

    def __init__(self, warning_threshold: float = 6, critical_threshold_val: float = 8):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "uv_index"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 6: VOC (Volatile Organic Compounds)
# ─────────────────────────────────────────────

class VOCEvaluator(ThresholdEvaluator):
    """
    VOC assessment (EPA indoor/outdoor air quality):
      <500 ppb    → Normal background levels (SAFE)
      500–2000 ppb → Elevated, investigate source (WARNING)
      >2000 ppb    → Hazardous, possible chemical leak (CRITICAL)
    """

    def __init__(self, warning_threshold: float = 500, critical_threshold_val: float = 2000):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "voc_ppb"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE


# ─────────────────────────────────────────────
# Concrete Evaluator 7: Water Turbidity (NTU)
# ─────────────────────────────────────────────

class TurbidityEvaluator(ThresholdEvaluator):
    """
    Water turbidity assessment (WHO drinking water guidelines):
      <5 NTU   → Clear water, safe (SAFE)
      5–50 NTU → Cloudy, potential contamination (WARNING)
      >50 NTU  → Severely turbid, unsafe (CRITICAL — possible sewage/runoff)
    """

    def __init__(self, warning_threshold: float = 5, critical_threshold_val: float = 50):
        self._warning  = warning_threshold
        self._critical = critical_threshold_val

    @property
    def critical_threshold(self) -> float:
        return self._critical

    @property
    def metric_name(self) -> str:
        return "turbidity_ntu"

    def check(self, value: float) -> SafetyStatus:
        if value >= self._critical:
            return SafetyStatus.CRITICAL
        elif value >= self._warning:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE
