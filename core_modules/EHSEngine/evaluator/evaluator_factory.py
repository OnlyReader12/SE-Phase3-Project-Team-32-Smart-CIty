"""
evaluator/evaluator_factory.py — Factory Method: Creates the correct ThresholdEvaluator.

DESIGN PATTERN: Factory Method
────────────────────────────────
The EngineEvaluator never instantiates evaluators directly. It asks the factory:
  "Give me an evaluator for 'aqi'."
The factory decides which concrete class to return.

Extensibility: Adding a new metric evaluator requires:
  1. Creating the evaluator class in threshold_evaluator.py
  2. Adding one 'elif' case here.
  3. Zero changes anywhere else in the codebase.

Expanded: Now supports 7 metric types (AQI, Water pH, Noise, PM2.5, UV, VOC, Turbidity).
"""

from evaluator.threshold_evaluator import (
    ThresholdEvaluator,
    AQIThresholdEvaluator,
    WaterPhEvaluator,
    NoiseThresholdEvaluator,
    PM25ThresholdEvaluator,
    UVIndexEvaluator,
    VOCEvaluator,
    TurbidityEvaluator,
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

        elif metric_type == "noise_db":
            noise_cfg = thresholds.get("noise_db", {})
            return NoiseThresholdEvaluator(
                warning_threshold=noise_cfg.get("warning", 70),
                critical_threshold_val=noise_cfg.get("critical", 85),
            )

        elif metric_type == "pm25":
            pm25_cfg = thresholds.get("pm25", {})
            return PM25ThresholdEvaluator(
                warning_threshold=pm25_cfg.get("warning", 35),
                critical_threshold_val=pm25_cfg.get("critical", 150),
            )

        elif metric_type == "uv_index":
            uv_cfg = thresholds.get("uv_index", {})
            return UVIndexEvaluator(
                warning_threshold=uv_cfg.get("warning", 6),
                critical_threshold_val=uv_cfg.get("critical", 8),
            )

        elif metric_type == "voc":
            voc_cfg = thresholds.get("voc", {})
            return VOCEvaluator(
                warning_threshold=voc_cfg.get("warning", 500),
                critical_threshold_val=voc_cfg.get("critical", 2000),
            )

        elif metric_type == "turbidity":
            turb_cfg = thresholds.get("turbidity", {})
            return TurbidityEvaluator(
                warning_threshold=turb_cfg.get("warning", 5),
                critical_threshold_val=turb_cfg.get("critical", 50),
            )

        else:
            raise ValueError(
                f"[EvaluatorFactory] Unknown metric type: '{metric_type}'. "
                f"Supported: 'aqi', 'water_ph', 'noise_db', 'pm25', 'uv_index', 'voc', 'turbidity'."
            )
