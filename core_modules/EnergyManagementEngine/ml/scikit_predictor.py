"""
ml/scikit_predictor.py — Strategy Pattern: Scikit-learn Concrete Implementation.

This is the DEFAULT strategy loaded when config.yaml sets ml_strategy: "scikit".

If a pre-trained model file exists at the configured path, it is loaded.
If not (e.g., fresh development environment), a simple linear fallback
is used so the engine still runs without crashing — great for local dev.
"""

import os
import numpy as np
from typing import List
import joblib

from ml.predictor_strategy import PredictorStrategy
from models.schemas import ForecastResult


class ScikitEnergyPredictor(PredictorStrategy):
    """
    Scikit-learn based forecasting strategy for energy metrics.
    Loads a pre-trained regression model (.joblib) and predicts the next
    energy reading based on a rolling window of historical values.
    """

    MODEL_NAME = "scikit-learn"

    def __init__(self, model_path: str = "./models/energy_forecast.joblib"):
        self._model = None
        self._model_path = model_path
        self._load_model()

    def _load_model(self):
        """Load the pre-trained model if it exists, else use a simple fallback."""
        if os.path.exists(self._model_path):
            try:
                self._model = joblib.load(self._model_path)
                print(f"[ScikitPredictor] Loaded model from {self._model_path}")
            except Exception as e:
                print(f"[ScikitPredictor] Failed to load model: {e}. Using fallback.")
                self._model = None
        else:
            print(f"[ScikitPredictor] No model at {self._model_path}. Using linear fallback.")

    def predict(self, historical_data: List[float], metric_name: str) -> ForecastResult:
        """
        Predict the next value using scikit-learn or a linear extrapolation fallback.
        Uses the last N readings as a feature window.
        """
        if not historical_data:
            return ForecastResult(
                predicted_value=0.0, confidence=0.0,
                model=self.MODEL_NAME, trend="stable"
            )

        trend = self._detect_trend(historical_data)

        # ── Path A: Use the loaded scikit-learn model ──
        if self._model is not None:
            try:
                # Feature: rolling window reshaped for sklearn
                window = np.array(historical_data[-10:]).reshape(1, -1)
                # Pad if window too short
                if window.shape[1] < 10:
                    pad = np.zeros((1, 10 - window.shape[1]))
                    window = np.concatenate([pad, window], axis=1)
                predicted = float(self._model.predict(window)[0])
                confidence = 0.82  # Hardcoded from model evaluation metrics
                return ForecastResult(
                    predicted_value=round(predicted, 2),
                    confidence=confidence,
                    model=self.MODEL_NAME,
                    trend=trend,
                )
            except Exception as e:
                print(f"[ScikitPredictor] Inference error: {e}. Falling back.")

        # ── Path B: Linear extrapolation fallback (no model file required) ──
        window = historical_data[-5:]
        if len(window) >= 2:
            deltas = [window[i + 1] - window[i] for i in range(len(window) - 1)]
            avg_delta = sum(deltas) / len(deltas)
            predicted = window[-1] + avg_delta
        else:
            predicted = historical_data[-1]

        return ForecastResult(
            predicted_value=round(float(predicted), 2),
            confidence=0.55,  # Lower confidence for fallback
            model=f"{self.MODEL_NAME}-fallback",
            trend=trend,
        )
