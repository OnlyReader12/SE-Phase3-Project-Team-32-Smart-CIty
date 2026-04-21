"""
evaluator/evaluator_factory.py — Factory Method: Creates the correct ThresholdEvaluator.

DESIGN PATTERN: Factory Method
────────────────────────────────
The EngineEvaluator never instantiates evaluators directly. It asks the factory:
  "Give me an evaluator for 'aqi'."
The factory decides which concrete class to return.

Extensibility: Adding "noise_db" (noise decibel monitoring) in the future only
requires:
  1. Creating NoiseDbEvaluator(ThresholdEvaluator) in threshold_evaluator.py
  2. Adding one 'elif' case here.
  3. Zero changes anywhere else in the codebase.
"""

from evaluator.threshold_evaluator import (
    ThresholdEvaluator,
    AQIThresholdEvaluator,
    WaterPhEvaluator,
)


class EvaluatorFactory:
    """
    Static factory for creating ThresholdEvaluator instances.
    Accepts runtime threshold configuration from config.yaml.
    """

    @staticmethod
    def create(metric_type: str, thresholds: dict) -> ThresholdEvaluator:
        """
        Create and return the appropriate evaluator for the given metric.

        Args:
            metric_type: Metric identifier string — "aqi" or "water_ph".
            thresholds:  The thresholds sub-dict from config.yaml.

        Returns:
            A concrete ThresholdEvaluator instance.

        Raises:
            ValueError if metric_type is unknown.
        """
        if metric_type == "aqi":
            aqi_cfg = thresholds.get("aqi", {})
            return AQIThresholdEvaluator(
                warning_threshold=aqi_cfg.get("warning", 150),
                critical_threshold_val=aqi_cfg.get("critical", 300),
            )

        elif metric_type == "water_ph":
            ph_cfg = thresholds.get("water_ph", {})
            return WaterPhEvaluator(
                safe_min=ph_cfg.get("safe_min", 6.5),
                safe_max=ph_cfg.get("safe_max", 8.5),
                danger_min=ph_cfg.get("danger_min", 5.0),
                danger_max=ph_cfg.get("danger_max", 9.5),
            )

        else:
            raise ValueError(
                f"[EvaluatorFactory] Unknown metric type: '{metric_type}'. "
                f"Supported: 'aqi', 'water_ph'."
            )
