"""Q1 — Power Balance: Generation vs Consumption."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.base_engine import AnalysisRule, AlertPayload


class PowerBalanceRule(AnalysisRule):
    rule_id = "power_balance"
    domain  = "energy"

    def get_default_thresholds(self):
        return {
            "solar_drop_pct": 40,          # % drop in 5 min triggers warning
            "sustained_deficit_min": 10,   # minutes consumption > generation
            "grid_overload_pct": 90,       # grid load % threshold
        }

    def analyse(self, readings: list[dict], thresholds: dict) -> list[AlertPayload]:
        alerts = []
        solar    = [r for r in readings if "solar" in r.get("node_type", "").lower()]
        meters   = [r for r in readings if "energy_meter" in r.get("node_type", "").lower()]
        grid     = [r for r in readings if "grid" in r.get("node_type", "").lower()]

        # Grid overload check
        for g in grid:
            load = g.get("data", {}).get("load_percent")
            if load is not None and load > thresholds.get("grid_overload_pct", 90):
                alerts.append(AlertPayload(
                    rule_id="power_balance",
                    severity="CRITICAL",
                    message=f"Grid overload: {load:.1f}% load on {g.get('node_id')}",
                    node_id=g.get("node_id"),
                    zone_id=g.get("zone"),
                    domain="energy",
                    metric_key="load_percent",
                    metric_value=load,
                    threshold_value=thresholds.get("grid_overload_pct", 90),
                ))

        # Net balance: total solar vs total consumption
        total_solar = sum(r.get("data", {}).get("power_w", 0) / 1000 for r in solar)
        total_use   = sum(r.get("data", {}).get("power", 0) / 1000 for r in meters)
        if total_solar > 0 and total_use > 0 and total_use > total_solar * 1.2:
            alerts.append(AlertPayload(
                rule_id="power_balance",
                severity="WARNING",
                message=f"Consumption ({total_use:.2f} kW) exceeds solar generation ({total_solar:.2f} kW)",
                node_id=None,
                zone_id=None,
                domain="energy",
                metric_key="net_balance_kw",
                metric_value=total_use - total_solar,
                threshold_value=0,
            ))
        return alerts
