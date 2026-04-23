"""Q3 — Light Waste: Lights ON with no occupancy detected."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from datetime import datetime
from shared.base_engine import AnalysisRule, AlertPayload


class LightWasteRule(AnalysisRule):
    rule_id = "light_waste"
    domain  = "energy"

    def get_default_thresholds(self):
        return {
            "min_footfall": 3,         # footfall below this = "unoccupied"
            "daylight_start_hour": 6,  # lamps outside shouldn't be on
            "daylight_end_hour": 19,
        }

    def analyse(self, readings, thresholds):
        alerts = []
        lights    = {r.get("zone"): r for r in readings 
                     if any(t in r.get("node_type", "").lower() 
                            for t in ["lighting", "lamp_post"])}
        footfalls = {r.get("zone"): r for r in readings 
                     if "occupancy" in r.get("node_type", "").lower() or 
                        "footfall"  in r.get("node_type", "").lower()}

        for zone, light in lights.items():
            if light.get("data", {}).get("state") != "ON":
                continue

            occ = footfalls.get(zone)
            if occ is None:
                continue

            count = occ.get("data", {}).get("count", 0) or 0
            if count < thresholds.get("min_footfall", 3):
                alerts.append(AlertPayload(
                    rule_id="light_waste",
                    severity="WARNING",
                    message=f"Lights ON in zone {zone} but only {count} people detected",
                    node_id=light.get("node_id"),
                    zone_id=zone,
                    domain="energy",
                    metric_key="occupancy_count",
                    metric_value=count,
                    threshold_value=thresholds.get("min_footfall", 3),
                ))

        # Outdoor lamp post during daylight hours
        now_hour = datetime.utcnow().hour
        day_start = thresholds.get("daylight_start_hour", 6)
        day_end   = thresholds.get("daylight_end_hour", 19)
        for r in readings:
            if "lamp_post" in r.get("node_type", "").lower():
                if r.get("data", {}).get("state") == "ON" and day_start <= now_hour < day_end:
                    alerts.append(AlertPayload(
                        rule_id="light_waste",
                        severity="INFO",
                        message=f"Lamp post {r.get('node_id')} ON during daylight hours",
                        node_id=r.get("node_id"),
                        zone_id=r.get("zone"),
                        domain="energy",
                        metric_key="daylight_hour",
                        metric_value=now_hour,
                        threshold_value=day_end,
                    ))
        return alerts
