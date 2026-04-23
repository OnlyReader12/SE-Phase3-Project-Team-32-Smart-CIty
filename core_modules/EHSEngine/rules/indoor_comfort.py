"""Q2 — Indoor Comfort: Temp, Humidity, CO2 comfort violation."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class IndoorComfortRule(AnalysisRule):
    rule_id = "indoor_comfort"
    domain  = "ehs"

    def get_default_thresholds(self):
        return {
            "max_temp_c": 30,
            "max_humidity_pct": 70,
            "co2_poor_ppm": 800,
        }

    def analyse(self, readings, thresholds):
        alerts = []
        nodes = [r for r in readings if any(t in r.get("node_type", "").lower()
                 for t in ["temp_humidity", "temperature", "hvac"])]

        for node in nodes:
            d = node.get("data", {})
            nid, zone = node.get("node_id"), node.get("zone")

            temp = d.get("temperature")
            if temp is not None and temp > thresholds["max_temp_c"]:
                alerts.append(AlertPayload("indoor_comfort", "WARNING",
                    f"Overheating in {zone}: {temp:.1f}°C at {nid}",
                    nid, zone, "ehs", "temperature", temp, thresholds["max_temp_c"]))

            humidity = d.get("humidity")
            if humidity is not None and humidity > thresholds["max_humidity_pct"]:
                alerts.append(AlertPayload("indoor_comfort", "WARNING",
                    f"High humidity in {zone}: {humidity:.1f}% at {nid}",
                    nid, zone, "ehs", "humidity", humidity, thresholds["max_humidity_pct"]))

            co2 = d.get("co2") or d.get("co2_ppm")
            if co2 is not None and co2 > thresholds["co2_poor_ppm"]:
                alerts.append(AlertPayload("indoor_comfort", "WARNING",
                    f"Poor ventilation in {zone}: CO2 {co2:.0f} ppm at {nid}",
                    nid, zone, "ehs", "co2_ppm", co2, thresholds["co2_poor_ppm"]))
        return alerts
