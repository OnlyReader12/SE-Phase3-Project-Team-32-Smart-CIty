"""Q4 — Water Quality: pH, turbidity, TDS threshold violations."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class WaterQualityRule(AnalysisRule):
    rule_id = "water_quality"
    domain  = "ehs"

    def get_default_thresholds(self):
        return {
            "ph_min": 6.5, "ph_max": 8.5,
            "turbidity_warning_ntu": 1.0,
            "turbidity_critical_ntu": 4.0,
            "tds_max_mgl": 500,
        }

    def analyse(self, readings, thresholds):
        alerts = []
        nodes = [r for r in readings if "water_quality" in r.get("node_type", "").lower()]

        for node in nodes:
            d = node.get("data", {})
            nid, zone = node.get("node_id"), node.get("zone")

            ph = d.get("ph")
            if ph is not None:
                if ph < thresholds["ph_min"] or ph > thresholds["ph_max"]:
                    alerts.append(AlertPayload("water_quality", "CRITICAL",
                        f"pH out of safe range: {ph:.2f} at {nid} (safe: {thresholds['ph_min']}–{thresholds['ph_max']})",
                        nid, zone, "ehs", "ph", ph, thresholds["ph_max"]))

            turbidity = d.get("turbidity")
            if turbidity is not None:
                if turbidity > thresholds["turbidity_critical_ntu"]:
                    alerts.append(AlertPayload("water_quality", "CRITICAL",
                        f"Turbidity CRITICAL: {turbidity:.2f} NTU at {nid}",
                        nid, zone, "ehs", "turbidity", turbidity, thresholds["turbidity_critical_ntu"]))
                elif turbidity > thresholds["turbidity_warning_ntu"]:
                    alerts.append(AlertPayload("water_quality", "WARNING",
                        f"Turbidity elevated: {turbidity:.2f} NTU at {nid}",
                        nid, zone, "ehs", "turbidity", turbidity, thresholds["turbidity_warning_ntu"]))

            tds = d.get("tds")
            if tds is not None and tds > thresholds["tds_max_mgl"]:
                alerts.append(AlertPayload("water_quality", "WARNING",
                    f"TDS exceeds limit: {tds:.0f} mg/L at {nid}",
                    nid, zone, "ehs", "tds", tds, thresholds["tds_max_mgl"]))

            if d.get("contamination_level", 0) and d["contamination_level"] > 0:
                alerts.append(AlertPayload("water_quality", "CRITICAL",
                    f"Contamination detected at {nid}!",
                    nid, zone, "ehs", "contamination_level", d["contamination_level"], 0))
        return alerts
