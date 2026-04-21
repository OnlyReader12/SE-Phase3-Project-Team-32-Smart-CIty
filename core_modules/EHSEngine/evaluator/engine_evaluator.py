"""
evaluator/engine_evaluator.py — Core Business Logic Controller.

This is the "brain" of the EHS Engine. It orchestrates all three patterns:
  - Factory Method  → creates the right ThresholdEvaluator per metric
  - Strategy Pattern→ calls the injected PredictorStrategy for forecasting
  - Observer Pattern→ is called by AMQPConsumer when events arrive (via callback)

Key boundary rules enforced here:
  ✅ Only evaluates AQI and water pH
  ✅ Writes to InfluxDB (Member 5 reads from there for the Researcher API)
  ✅ Publishes to alerts.critical on RabbitMQ (Member 4 handles SMS/Email)
  ❌ Never calls Twilio or SendGrid directly
  ❌ Never writes to PostgreSQL (that's Member 5's domain)
"""

import datetime
from collections import defaultdict, deque
from typing import Dict, Deque

from evaluator.evaluator_factory import EvaluatorFactory
from ml.predictor_strategy import PredictorStrategy
from models.schemas import (
    EHSTelemetry, EvaluatedReading, SafetyStatus, MetricType
)


# Rolling window of recent readings per node, used for ML forecasting
_HISTORY_WINDOW = 20  # last 20 readings per sensor node


class EHSEngineEvaluator:
    """
    Core evaluation controller for the EHS Domain Engine.

    Receives EHSTelemetry events, evaluates each metric using the Factory-
    created evaluators, runs ML forecasting via the Strategy-injected predictor,
    then delegates persistence and alerting to their respective components.
    """

    def __init__(
        self,
        predictor: PredictorStrategy,
        influx_writer,      # persistence.influx_writer.InfluxWriter
        alert_publisher,    # publisher.alert_publisher.AlertPublisher
        thresholds: dict,
    ):
        self._predictor       = predictor         # Strategy: swappable ML model
        self._influx_writer   = influx_writer
        self._alert_publisher = alert_publisher
        self._thresholds      = thresholds

        # Factory instances cached per metric (avoid re-creating per message)
        self._aqi_evaluator = EvaluatorFactory.create("aqi", thresholds)
        self._ph_evaluator  = EvaluatorFactory.create("water_ph", thresholds)

        # Per-node history for ML forecasting
        self._aqi_history: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._ph_history:  Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))

    def evaluate(self, telemetry: EHSTelemetry) -> EvaluatedReading:
        """
        Main evaluation pipeline for one telemetry event.
        Called by AMQPConsumer on each message from telemetry.enviro.*
        """
        node_id = telemetry.node_id
        aqi_val = telemetry.data.aqi
        ph_val  = telemetry.data.water_ph

        # ── 1. Update rolling history windows ──
        self._aqi_history[node_id].append(aqi_val)
        self._ph_history[node_id].append(ph_val)

        # ── 2. Threshold Evaluation (Factory Method) ──
        aqi_status = self._aqi_evaluator.check(aqi_val)
        ph_status  = self._ph_evaluator.check(ph_val)
        overall    = self._compute_overall_status(aqi_status, ph_status)

        # ── 3. ML Forecasting (Strategy Pattern) ──
        # Only run forecast if status is WARNING or CRITICAL (saves compute for SAFE readings)
        aqi_forecast = None
        ph_forecast  = None

        if aqi_status != SafetyStatus.SAFE:
            aqi_forecast = self._predictor.predict(
                list(self._aqi_history[node_id]), metric_name="aqi"
            )
            print(f"[EHSEvaluator] AQI forecast for {node_id}: "
                  f"{aqi_forecast.predicted_value} (trend: {aqi_forecast.trend})")

        if ph_status != SafetyStatus.SAFE:
            ph_forecast = self._predictor.predict(
                list(self._ph_history[node_id]), metric_name="water_ph"
            )

        # ── 4. Build evaluated reading ──
        evaluated = EvaluatedReading(
            node_id=node_id,
            timestamp=telemetry.timestamp,
            aqi_value=aqi_val,
            aqi_status=aqi_status,
            water_ph_value=ph_val,
            water_ph_status=ph_status,
            overall_status=overall,
            aqi_forecast=aqi_forecast,
            water_ph_forecast=ph_forecast,
        )

        # ── 5. Persist to InfluxDB (Member 5 reads this for Researcher API) ──
        self._influx_writer.write(evaluated)

        # ── 6. Publish alert to RabbitMQ if CRITICAL ──
        # We publish the minimal payload; Member 4 handles SMS/Email. We NEVER call Twilio.
        if aqi_status == SafetyStatus.CRITICAL:
            self._alert_publisher.publish(
                metric=MetricType.AQI,
                value=aqi_val,
                threshold=self._aqi_evaluator.critical_threshold,
                severity=SafetyStatus.CRITICAL,
                node_id=node_id,
                timestamp=telemetry.timestamp,
                message=f"CRITICAL: AQI={aqi_val} at {node_id} — hazardous air quality!",
            )

        if ph_status == SafetyStatus.CRITICAL:
            self._alert_publisher.publish(
                metric=MetricType.WATER_PH,
                value=ph_val,
                threshold=self._ph_evaluator.critical_threshold,
                severity=SafetyStatus.CRITICAL,
                node_id=node_id,
                timestamp=telemetry.timestamp,
                message=f"CRITICAL: Water pH={ph_val} at {node_id} — unsafe water!",
            )

        status_icon = {"SAFE": "[OK]", "WARNING": "[WARN]", "CRITICAL": "[!!!]"}.get(overall.value, "[?]")
        print(f"[EHSEvaluator] {status_icon} {node_id} | AQI={aqi_val}({aqi_status.value}) | "
              f"pH={ph_val}({ph_status.value}) | Overall={overall.value}")

        return evaluated

    @staticmethod
    def _compute_overall_status(
        aqi_status: SafetyStatus, ph_status: SafetyStatus
    ) -> SafetyStatus:
        """Worst-case aggregation: overall = most severe individual metric."""
        if SafetyStatus.CRITICAL in (aqi_status, ph_status):
            return SafetyStatus.CRITICAL
        if SafetyStatus.WARNING in (aqi_status, ph_status):
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE
