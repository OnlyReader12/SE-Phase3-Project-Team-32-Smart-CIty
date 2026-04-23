"""Q1 — Air Quality: PM2.5, CO2, NO2, O3 threshold violations."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class AirQualityRule(AnalysisRule):
    rule_id = "air_quality"
    domain  = "ehs"

    def get_default_thresholds(self):
        return {
            "pm2_5_warning_ugm3": 25,
            "pm2_5_critical_ugm3": 50,
            "co2_warning_ppm": 800,
            "co2_critical_ppm": 1000,
            "no2_limit_ppb": 53,
            "o3_limit_ppb": 70,
        }

    def analyse(self, readings, thresholds):
        alerts = []
        nodes = [r for r in readings if any(t in r.get("node_type", "").lower()
                 for t in ["air_quality", "environmental"])]

        for node in nodes:
            d = node.get("data", {})
            nid, zone = node.get("node_id"), node.get("zone")

            pm25 = d.get("pm2_5")
            if pm25 is not None:
                if pm25 > thresholds["pm2_5_critical_ugm3"]:
                    alerts.append(AlertPayload("air_quality", "CRITICAL",
                        f"PM2.5 CRITICAL: {pm25:.1f} μg/m³ at {nid}",
                        nid, zone, "ehs", "pm2_5", pm25, thresholds["pm2_5_critical_ugm3"]))
                elif pm25 > thresholds["pm2_5_warning_ugm3"]:
                    alerts.append(AlertPayload("air_quality", "WARNING",
                        f"PM2.5 elevated: {pm25:.1f} μg/m³ at {nid}",
                        nid, zone, "ehs", "pm2_5", pm25, thresholds["pm2_5_warning_ugm3"]))

            co2 = d.get("co2")
            if co2 is not None:
                if co2 > thresholds["co2_critical_ppm"]:
                    alerts.append(AlertPayload("air_quality", "CRITICAL",
                        f"CO2 CRITICAL: {co2:.0f} ppm at {nid} — ventilate immediately",
                        nid, zone, "ehs", "co2", co2, thresholds["co2_critical_ppm"]))
                elif co2 > thresholds["co2_warning_ppm"]:
                    alerts.append(AlertPayload("air_quality", "WARNING",
                        f"CO2 elevated: {co2:.0f} ppm at {nid}",
                        nid, zone, "ehs", "co2", co2, thresholds["co2_warning_ppm"]))

            no2 = d.get("no2")
            if no2 is not None and no2 > thresholds["no2_limit_ppb"]:
                alerts.append(AlertPayload("air_quality", "CRITICAL",
                    f"NO2 exceeds WHO limit: {no2:.1f} ppb at {nid}",
                    nid, zone, "ehs", "no2", no2, thresholds["no2_limit_ppb"]))
        return alerts
