"""Q4 — Battery Health: Low SOC during peak hours, excessive discharge."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from datetime import datetime
from shared.base_engine import AnalysisRule, AlertPayload


class BatteryHealthRule(AnalysisRule):
    rule_id = "battery_health"
    domain  = "energy"

    def get_default_thresholds(self):
        return {
            "low_soc_pct": 20,
            "peak_hour_start": 9,
            "peak_hour_end": 20,
        }

    def analyse(self, readings, thresholds):
        alerts = []
        batteries = [r for r in readings 
                     if "battery" in r.get("node_type", "").lower() or 
                        "storage" in r.get("node_type", "").lower()]
        now_hour = datetime.utcnow().hour
        is_peak  = thresholds["peak_hour_start"] <= now_hour < thresholds["peak_hour_end"]

        for bat in batteries:
            d   = bat.get("data", {})
            soc = d.get("soc")
            if soc is None:
                continue

            if soc < thresholds["low_soc_pct"] and is_peak:
                alerts.append(AlertPayload(
                    rule_id="battery_health",
                    severity="CRITICAL",
                    message=f"Battery {bat.get('node_id')} at {soc:.1f}% SOC during peak hours",
                    node_id=bat.get("node_id"),
                    zone_id=bat.get("zone"),
                    domain="energy",
                    metric_key="soc",
                    metric_value=soc,
                    threshold_value=thresholds["low_soc_pct"],
                ))
        return alerts
