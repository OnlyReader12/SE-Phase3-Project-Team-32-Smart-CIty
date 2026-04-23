"""
evaluator/evaluator_factory.py — Factory Method: Creates the correct ThresholdEvaluator.

DESIGN PATTERN: Factory Method
────────────────────────────────
The EngineEvaluator never instantiates evaluators directly. It asks the factory:
  "Give me an evaluator for 'solar_power_w'."
The factory decides which concrete class to return.

Extensibility: Adding a new metric evaluator requires:
  1. Creating the evaluator class in threshold_evaluator.py
  2. Adding one 'elif' case here.
  3. Zero changes anywhere else in the codebase.

Supports 7 metric types: solar_power, power_factor, battery_soc, grid_load,
occupancy, water_leak, ac_overload.
"""

from evaluator.threshold_evaluator import (
    ThresholdEvaluator,
    SolarEfficiencyEvaluator,
    PowerFactorEvaluator,
    BatterySoCEvaluator,
    GridLoadEvaluator,
    OccupancyEvaluator,
    WaterLeakEvaluator,
    ACOverloadEvaluator,
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
            metric_type: Metric identifier string.
            thresholds:  The thresholds sub-dict from config.yaml.

        Returns:
            A concrete ThresholdEvaluator instance.

        Raises:
            ValueError if metric_type is unknown.
        """
        if metric_type == "solar_power":
            cfg = thresholds.get("solar_power", {})
            return SolarEfficiencyEvaluator(
                warning_threshold=cfg.get("warning", 200),
                critical_threshold_val=cfg.get("critical", 50),
            )

        elif metric_type == "power_factor":
            cfg = thresholds.get("power_factor", {})
            return PowerFactorEvaluator(
                warning_threshold=cfg.get("warning", 0.90),
                critical_threshold_val=cfg.get("critical", 0.80),
            )

        elif metric_type == "battery_soc":
            cfg = thresholds.get("battery_soc", {})
            return BatterySoCEvaluator(
                warning_threshold=cfg.get("warning", 40),
                critical_threshold_val=cfg.get("critical", 20),
            )

        elif metric_type == "grid_load":
            cfg = thresholds.get("grid_load", {})
            return GridLoadEvaluator(
                warning_threshold=cfg.get("warning", 70),
                critical_threshold_val=cfg.get("critical", 90),
            )

        elif metric_type == "occupancy":
            cfg = thresholds.get("occupancy", {})
            return OccupancyEvaluator(
                warning_threshold=cfg.get("warning", 50),
                critical_threshold_val=cfg.get("critical", 100),
            )

        elif metric_type == "water_leak":
            cfg = thresholds.get("water_leak", {})
            return WaterLeakEvaluator(
                warning_threshold=cfg.get("warning", 50),
                critical_threshold_val=cfg.get("critical", 100),
            )

        elif metric_type == "ac_overload":
            cfg = thresholds.get("ac_overload", {})
            return ACOverloadEvaluator(
                warning_threshold=cfg.get("warning", 2000),
                critical_threshold_val=cfg.get("critical", 3500),
            )

        else:
            raise ValueError(
                f"[EvaluatorFactory] Unknown metric type: '{metric_type}'. "
                f"Supported: 'solar_power', 'power_factor', 'battery_soc', "
                f"'grid_load', 'occupancy', 'water_leak', 'ac_overload'."
            )
