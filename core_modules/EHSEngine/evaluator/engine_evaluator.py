"""
evaluator/engine_evaluator.py — Core Business Logic Controller (Expanded).

This is the "brain" of the EHS Engine. It orchestrates all three patterns:
  - Factory Method  → creates the right ThresholdEvaluator per metric
  - Strategy Pattern→ calls the injected PredictorStrategy for forecasting
  - Observer Pattern→ is called by AMQPConsumer when events arrive (via callback)

Expanded capabilities:
  ✅ Evaluates 7+ metrics across 6 node types
  ✅ Generates actionable suggestions based on current + forecasted values
  ✅ Provides dashboard summary with campus health score
  ✅ Provides visualization-ready time-series data

Key boundary rules enforced here:
  ✅ Writes to InfluxDB (Member 5 reads from there for the Researcher API)
  ✅ Publishes to alerts.critical on RabbitMQ (Member 4 handles SMS/Email)
  ❌ Never calls Twilio or SendGrid directly
  ❌ Never writes to PostgreSQL (that's Member 5's domain)
"""

import datetime
import uuid
import threading
from collections import defaultdict, deque
from typing import Dict, Deque, List, Optional

from evaluator.evaluator_factory import EvaluatorFactory
from ml.predictor_strategy import PredictorStrategy
from models.schemas import (
    EHSTelemetry, EvaluatedReading, SafetyStatus, MetricType,
    MetricEvaluation, ForecastResult,
    EHSSuggestion, SuggestionSeverity, EHSDashboardSummary, NodeStatus,
)


# Rolling window of recent readings per node, used for ML forecasting
_HISTORY_WINDOW = 20  # last 20 readings per sensor node


class EHSEngineEvaluator:
    """
    Core evaluation controller for the EHS Domain Engine.

    Receives EHSTelemetry events, evaluates each metric using the Factory-
    created evaluators, runs ML forecasting via the Strategy-injected predictor,
    then delegates persistence and alerting to their respective components.
    
    Extended with:
      - Multi-metric evaluation (noise, PM2.5, UV, VOC, turbidity)
      - Suggestion generation engine
      - Dashboard summary aggregation
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
        self._aqi_evaluator  = EvaluatorFactory.create("aqi", thresholds)
        self._ph_evaluator   = EvaluatorFactory.create("water_ph", thresholds)
        # New extended evaluators
        self._noise_evaluator     = EvaluatorFactory.create("noise_db", thresholds)
        self._pm25_evaluator      = EvaluatorFactory.create("pm25", thresholds)
        self._uv_evaluator        = EvaluatorFactory.create("uv_index", thresholds)
        self._voc_evaluator       = EvaluatorFactory.create("voc", thresholds)
        self._turbidity_evaluator = EvaluatorFactory.create("turbidity", thresholds)

        # Per-node history for ML forecasting (keyed by metric name)
        self._aqi_history: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._ph_history:  Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._noise_history: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._pm25_history:  Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))

        # Track latest evaluations per node for dashboard
        self._latest_evaluations: Dict[str, EvaluatedReading] = {}
        self._latest_node_types: Dict[str, str] = {}

    def evaluate(self, telemetry: EHSTelemetry) -> EvaluatedReading:
        """
        Main evaluation pipeline for one telemetry event.
        Called by AMQPConsumer on each message from telemetry.enviro.*
        """
        node_id = telemetry.node_id
        node_type = getattr(telemetry, 'node_type', 'air_quality')
        aqi_val = telemetry.data.aqi
        ph_val  = telemetry.data.water_ph

        # ── 1. Update rolling history windows ──
        self._aqi_history[node_id].append(aqi_val)
        self._ph_history[node_id].append(ph_val)

        # ── 2. Threshold Evaluation (Factory Method) ──
        aqi_status = self._aqi_evaluator.check(aqi_val)
        ph_status  = self._ph_evaluator.check(ph_val)

        # ── 3. Extended metric evaluations ──
        extended_metrics = []
        data = telemetry.data

        if data.noise_db is not None:
            noise_status = self._noise_evaluator.check(data.noise_db)
            self._noise_history[node_id].append(data.noise_db)
            extended_metrics.append(MetricEvaluation(
                metric="noise_db", value=data.noise_db, status=noise_status
            ))

        if data.pm25 is not None:
            pm25_status = self._pm25_evaluator.check(data.pm25)
            self._pm25_history[node_id].append(data.pm25)
            extended_metrics.append(MetricEvaluation(
                metric="pm25", value=data.pm25, status=pm25_status
            ))

        if data.uv_index is not None:
            uv_status = self._uv_evaluator.check(data.uv_index)
            extended_metrics.append(MetricEvaluation(
                metric="uv_index", value=data.uv_index, status=uv_status
            ))

        if data.voc_ppb is not None:
            voc_status = self._voc_evaluator.check(data.voc_ppb)
            extended_metrics.append(MetricEvaluation(
                metric="voc_ppb", value=data.voc_ppb, status=voc_status
            ))

        if data.turbidity_ntu is not None:
            turb_status = self._turbidity_evaluator.check(data.turbidity_ntu)
            extended_metrics.append(MetricEvaluation(
                metric="turbidity_ntu", value=data.turbidity_ntu, status=turb_status
            ))

        # ── 4. Compute overall status (worst-case across all metrics) ──
        all_statuses = [aqi_status, ph_status] + [m.status for m in extended_metrics]
        overall = self._compute_overall_from_list(all_statuses)

        # ── 5. ML Forecasting (Strategy Pattern) ──
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

        # Add forecasts to extended metrics where applicable
        for me in extended_metrics:
            if me.status != SafetyStatus.SAFE:
                history_map = {
                    "noise_db": self._noise_history,
                    "pm25": self._pm25_history,
                }
                if me.metric in history_map and len(history_map[me.metric].get(node_id, [])) > 0:
                    me.forecast = self._predictor.predict(
                        list(history_map[me.metric][node_id]),
                        metric_name=me.metric,
                    )

        # ── 6. Build evaluated reading ──
        evaluated = EvaluatedReading(
            node_id=node_id,
            node_type=node_type,
            timestamp=telemetry.timestamp,
            aqi_value=aqi_val,
            aqi_status=aqi_status,
            water_ph_value=ph_val,
            water_ph_status=ph_status,
            overall_status=overall,
            aqi_forecast=aqi_forecast,
            water_ph_forecast=ph_forecast,
            extended_metrics=extended_metrics if extended_metrics else None,
        )

        # Track for dashboard
        self._latest_evaluations[node_id] = evaluated
        self._latest_node_types[node_id] = node_type

        # -- 7. Persist to InfluxDB (non-blocking) --
        threading.Thread(
            target=self._influx_writer.write, args=(evaluated,), daemon=True
        ).start()

        # -- 8. Publish alerts to RabbitMQ if CRITICAL (non-blocking) --
        def _publish_alerts():
            if aqi_status == SafetyStatus.CRITICAL:
                self._alert_publisher.publish(
                    metric=MetricType.AQI, value=aqi_val,
                    threshold=self._aqi_evaluator.critical_threshold,
                    severity=SafetyStatus.CRITICAL, node_id=node_id,
                    timestamp=telemetry.timestamp,
                    message=f"CRITICAL: AQI={aqi_val} at {node_id} - hazardous air quality!",
                )
            if ph_status == SafetyStatus.CRITICAL:
                self._alert_publisher.publish(
                    metric=MetricType.WATER_PH, value=ph_val,
                    threshold=self._ph_evaluator.critical_threshold,
                    severity=SafetyStatus.CRITICAL, node_id=node_id,
                    timestamp=telemetry.timestamp,
                    message=f"CRITICAL: Water pH={ph_val} at {node_id} - unsafe water!",
                )
            for me in extended_metrics:
                if me.status == SafetyStatus.CRITICAL:
                    try:
                        metric_enum = MetricType(me.metric)
                    except ValueError:
                        continue
                    evaluator_map = {
                        "noise_db": self._noise_evaluator,
                        "pm25": self._pm25_evaluator,
                        "uv_index": self._uv_evaluator,
                        "voc_ppb": self._voc_evaluator,
                        "turbidity_ntu": self._turbidity_evaluator,
                    }
                    ev = evaluator_map.get(me.metric)
                    if ev:
                        self._alert_publisher.publish(
                            metric=metric_enum, value=me.value,
                            threshold=ev.critical_threshold,
                            severity=SafetyStatus.CRITICAL, node_id=node_id,
                            timestamp=telemetry.timestamp,
                            message=f"CRITICAL: {me.metric}={me.value} at {node_id}!",
                        )

        if any(s == SafetyStatus.CRITICAL for s in all_statuses):
            threading.Thread(target=_publish_alerts, daemon=True).start()

        status_icon = {"SAFE": "[OK]", "WARNING": "[WARN]", "CRITICAL": "[!!!]"}.get(overall.value, "[?]")
        ext_str = ""
        if extended_metrics:
            ext_str = " | " + " | ".join(f"{m.metric}={m.value}({m.status.value})" for m in extended_metrics)
        print(f"[EHSEvaluator] {status_icon} {node_id} ({node_type}) | AQI={aqi_val}({aqi_status.value}) | "
              f"pH={ph_val}({ph_status.value}){ext_str} | Overall={overall.value}")

        return evaluated

    # ─────────────────────────────────────────────
    # Suggestion Engine
    # ─────────────────────────────────────────────

    def generate_suggestions(self) -> List[EHSSuggestion]:
        """
        Generate actionable EHS suggestions based on all current evaluations.
        Rules are domain-specific and combine current readings with ML forecasts.
        """
        suggestions = []
        now = datetime.datetime.now().isoformat()

        for node_id, evaluation in self._latest_evaluations.items():
            node_type = self._latest_node_types.get(node_id, "unknown")

            # ── AQI Suggestions ──
            if evaluation.aqi_status == SafetyStatus.CRITICAL:
                suggestions.append(EHSSuggestion(
                    id=f"SUG-{uuid.uuid4().hex[:8]}",
                    severity=SuggestionSeverity.EMERGENCY,
                    category="air_quality",
                    title="🚨 Hazardous Air Quality Detected",
                    description=(
                        f"AQI at {node_id} has reached {evaluation.aqi_value} (Hazardous). "
                        f"Immediately close all windows and activate HVAC filtration in nearby buildings. "
                        f"Issue campus-wide outdoor activity restriction."
                    ),
                    affected_nodes=[node_id],
                    timestamp=now,
                ))
            elif evaluation.aqi_status == SafetyStatus.WARNING:
                desc = f"AQI at {node_id} is {evaluation.aqi_value} (Unhealthy for sensitive groups). "
                if evaluation.aqi_forecast and evaluation.aqi_forecast.trend == "rising":
                    desc += f"ML forecast predicts further deterioration to {evaluation.aqi_forecast.predicted_value} within 60 min. Pre-emptively restrict outdoor activities."
                    sev = SuggestionSeverity.URGENT
                else:
                    desc += "Monitor closely. Consider limiting extended outdoor athletic activities."
                    sev = SuggestionSeverity.CAUTION
                suggestions.append(EHSSuggestion(
                    id=f"SUG-{uuid.uuid4().hex[:8]}",
                    severity=sev,
                    category="air_quality",
                    title="⚠️ Elevated Air Quality Index",
                    description=desc,
                    affected_nodes=[node_id],
                    timestamp=now,
                ))

            # ── Water pH Suggestions ──
            if evaluation.water_ph_status == SafetyStatus.CRITICAL:
                suggestions.append(EHSSuggestion(
                    id=f"SUG-{uuid.uuid4().hex[:8]}",
                    severity=SuggestionSeverity.EMERGENCY,
                    category="water",
                    title="🚨 Unsafe Water Detected",
                    description=(
                        f"Water pH at {node_id} is {evaluation.water_ph_value} (outside safe range 6.5–8.5). "
                        f"Shut off affected campus water supply lines immediately. Dispatch water quality team."
                    ),
                    affected_nodes=[node_id],
                    timestamp=now,
                ))

            # ── Extended Metric Suggestions ──
            if evaluation.extended_metrics:
                for me in evaluation.extended_metrics:
                    if me.metric == "noise_db" and me.status == SafetyStatus.CRITICAL:
                        suggestions.append(EHSSuggestion(
                            id=f"SUG-{uuid.uuid4().hex[:8]}",
                            severity=SuggestionSeverity.URGENT,
                            category="noise",
                            title="🔊 Dangerous Noise Levels",
                            description=(
                                f"Noise at {node_id} is {me.value} dB (exceeds 85 dB OSHA limit). "
                                f"Issue hearing protection mandate for nearby buildings. "
                                f"Contact construction management to reduce noise output."
                            ),
                            affected_nodes=[node_id],
                            timestamp=now,
                        ))
                    elif me.metric == "voc_ppb" and me.status == SafetyStatus.CRITICAL:
                        suggestions.append(EHSSuggestion(
                            id=f"SUG-{uuid.uuid4().hex[:8]}",
                            severity=SuggestionSeverity.EMERGENCY,
                            category="radiation",
                            title="☢️ Chemical Leak — Elevated VOC",
                            description=(
                                f"VOC concentration at {node_id} is {me.value} ppb (exceeds 2000 ppb safety limit). "
                                f"Evacuate nearby laboratories immediately. Activate ventilation systems. "
                                f"Dispatch hazmat response team."
                            ),
                            affected_nodes=[node_id],
                            timestamp=now,
                        ))
                    elif me.metric == "uv_index" and me.status == SafetyStatus.CRITICAL:
                        suggestions.append(EHSSuggestion(
                            id=f"SUG-{uuid.uuid4().hex[:8]}",
                            severity=SuggestionSeverity.CAUTION,
                            category="weather",
                            title="☀️ Extreme UV Radiation",
                            description=(
                                f"UV Index at {node_id} is {me.value} (Very High/Extreme). "
                                f"Cancel or reschedule outdoor events. Advise sunscreen & shade for campus."
                            ),
                            affected_nodes=[node_id],
                            timestamp=now,
                        ))
                    elif me.metric == "turbidity_ntu" and me.status == SafetyStatus.CRITICAL:
                        suggestions.append(EHSSuggestion(
                            id=f"SUG-{uuid.uuid4().hex[:8]}",
                            severity=SuggestionSeverity.URGENT,
                            category="water",
                            title="💧 Severely Turbid Water",
                            description=(
                                f"Turbidity at {node_id} is {me.value} NTU (unsafe, >50 NTU). "
                                f"Possible sewage infiltration or runoff contamination. "
                                f"Issue do-not-drink advisory for affected water lines."
                            ),
                            affected_nodes=[node_id],
                            timestamp=now,
                        ))
                    elif me.metric == "pm25" and me.status == SafetyStatus.CRITICAL:
                        suggestions.append(EHSSuggestion(
                            id=f"SUG-{uuid.uuid4().hex[:8]}",
                            severity=SuggestionSeverity.EMERGENCY,
                            category="air_quality",
                            title="🫁 Dangerous Particulate Levels",
                            description=(
                                f"PM2.5 at {node_id} is {me.value} µg/m³ (above 150 µg/m³). "
                                f"Activate all building HVAC filtration to MAX. "
                                f"Cancel outdoor events. Warn respiratory-sensitive residents."
                            ),
                            affected_nodes=[node_id],
                            timestamp=now,
                        ))

        # Sort by severity (emergency first)
        severity_order = {
            SuggestionSeverity.EMERGENCY: 0,
            SuggestionSeverity.URGENT: 1,
            SuggestionSeverity.CAUTION: 2,
            SuggestionSeverity.INFO: 3,
        }
        suggestions.sort(key=lambda s: severity_order.get(s.severity, 99))

        # If everything is safe, add an all-clear
        if not suggestions and self._latest_evaluations:
            suggestions.append(EHSSuggestion(
                id=f"SUG-{uuid.uuid4().hex[:8]}",
                severity=SuggestionSeverity.INFO,
                category="general",
                title="✅ All Clear — Campus EHS Nominal",
                description="All environmental metrics are within safe operating limits. No action required.",
                affected_nodes=[],
                timestamp=now,
            ))

        return suggestions

    # ─────────────────────────────────────────────
    # Dashboard Summary
    # ─────────────────────────────────────────────

    def get_dashboard_summary(self) -> EHSDashboardSummary:
        """
        Aggregate all current evaluations into a campus-wide dashboard summary.
        """
        evaluations = list(self._latest_evaluations.values())
        total = len(evaluations)
        critical = sum(1 for e in evaluations if e.overall_status == SafetyStatus.CRITICAL)
        warning = sum(1 for e in evaluations if e.overall_status == SafetyStatus.WARNING)
        safe = sum(1 for e in evaluations if e.overall_status == SafetyStatus.SAFE)

        # Campus health score: 100 = all safe, 0 = all critical
        if total > 0:
            score = ((safe * 100) + (warning * 50) + (critical * 0)) / total
        else:
            score = 100.0

        # Build metric cards from latest evaluations
        metric_cards = self._build_metric_cards(evaluations)

        # Build node status list
        node_statuses = []
        for node_id, ev in self._latest_evaluations.items():
            last_value = {"aqi": ev.aqi_value, "water_ph": ev.water_ph_value}
            if ev.extended_metrics:
                for me in ev.extended_metrics:
                    last_value[me.metric] = me.value
            node_statuses.append(NodeStatus(
                node_id=node_id,
                node_type=self._latest_node_types.get(node_id, "unknown"),
                status=ev.overall_status,
                last_value=last_value,
                last_seen=ev.timestamp,
            ))

        suggestions = self.generate_suggestions()

        return EHSDashboardSummary(
            campus_health_score=round(score, 1),
            total_nodes=total,
            critical_count=critical,
            warning_count=warning,
            safe_count=safe,
            metric_cards=metric_cards,
            suggestions=suggestions,
            node_statuses=node_statuses,
        )

    def _build_metric_cards(self, evaluations: list) -> dict:
        """Build aggregated metric summary cards for the dashboard."""
        cards = {}
        if not evaluations:
            return cards

        # AQI card
        aqi_vals = [e.aqi_value for e in evaluations if e.aqi_value > 0]
        if aqi_vals:
            cards["aqi"] = {
                "label": "Air Quality Index",
                "avg": round(sum(aqi_vals) / len(aqi_vals), 1),
                "max": max(aqi_vals),
                "min": min(aqi_vals),
                "unit": "AQI",
                "nodes_reporting": len(aqi_vals),
            }

        # Water pH card
        ph_vals = [e.water_ph_value for e in evaluations if e.water_ph_value != 7.0 or e.node_type == "water_quality"]
        if ph_vals:
            cards["water_ph"] = {
                "label": "Water pH",
                "avg": round(sum(ph_vals) / len(ph_vals), 2),
                "max": max(ph_vals),
                "min": min(ph_vals),
                "unit": "pH",
                "nodes_reporting": len(ph_vals),
            }

        # Extended metric cards
        metric_map = {
            "noise_db": ("Noise Level", "dB"),
            "pm25": ("PM2.5 Particles", "µg/m³"),
            "uv_index": ("UV Index", "UV"),
            "voc_ppb": ("Volatile Organics", "ppb"),
            "turbidity_ntu": ("Water Turbidity", "NTU"),
        }
        for metric_key, (label, unit) in metric_map.items():
            vals = []
            for e in evaluations:
                if e.extended_metrics:
                    for me in e.extended_metrics:
                        if me.metric == metric_key:
                            vals.append(me.value)
            if vals:
                cards[metric_key] = {
                    "label": label,
                    "avg": round(sum(vals) / len(vals), 1),
                    "max": round(max(vals), 1),
                    "min": round(min(vals), 1),
                    "unit": unit,
                    "nodes_reporting": len(vals),
                }

        return cards

    # ─────────────────────────────────────────────
    # Prediction Access
    # ─────────────────────────────────────────────

    def get_prediction(self, node_id: str) -> Optional[dict]:
        """Get ML prediction for a specific node using its history."""
        result = {}

        if node_id in self._aqi_history and len(self._aqi_history[node_id]) >= 3:
            result["aqi_forecast"] = self._predictor.predict(
                list(self._aqi_history[node_id]), metric_name="aqi"
            ).dict()

        if node_id in self._ph_history and len(self._ph_history[node_id]) >= 3:
            result["water_ph_forecast"] = self._predictor.predict(
                list(self._ph_history[node_id]), metric_name="water_ph"
            ).dict()

        if node_id in self._noise_history and len(self._noise_history[node_id]) >= 3:
            result["noise_db_forecast"] = self._predictor.predict(
                list(self._noise_history[node_id]), metric_name="noise_db"
            ).dict()

        if node_id in self._pm25_history and len(self._pm25_history[node_id]) >= 3:
            result["pm25_forecast"] = self._predictor.predict(
                list(self._pm25_history[node_id]), metric_name="pm25"
            ).dict()

        if not result:
            return None
        result["node_id"] = node_id
        result["generated_at"] = datetime.datetime.now().isoformat()
        return result

    # ─────────────────────────────────────────────
    # Visualization Data
    # ─────────────────────────────────────────────

    def get_visualization_data(self, metric: str = "aqi", limit: int = 50) -> dict:
        """
        Returns time-series visualization data for a specific metric across all nodes.
        Suitable for charting libraries (Chart.js, D3, etc.)
        """
        history_map = {
            "aqi": self._aqi_history,
            "water_ph": self._ph_history,
            "noise_db": self._noise_history,
            "pm25": self._pm25_history,
        }
        history = history_map.get(metric, {})

        series = []
        for node_id, readings in history.items():
            data_points = list(readings)[-limit:]
            if data_points:
                series.append({
                    "node_id": node_id,
                    "node_type": self._latest_node_types.get(node_id, "unknown"),
                    "values": data_points,
                    "latest": data_points[-1],
                    "avg": round(sum(data_points) / len(data_points), 2),
                    "count": len(data_points),
                })

        return {
            "metric": metric,
            "total_series": len(series),
            "generated_at": datetime.datetime.now().isoformat(),
            "series": series,
        }

    def get_heatmap_data(self) -> dict:
        """
        Returns campus-wide metric heatmap data — one entry per node
        with its latest critical metric value and status for geographic overlay.
        """
        heatmap = []
        for node_id, evaluation in self._latest_evaluations.items():
            entry = {
                "node_id": node_id,
                "node_type": self._latest_node_types.get(node_id, "unknown"),
                "status": evaluation.overall_status.value,
                "aqi": evaluation.aqi_value,
                "water_ph": evaluation.water_ph_value,
            }
            if evaluation.extended_metrics:
                for me in evaluation.extended_metrics:
                    entry[me.metric] = me.value
            heatmap.append(entry)

        return {
            "total_nodes": len(heatmap),
            "generated_at": datetime.datetime.now().isoformat(),
            "heatmap": heatmap,
        }

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

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

    @staticmethod
    def _compute_overall_from_list(statuses: List[SafetyStatus]) -> SafetyStatus:
        """Worst-case aggregation over a list of statuses."""
        if SafetyStatus.CRITICAL in statuses:
            return SafetyStatus.CRITICAL
        if SafetyStatus.WARNING in statuses:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE
