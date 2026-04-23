"""
evaluator/engine_evaluator.py — Core Business Logic Controller for Energy Engine.

This is the "brain" of the Energy Management Engine. It orchestrates all three patterns:
  - Factory Method  → creates the right ThresholdEvaluator per metric
  - Strategy Pattern→ calls the injected PredictorStrategy for forecasting
  - Observer Pattern→ is called by AMQPConsumer when events arrive (via callback)

Capabilities:
  ✅ Evaluates 7 metrics across 7 node types
  ✅ Generates actionable suggestions (Command Pattern) based on current + forecasted values
  ✅ Provides dashboard summary with campus energy efficiency score
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
    EnergyTelemetry, EvaluatedReading, SafetyStatus,
    MetricEvaluation, ForecastResult,
    EnergySuggestion, SuggestionSeverity, EnergyDashboardSummary, NodeStatus,
)


# Rolling window of recent readings per node, used for ML forecasting
_HISTORY_WINDOW = 20  # last 20 readings per sensor node


class EnergyEngineEvaluator:
    """
    Core evaluation controller for the Energy Management Engine.

    Receives EnergyTelemetry events, evaluates each metric using the Factory-
    created evaluators, runs ML forecasting via the Strategy-injected predictor,
    then delegates persistence and alerting to their respective components.

    Extended with:
      - Multi-metric evaluation (solar, battery, grid, efficiency, water, HVAC)
      - Suggestion generation engine with Command Pattern semantics
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
        self._solar_evaluator     = EvaluatorFactory.create("solar_power", thresholds)
        self._pf_evaluator        = EvaluatorFactory.create("power_factor", thresholds)
        self._battery_evaluator   = EvaluatorFactory.create("battery_soc", thresholds)
        self._grid_evaluator      = EvaluatorFactory.create("grid_load", thresholds)
        self._occupancy_evaluator = EvaluatorFactory.create("occupancy", thresholds)
        self._water_evaluator     = EvaluatorFactory.create("water_leak", thresholds)
        self._ac_evaluator        = EvaluatorFactory.create("ac_overload", thresholds)

        # Per-node history for ML forecasting (keyed by metric name)
        self._solar_history:   Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._power_history:   Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._battery_history: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._grid_history:    Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._ac_history:      Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))
        self._water_history:   Dict[str, Deque] = defaultdict(lambda: deque(maxlen=_HISTORY_WINDOW))

        # Track latest evaluations per node for dashboard
        self._latest_evaluations: Dict[str, EvaluatedReading] = {}
        self._latest_node_types: Dict[str, str] = {}

    def evaluate(self, telemetry: EnergyTelemetry) -> EvaluatedReading:
        """
        Main evaluation pipeline for one telemetry event.
        Called by AMQPConsumer on each message from telemetry.power.*
        """
        node_id = telemetry.node_id
        node_type = getattr(telemetry, 'node_type', 'solar_panel')
        data = telemetry.data

        metric_evaluations = []

        # ── Evaluate metrics based on node type ──

        # Solar Panel metrics
        if data.solar_power_w is not None:
            status = self._solar_evaluator.check(data.solar_power_w)
            self._solar_history[node_id].append(data.solar_power_w)
            forecast = None
            if status != SafetyStatus.SAFE and len(self._solar_history[node_id]) >= 3:
                forecast = self._predictor.predict(
                    list(self._solar_history[node_id]), metric_name="solar_power_w"
                )
            metric_evaluations.append(MetricEvaluation(
                metric="solar_power_w", value=data.solar_power_w,
                status=status, forecast=forecast
            ))

        # Power Factor
        if data.power_factor is not None:
            status = self._pf_evaluator.check(data.power_factor)
            self._power_history[node_id].append(data.power_factor)
            forecast = None
            if status != SafetyStatus.SAFE and len(self._power_history[node_id]) >= 3:
                forecast = self._predictor.predict(
                    list(self._power_history[node_id]), metric_name="power_factor"
                )
            metric_evaluations.append(MetricEvaluation(
                metric="power_factor", value=data.power_factor,
                status=status, forecast=forecast
            ))

        # Battery SoC
        if data.battery_soc_pct is not None:
            status = self._battery_evaluator.check(data.battery_soc_pct)
            self._battery_history[node_id].append(data.battery_soc_pct)
            forecast = None
            if status != SafetyStatus.SAFE and len(self._battery_history[node_id]) >= 3:
                forecast = self._predictor.predict(
                    list(self._battery_history[node_id]), metric_name="battery_soc_pct"
                )
            metric_evaluations.append(MetricEvaluation(
                metric="battery_soc_pct", value=data.battery_soc_pct,
                status=status, forecast=forecast
            ))

        # Grid Load
        if data.grid_load_pct is not None:
            status = self._grid_evaluator.check(data.grid_load_pct)
            self._grid_history[node_id].append(data.grid_load_pct)
            forecast = None
            if status != SafetyStatus.SAFE and len(self._grid_history[node_id]) >= 3:
                forecast = self._predictor.predict(
                    list(self._grid_history[node_id]), metric_name="grid_load_pct"
                )
            metric_evaluations.append(MetricEvaluation(
                metric="grid_load_pct", value=data.grid_load_pct,
                status=status, forecast=forecast
            ))

        # Occupancy
        if data.person_count is not None:
            status = self._occupancy_evaluator.check(float(data.person_count))
            metric_evaluations.append(MetricEvaluation(
                metric="person_count", value=float(data.person_count), status=status
            ))

        # Water Flow / Leak
        if data.flow_rate_lpm is not None:
            # If leak_detected is True, automatically CRITICAL
            if data.leak_detected:
                status = SafetyStatus.CRITICAL
            else:
                status = self._water_evaluator.check(data.flow_rate_lpm)
            self._water_history[node_id].append(data.flow_rate_lpm)
            metric_evaluations.append(MetricEvaluation(
                metric="flow_rate_lpm", value=data.flow_rate_lpm, status=status
            ))

        # AC Unit Power
        if data.ac_power_w is not None:
            status = self._ac_evaluator.check(data.ac_power_w)
            self._ac_history[node_id].append(data.ac_power_w)
            forecast = None
            if status != SafetyStatus.SAFE and len(self._ac_history[node_id]) >= 3:
                forecast = self._predictor.predict(
                    list(self._ac_history[node_id]), metric_name="ac_power_w"
                )
            metric_evaluations.append(MetricEvaluation(
                metric="ac_power_w", value=data.ac_power_w,
                status=status, forecast=forecast
            ))

        # Also capture general power consumption
        if data.power_w is not None and data.power_factor is None:
            # Generic power reading (smart meters without explicit power_factor)
            self._power_history[node_id].append(data.power_w)
            metric_evaluations.append(MetricEvaluation(
                metric="power_w", value=data.power_w, status=SafetyStatus.SAFE
            ))

        # ── Compute overall status (worst-case across all metrics) ──
        all_statuses = [m.status for m in metric_evaluations] if metric_evaluations else [SafetyStatus.SAFE]
        overall = self._compute_overall_from_list(all_statuses)

        # ── Determine primary metric ──
        primary = metric_evaluations[0] if metric_evaluations else None

        # ── Build evaluated reading ──
        evaluated = EvaluatedReading(
            node_id=node_id,
            node_type=node_type,
            timestamp=telemetry.timestamp,
            overall_status=overall,
            metric_evaluations=metric_evaluations,
            primary_metric=primary.metric if primary else None,
            primary_value=primary.value if primary else None,
            primary_status=primary.status if primary else None,
            primary_forecast=primary.forecast if primary else None,
        )

        # Track for dashboard
        self._latest_evaluations[node_id] = evaluated
        self._latest_node_types[node_id] = node_type

        # -- Persist to InfluxDB (non-blocking) --
        threading.Thread(
            target=self._influx_writer.write, args=(evaluated,), daemon=True
        ).start()

        # -- Publish alerts to RabbitMQ if CRITICAL (non-blocking) --
        def _publish_alerts():
            for me in metric_evaluations:
                if me.status == SafetyStatus.CRITICAL:
                    evaluator_map = {
                        "solar_power_w": self._solar_evaluator,
                        "power_factor": self._pf_evaluator,
                        "battery_soc_pct": self._battery_evaluator,
                        "grid_load_pct": self._grid_evaluator,
                        "person_count": self._occupancy_evaluator,
                        "flow_rate_lpm": self._water_evaluator,
                        "ac_power_w": self._ac_evaluator,
                    }
                    ev = evaluator_map.get(me.metric)
                    threshold = ev.critical_threshold if ev else 0
                    self._alert_publisher.publish(
                        metric=me.metric, value=me.value,
                        threshold=threshold,
                        severity=SafetyStatus.CRITICAL, node_id=node_id,
                        timestamp=telemetry.timestamp,
                        message=f"CRITICAL: {me.metric}={me.value} at {node_id}!",
                    )

        if any(s == SafetyStatus.CRITICAL for s in all_statuses):
            threading.Thread(target=_publish_alerts, daemon=True).start()

        status_icon = {"SAFE": "[OK]", "WARNING": "[WARN]", "CRITICAL": "[!!!]"}.get(overall.value, "[?]")
        metrics_str = " | ".join(f"{m.metric}={m.value}({m.status.value})" for m in metric_evaluations)
        print(f"[EnergyEvaluator] {status_icon} {node_id} ({node_type}) | {metrics_str} | Overall={overall.value}")

        return evaluated

    # ─────────────────────────────────────────────
    # Suggestion Engine (with Command Pattern semantics)
    # ─────────────────────────────────────────────

    def generate_suggestions(self) -> List[EnergySuggestion]:
        """
        Generate actionable Energy suggestions based on all current evaluations.
        Each suggestion includes a command_type representing the action to take
        (Command Pattern: turn_off, reduce_load, charge_battery, etc.)
        """
        suggestions = []
        now = datetime.datetime.now().isoformat()

        for node_id, evaluation in self._latest_evaluations.items():
            node_type = self._latest_node_types.get(node_id, "unknown")

            for me in evaluation.metric_evaluations:
                # ── Solar Power Suggestions ──
                if me.metric == "solar_power_w" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.URGENT,
                        category="solar",
                        title="☀️ Solar Panel Output Critical",
                        description=(
                            f"Solar output at {node_id} is only {me.value}W (below 50W threshold). "
                            f"Inspect panel for obstruction, damage, or inverter fault. "
                            f"Switch to grid/battery backup for affected buildings."
                        ),
                        affected_nodes=[node_id],
                        command_type="switch_to_grid_backup",
                        timestamp=now,
                    ))
                elif me.metric == "solar_power_w" and me.status == SafetyStatus.WARNING:
                    desc = f"Solar output at {node_id} is {me.value}W (below 200W). "
                    if me.forecast and me.forecast.trend == "falling":
                        desc += f"ML forecast predicts further decline to {me.forecast.predicted_value}W. Pre-emptively reduce non-essential loads."
                        sev = SuggestionSeverity.URGENT
                    else:
                        desc += "Likely cloud cover. Monitor and prepare backup power path."
                        sev = SuggestionSeverity.CAUTION
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=sev,
                        category="solar",
                        title="⚡ Low Solar Generation",
                        description=desc,
                        affected_nodes=[node_id],
                        command_type="reduce_non_essential_loads",
                        timestamp=now,
                    ))

                # ── Battery SoC Suggestions ──
                elif me.metric == "battery_soc_pct" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.EMERGENCY,
                        category="battery",
                        title="🔋 Battery Critically Low",
                        description=(
                            f"Battery at {node_id} is at {me.value}% SoC (below 20%). "
                            f"Initiate emergency load shedding. Turn off outdoor lampposts "
                            f"and non-essential campus lighting. Switch to grid power."
                        ),
                        affected_nodes=[node_id],
                        command_type="emergency_load_shed",
                        timestamp=now,
                    ))
                elif me.metric == "battery_soc_pct" and me.status == SafetyStatus.WARNING:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.CAUTION,
                        category="battery",
                        title="🔋 Battery Low",
                        description=(
                            f"Battery at {node_id} is at {me.value}% SoC. "
                            f"Consider reducing AC setpoints by 2°C and dimming outdoor lighting."
                        ),
                        affected_nodes=[node_id],
                        command_type="reduce_ac_setpoint",
                        timestamp=now,
                    ))

                # ── Grid Load Suggestions ──
                elif me.metric == "grid_load_pct" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.EMERGENCY,
                        category="grid",
                        title="⚡ Grid Transformer Overload",
                        description=(
                            f"Grid transformer {node_id} is at {me.value}% load (exceeds 90%). "
                            f"Immediate load shedding required. Turn off non-critical campus zones. "
                            f"Deploy battery reserves. Risk of transformer trip/fault."
                        ),
                        affected_nodes=[node_id],
                        command_type="emergency_grid_shed",
                        timestamp=now,
                    ))
                elif me.metric == "grid_load_pct" and me.status == SafetyStatus.WARNING:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.URGENT,
                        category="grid",
                        title="⚡ High Grid Load",
                        description=(
                            f"Grid load at {node_id} is {me.value}%. "
                            f"Stagger AC startup times across buildings. "
                            f"Activate demand-response protocols."
                        ),
                        affected_nodes=[node_id],
                        command_type="stagger_ac_startup",
                        timestamp=now,
                    ))

                # ── Power Factor Suggestions ──
                elif me.metric == "power_factor" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.URGENT,
                        category="efficiency",
                        title="📉 Severely Low Power Factor",
                        description=(
                            f"Power factor at {node_id} is {me.value} (below 0.80). "
                            f"Utility penalty charges apply. Inspect capacitor banks. "
                            f"Schedule power quality audit for the building."
                        ),
                        affected_nodes=[node_id],
                        command_type="inspect_capacitor_bank",
                        timestamp=now,
                    ))

                # ── Water Leak Suggestions ──
                elif me.metric == "flow_rate_lpm" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.EMERGENCY,
                        category="water",
                        title="💧 Water Leak Detected",
                        description=(
                            f"Water leak detected at {node_id}! Flow rate: {me.value} LPM. "
                            f"Shut off water pump for affected zone immediately. "
                            f"Dispatch maintenance team."
                        ),
                        affected_nodes=[node_id],
                        command_type="shut_water_pump",
                        timestamp=now,
                    ))

                # ── AC Overload Suggestions ──
                elif me.metric == "ac_power_w" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.URGENT,
                        category="hvac",
                        title="❄️ AC Unit Overload",
                        description=(
                            f"AC unit {node_id} is consuming {me.value}W (exceeds 3500W). "
                            f"Raise setpoint by 3°C or switch to fan-only mode. "
                            f"Risk of circuit breaker trip."
                        ),
                        affected_nodes=[node_id],
                        command_type="raise_ac_setpoint",
                        timestamp=now,
                    ))
                elif me.metric == "ac_power_w" and me.status == SafetyStatus.WARNING:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.CAUTION,
                        category="hvac",
                        title="❄️ High AC Consumption",
                        description=(
                            f"AC unit {node_id} is at {me.value}W. "
                            f"Consider raising setpoint by 1°C to reduce load."
                        ),
                        affected_nodes=[node_id],
                        command_type="optimize_ac_setpoint",
                        timestamp=now,
                    ))

                # ── Occupancy Suggestions ──
                elif me.metric == "person_count" and me.status == SafetyStatus.CRITICAL:
                    suggestions.append(EnergySuggestion(
                        id=f"SUG-{uuid.uuid4().hex[:8]}",
                        severity=SuggestionSeverity.URGENT,
                        category="efficiency",
                        title="👥 Zone Overcrowded",
                        description=(
                            f"Occupancy at {node_id} is {int(me.value)} persons (exceeds 100). "
                            f"Increase HVAC output for the zone. Verify fire code compliance."
                        ),
                        affected_nodes=[node_id],
                        command_type="boost_hvac_zone",
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
            suggestions.append(EnergySuggestion(
                id=f"SUG-{uuid.uuid4().hex[:8]}",
                severity=SuggestionSeverity.INFO,
                category="general",
                title="✅ All Clear — Campus Energy Grid Nominal",
                description="All energy metrics are within safe operating limits. Grid efficiency is optimal.",
                affected_nodes=[],
                command_type=None,
                timestamp=now,
            ))

        return suggestions

    # ─────────────────────────────────────────────
    # Dashboard Summary
    # ─────────────────────────────────────────────

    def get_dashboard_summary(self) -> EnergyDashboardSummary:
        """
        Aggregate all current evaluations into a campus-wide dashboard summary.
        """
        evaluations = list(self._latest_evaluations.values())
        total = len(evaluations)
        critical = sum(1 for e in evaluations if e.overall_status == SafetyStatus.CRITICAL)
        warning = sum(1 for e in evaluations if e.overall_status == SafetyStatus.WARNING)
        safe = sum(1 for e in evaluations if e.overall_status == SafetyStatus.SAFE)

        # Campus energy score: 100 = all safe, 0 = all critical
        if total > 0:
            score = ((safe * 100) + (warning * 50) + (critical * 0)) / total
        else:
            score = 100.0

        # Aggregate energy figures
        total_solar = 0
        total_consumption = 0
        battery_socs = []
        grid_loads = []

        for ev in evaluations:
            for me in ev.metric_evaluations:
                if me.metric == "solar_power_w":
                    total_solar += me.value
                elif me.metric in ("power_w", "ac_power_w"):
                    total_consumption += me.value
                elif me.metric == "battery_soc_pct":
                    battery_socs.append(me.value)
                elif me.metric == "grid_load_pct":
                    grid_loads.append(me.value)

        avg_battery = round(sum(battery_socs) / len(battery_socs), 1) if battery_socs else 0
        avg_grid = round(sum(grid_loads) / len(grid_loads), 1) if grid_loads else 0

        # Build metric cards
        metric_cards = self._build_metric_cards(evaluations)

        # Build node status list
        node_statuses = []
        for node_id, ev in self._latest_evaluations.items():
            last_value = {}
            for me in ev.metric_evaluations:
                last_value[me.metric] = me.value
            node_statuses.append(NodeStatus(
                node_id=node_id,
                node_type=self._latest_node_types.get(node_id, "unknown"),
                status=ev.overall_status,
                last_value=last_value,
                last_seen=ev.timestamp,
            ))

        suggestions = self.generate_suggestions()

        return EnergyDashboardSummary(
            campus_energy_score=round(score, 1),
            total_nodes=total,
            critical_count=critical,
            warning_count=warning,
            safe_count=safe,
            total_solar_generation_w=round(total_solar, 1),
            total_consumption_w=round(total_consumption, 1),
            avg_battery_soc=avg_battery,
            avg_grid_load=avg_grid,
            metric_cards=metric_cards,
            suggestions=suggestions,
            node_statuses=node_statuses,
            generated_at=datetime.datetime.now().isoformat(),
        )

    def _build_metric_cards(self, evaluations: list) -> dict:
        """Build aggregated metric summary cards for the dashboard."""
        cards = {}
        if not evaluations:
            return cards

        metric_map = {
            "solar_power_w": ("Solar Generation", "W"),
            "power_factor": ("Power Factor", "PF"),
            "battery_soc_pct": ("Battery SoC", "%"),
            "grid_load_pct": ("Grid Load", "%"),
            "person_count": ("Occupancy", "persons"),
            "flow_rate_lpm": ("Water Flow", "LPM"),
            "ac_power_w": ("AC Consumption", "W"),
            "power_w": ("Power Consumption", "W"),
        }

        for metric_key, (label, unit) in metric_map.items():
            vals = []
            for e in evaluations:
                for me in e.metric_evaluations:
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

        history_configs = [
            ("solar_forecast", self._solar_history, "solar_power_w"),
            ("power_factor_forecast", self._power_history, "power_factor"),
            ("battery_forecast", self._battery_history, "battery_soc_pct"),
            ("grid_load_forecast", self._grid_history, "grid_load_pct"),
            ("ac_forecast", self._ac_history, "ac_power_w"),
            ("water_forecast", self._water_history, "flow_rate_lpm"),
        ]

        for key, history, metric_name in history_configs:
            if node_id in history and len(history[node_id]) >= 3:
                result[key] = self._predictor.predict(
                    list(history[node_id]), metric_name=metric_name
                ).dict()

        if not result:
            return None
        result["node_id"] = node_id
        result["generated_at"] = datetime.datetime.now().isoformat()
        return result

    # ─────────────────────────────────────────────
    # Visualization Data
    # ─────────────────────────────────────────────

    def get_visualization_data(self, metric: str = "solar_power_w", limit: int = 50) -> dict:
        """
        Returns time-series visualization data for a specific metric across all nodes.
        Suitable for charting libraries (Chart.js, D3, etc.)
        """
        history_map = {
            "solar_power_w": self._solar_history,
            "power_factor": self._power_history,
            "battery_soc_pct": self._battery_history,
            "grid_load_pct": self._grid_history,
            "ac_power_w": self._ac_history,
            "flow_rate_lpm": self._water_history,
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
        with its latest critical metric value and status.
        """
        heatmap = []
        for node_id, evaluation in self._latest_evaluations.items():
            entry = {
                "node_id": node_id,
                "node_type": self._latest_node_types.get(node_id, "unknown"),
                "status": evaluation.overall_status.value,
            }
            for me in evaluation.metric_evaluations:
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
    def _compute_overall_from_list(statuses: List[SafetyStatus]) -> SafetyStatus:
        """Worst-case aggregation over a list of statuses."""
        if SafetyStatus.CRITICAL in statuses:
            return SafetyStatus.CRITICAL
        if SafetyStatus.WARNING in statuses:
            return SafetyStatus.WARNING
        return SafetyStatus.SAFE
