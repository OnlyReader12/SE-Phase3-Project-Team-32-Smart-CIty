"""Q3 — Water Safety: Dry run detection, leaks, low reservoir."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class WaterSafetyRule(AnalysisRule):
    rule_id = "water_safety"
    domain  = "ehs"

    def get_default_thresholds(self):
        return {
            "dry_run_min_flow_lpm": 2.0,   # below this while pump ON = dry run
            "low_reservoir_pct": 20,
            "flow_spike_multiplier": 2.0,  # N× average = suspected leak
        }

    def analyse(self, readings, thresholds):
        alerts = []
        pumps     = [r for r in readings if "water_pump" in r.get("node_type", "").lower()]
        meters    = [r for r in readings if "water_meter" in r.get("node_type", "").lower()]
        reservoirs = [r for r in readings if "reservoir" in r.get("node_type", "").lower()]

        # Dry run detection (most critical)
        for pump in pumps:
            d = pump.get("data", {})
            state     = d.get("state", "OFF")
            flow_rate = d.get("flow_level") or d.get("flow_rate_lpm") or 0
            if state == "ON" and flow_rate < thresholds["dry_run_min_flow_lpm"]:
                alerts.append(AlertPayload("water_safety", "CRITICAL",
                    f"DRY RUN detected: Pump {pump.get('node_id')} ON but flow={flow_rate} LPM",
                    pump.get("node_id"), pump.get("zone"), "ehs",
                    "flow_rate_lpm", flow_rate, thresholds["dry_run_min_flow_lpm"]))

        # Low reservoir
        for res in reservoirs:
            level = res.get("data", {}).get("level_percent")
            if level is not None and level < thresholds["low_reservoir_pct"]:
                alerts.append(AlertPayload("water_safety", "WARNING",
                    f"Low reservoir: {res.get('node_id')} at {level:.1f}%",
                    res.get("node_id"), res.get("zone"), "ehs",
                    "level_percent", level, thresholds["low_reservoir_pct"]))

        # Leak detection: flow meter reporting anomalous flow
        for meter in meters:
            d = meter.get("data", {})
            leak   = d.get("leak_detected", False)
            if leak:
                alerts.append(AlertPayload("water_safety", "CRITICAL",
                    f"Leak detected by {meter.get('node_id')} in zone {meter.get('zone')}",
                    meter.get("node_id"), meter.get("zone"), "ehs",
                    "leak_detected", 1, 0))
        return alerts
