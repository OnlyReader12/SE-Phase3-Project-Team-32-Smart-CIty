"""
MetricsService — Shared analytics computation layer.
Provides: SMA trend, time-to-breach prediction, zone aggregation.
Used by /metrics/* endpoints in both engines.
"""
from datetime import datetime, timedelta
import statistics


class MetricsService:

    @staticmethod
    def simple_moving_average(series: list[float], window: int = 3) -> list[float]:
        """
        Compute SMA over a rolling window.
        Returns a list of the same length (first (window-1) values = None).
        """
        result = []
        for i in range(len(series)):
            if i < window - 1:
                result.append(None)
            else:
                result.append(statistics.mean(series[i - window + 1: i + 1]))
        return result

    @staticmethod
    def predict_next(series: list[float], steps: int = 3) -> list[float]:
        """
        Predict next N values using SMA-3 extrapolation.
        Simple, no ML needed. Analysts see a dashed continuation on the chart.
        """
        working = list(series)
        predictions = []
        for _ in range(steps):
            if len(working) >= 3:
                next_val = statistics.mean(working[-3:])
            else:
                next_val = working[-1] if working else 0
            predictions.append(round(next_val, 3))
            working.append(next_val)
        return predictions

    @staticmethod
    def time_to_breach(current: float, threshold: float, rate_per_min: float) -> float | None:
        """
        Returns estimated minutes until a threshold is breached.
        Returns None if rate is not moving towards threshold.
        E.g. "PM2.5 will breach limit in ~12 min at current rate."
        """
        if rate_per_min == 0:
            return None
        delta = threshold - current
        if (delta > 0 and rate_per_min < 0) or (delta < 0 and rate_per_min > 0):
            return None  # Moving away from threshold
        minutes = abs(delta / rate_per_min)
        return round(minutes, 1)

    @staticmethod
    def aggregate_zone(readings: list[dict], param: str) -> dict:
        """
        Aggregate a numeric parameter across all nodes in the readings.
        Returns {avg, min, max, total, count}.
        """
        values = [
            r["data"][param]
            for r in readings
            if "data" in r and param in r["data"] and r["data"][param] is not None
        ]
        if not values:
            return {"avg": None, "min": None, "max": None, "total": None, "count": 0}
        return {
            "avg":   round(statistics.mean(values), 3),
            "min":   round(min(values), 3),
            "max":   round(max(values), 3),
            "total": round(sum(values), 3),
            "count": len(values),
        }

    @staticmethod
    def extract_timeseries(readings: list[dict], node_id: str, param: str) -> list[dict]:
        """
        Extract {ts, value} pairs from a flat list of readings for one node+param.
        """
        result = []
        for r in readings:
            if r.get("node_id") == node_id and "data" in r and param in r["data"]:
                result.append({
                    "ts":    r.get("timestamp", datetime.utcnow().isoformat()),
                    "value": r["data"][param],
                })
        return result
