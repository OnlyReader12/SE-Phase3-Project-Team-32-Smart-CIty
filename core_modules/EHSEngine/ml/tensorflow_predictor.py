"""
ml/tensorflow_predictor.py — Strategy Pattern: TensorFlow Concrete Implementation.

This strategy is loaded when config.yaml sets ml_strategy: "tensorflow".
Swapping to this from Scikit requires ZERO changes to the evaluator — that is
the Strategy Pattern paying off.

If TensorFlow is not installed or no model exists, a graceful fallback is used.
"""

import os
import numpy as np
from typing import List

from ml.predictor_strategy import PredictorStrategy
from models.schemas import ForecastResult


class TensorFlowAQIPredictor(PredictorStrategy):
    """
    TensorFlow/Keras LSTM-based forecasting strategy.
    Loads a pre-trained SavedModel or .h5 file to forecast environmental metrics.

    Typical use case: When the data science team evolves beyond simple linear
    regression and trains a recurrent neural network on historical campus data.
    """

    MODEL_NAME = "tensorflow-keras"

    def __init__(self, model_path: str = "./models/aqi_forecast_tf"):
        self._model = None
        self._model_path = model_path
        self._load_model()

    def _load_model(self):
        """Attempt to import TensorFlow and load the model."""
        try:
            import tensorflow as tf  # Lazy import — TF is heavy
            if os.path.exists(self._model_path):
                self._model = tf.keras.models.load_model(self._model_path)
                print(f"[TFPredictor] Loaded TF model from {self._model_path}")
            else:
                print(f"[TFPredictor] No model at {self._model_path}. Using fallback.")
        except ImportError:
            print("[TFPredictor] TensorFlow not installed. Using statistical fallback.")
        except Exception as e:
            print(f"[TFPredictor] Error loading model: {e}. Using fallback.")

    def predict(self, historical_data: List[float], metric_name: str) -> ForecastResult:
        """
        Predict using TF model (LSTM expects shape: [1, timesteps, 1]).
        Falls back to weighted moving average if model unavailable.
        """
        if not historical_data:
            return ForecastResult(
                predicted_value=0.0, confidence=0.0,
                model=self.MODEL_NAME, trend="stable"
            )

        trend = self._detect_trend(historical_data)

        # ── Path A: TensorFlow model inference ──
        if self._model is not None:
            try:
                import tensorflow as tf
                window_size = 20
                window = historical_data[-window_size:]
                # Pad if too short
                while len(window) < window_size:
                    window.insert(0, window[0])
                # LSTM input: [batch=1, timesteps, features=1]
                input_tensor = np.array(window, dtype=np.float32).reshape(1, window_size, 1)
                predicted = float(self._model.predict(input_tensor, verbose=0)[0][0])
                confidence = 0.91  # Higher confidence from deep learning model
                return ForecastResult(
                    predicted_value=round(predicted, 2),
                    confidence=confidence,
                    model=self.MODEL_NAME,
                    trend=trend,
                )
            except Exception as e:
                print(f"[TFPredictor] Inference error: {e}. Falling back.")

        # ── Path B: Weighted moving average fallback ──
        window = historical_data[-5:]
        weights = [0.1, 0.15, 0.2, 0.25, 0.3][:len(window)]
        norm = sum(weights)
        predicted = sum(w * v for w, v in zip(weights, window)) / norm

        return ForecastResult(
            predicted_value=round(float(predicted), 2),
            confidence=0.60,
            model=f"{self.MODEL_NAME}-fallback",
            trend=trend,
        )
