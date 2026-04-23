"""Q5 — EV Peak Load: Multiple EV chargers simultaneously active."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class EVPeakLoadRule(AnalysisRule):
    rule_id = "ev_peak_load"
    domain  = "energy"

    def get_default_thresholds(self):
        return {
            "max_concurrent_chargers": 3,
            "grid_stress_pct": 80,
        }

    def analyse(self, readings, thresholds):
        alerts = []
        # Proxy: high-occupancy parking zone nodes = EV charging activity
        parking = [r for r in readings 
                   if r.get("zone", "").upper() in ("PARKING", "EV") and
                      "occupancy" in r.get("node_type", "").lower()]
        active = [r for r in parking if (r.get("data", {}).get("count") or 0) > 0]

        if len(active) >= thresholds["max_concurrent_chargers"]:
            grid_nodes = [r for r in readings if "grid" in r.get("node_type", "").lower()]
            severity = "WARNING"
            for g in grid_nodes:
                if (g.get("data", {}).get("load_percent") or 0) > thresholds["grid_stress_pct"]:
                    severity = "CRITICAL"
                    break

            alerts.append(AlertPayload(
                rule_id="ev_peak_load",
                severity=severity,
                message=f"{len(active)} EV chargers concurrently active (limit: {thresholds['max_concurrent_chargers']})",
                node_id=None,
                zone_id="PARKING",
                domain="energy",
                metric_key="concurrent_ev_count",
                metric_value=len(active),
                threshold_value=thresholds["max_concurrent_chargers"],
            ))
        return alerts
