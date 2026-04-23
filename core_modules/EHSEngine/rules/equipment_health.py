"""Q5 — Equipment Health: Motor temperature, vibration, filter pressure."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class EquipmentHealthRule(AnalysisRule):
    rule_id = "equipment_health"
    domain  = "ehs"

    def get_default_thresholds(self):
        return {
            "max_motor_temp_c": 75,
            "max_filter_pressure_pa": 500,
            "vibration_high_label": "HIGH",  # string label from telemetry
        }

    def analyse(self, readings, thresholds):
        alerts = []
        equipment = [r for r in readings if any(t in r.get("node_type", "").lower()
                     for t in ["water_pump", "ventilation", "hvac", "air_purification"])]

        for node in equipment:
            d = node.get("data", {})
            nid, zone = node.get("node_id"), node.get("zone")

            # Infer motor temperature from power usage if explicit field absent
            motor_temp = d.get("motor_temp_c")
            if motor_temp is None:
                # Rough heuristic: power_usage > 5 kW && state = ON → assume warm
                power = d.get("power_usage", 0) or 0
                if power > 5 and d.get("state") == "ON":
                    motor_temp = 60 + (power - 5) * 5  # crude estimate

            if motor_temp is not None and motor_temp > thresholds["max_motor_temp_c"]:
                alerts.append(AlertPayload("equipment_health", "CRITICAL",
                    f"Motor overheating: {nid} at {motor_temp:.1f}°C",
                    nid, zone, "ehs", "motor_temp_c", motor_temp, thresholds["max_motor_temp_c"]))

            vibration = d.get("vibration_level")
            if vibration is not None and str(vibration).upper() == thresholds["vibration_high_label"]:
                alerts.append(AlertPayload("equipment_health", "WARNING",
                    f"High vibration detected at {nid} — possible bearing failure",
                    nid, zone, "ehs", "vibration_level", 1, 0))

            filter_pa = d.get("filter_pressure_pa")
            if filter_pa is not None and filter_pa > thresholds["max_filter_pressure_pa"]:
                alerts.append(AlertPayload("equipment_health", "WARNING",
                    f"Filter clogged at {nid}: {filter_pa:.0f} Pa (limit {thresholds['max_filter_pressure_pa']} Pa)",
                    nid, zone, "ehs", "filter_pressure_pa", filter_pa, thresholds["max_filter_pressure_pa"]))
        return alerts
