"""
ml/predictor_strategy.py — Strategy Pattern: Abstract Forecasting Interface.

DESIGN PATTERN: Strategy
────────────────────────
This abstract class is the "Strategy" interface. The EnergyEngineEvaluator never
hard-codes math — it holds a reference to a PredictorStrategy and calls
.predict(). Swapping from Scikit-learn to TensorFlow means:
  1. Writing a new concrete class that inherits from PredictorStrategy.
  2. Updating ONE line in config.yaml.
  3. Zero changes to the evaluator or any other file.

This satisfies the Open-Closed Principle (ADR-001): the evaluator is
closed for modification, open for extension via new Strategy classes.
"""

from abc import ABC, abstractmethod
from typing import List
from models.schemas import ForecastResult


class PredictorStrategy(ABC):
    """
    Abstract base strategy for Energy metric forecasting.
    All concrete predictors must implement this interface.
    """

    @abstractmethod
    def predict(self, historical_data: List[float], metric_name: str) -> ForecastResult:
        """
        Given a window of recent readings, forecast the next value.

        Args:
            historical_data: List of recent metric readings (oldest to newest).
            metric_name:      The metric being forecast, e.g. "solar_power_w" or "grid_load_pct".

        Returns:
            ForecastResult with predicted_value, confidence, model name, and trend.
        """
        pass

    def _detect_trend(self, historical_data: List[float]) -> str:
        """
        Utility: derive a trend label from the last few data points.
        Returns: "rising" | "falling" | "stable"
        """
        if len(historical_data) < 3:
            return "stable"
        recent = historical_data[-3:]
        if recent[-1] > recent[0] * 1.05:
            return "rising"
        elif recent[-1] < recent[0] * 0.95:
            return "falling"
        return "stable"
