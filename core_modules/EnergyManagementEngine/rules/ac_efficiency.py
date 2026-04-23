"""Q2 — AC Efficiency: High power, low cooling delta = waste."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class ACEfficiencyRule(AnalysisRule):
    rule_id = "ac_efficiency"
    domain  = "energy"

    def get_default_thresholds(self):
        return {
            "efficiency_min_delta_c": 1.0,   # min cooling delta for efficient operation
            "overload_delta_c": 5.0,          # temp still too high despite AC on
            "high_power_kw": 2.0,             # what counts as "high power for an AC"
        }

    def analyse(self, readings, thresholds):
        alerts = []
        ac_units = [r for r in readings if "ac_unit" in r.get("node_type", "").lower()]

        for ac in ac_units:
            d = ac.get("data", {})
            power      = d.get("power_usage", 0) or 0
            current    = d.get("current_temp")
            set_temp   = d.get("set_temp")
            state      = d.get("state", "OFF")

            if state != "ON" or current is None or set_temp is None:
                continue

            delta = abs(current - set_temp)
            high_power = power > thresholds.get("high_power_kw", 2.0)

            if high_power and delta < thresholds.get("efficiency_min_delta_c", 1.0):
                alerts.append(AlertPayload(
                    rule_id="ac_efficiency",
                    severity="WARNING",
                    message=f"AC {ac.get('node_id')} inefficient: {power:.1f}kW but only {delta:.1f}°C delta",
                    node_id=ac.get("node_id"),
                    zone_id=ac.get("zone"),
                    domain="energy",
                    metric_key="temp_delta_c",
                    metric_value=delta,
                    threshold_value=thresholds.get("efficiency_min_delta_c", 1.0),
                ))
            elif delta > thresholds.get("overload_delta_c", 5.0):
                alerts.append(AlertPayload(
                    rule_id="ac_efficiency",
                    severity="CRITICAL",
                    message=f"AC {ac.get('node_id')} overloaded: room still {delta:.1f}°C above setpoint",
                    node_id=ac.get("node_id"),
                    zone_id=ac.get("zone"),
                    domain="energy",
                    metric_key="temp_delta_c",
                    metric_value=delta,
                    threshold_value=thresholds.get("overload_delta_c", 5.0),
                ))
        return alerts
