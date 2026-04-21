"""
persistence/influx_writer.py — InfluxDB Bulk-Write Client.

Writes the fully-evaluated EHS readings to InfluxDB via TCP.
Uses the official influxdb-client Python SDK.

Why InfluxDB? (ADR-007):
  - 300 sensor nodes firing every few seconds = massive write throughput.
  - Built-in 30-day Data Retention Policy satisfies the Researcher API constraint.
  - Native time-series windowing queries for ML analytics.

Boundary rules:
  ✅ Writes evaluated EHS data with rich tags (node_id, status, metric_type)
  ✅ Includes forecast predictions as additional fields
  ❌ Does NOT write user credentials or RBAC data (that's PostgreSQL / Member 5)
"""

import datetime
from typing import Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from models.schemas import EvaluatedReading


class InfluxWriter:
    """
    Handles all InfluxDB write operations for the EHS Engine.
    Uses a synchronous write API for simplicity inside the evaluation pipeline.
    """

    def __init__(self, url: str, token: str, org: str, bucket: str):
        self._url    = url
        self._token  = token
        self._org    = org
        self._bucket = bucket
        self._client     = None
        self._write_api  = None
        self._connect()

    def _connect(self):
        """Establish connection to InfluxDB."""
        try:
            self._client    = InfluxDBClient(url=self._url, token=self._token, org=self._org)
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            print(f"[InfluxWriter] Connected to InfluxDB at {self._url}")
        except Exception as e:
            print(f"[InfluxWriter] WARNING: Could not connect to InfluxDB: {e}")
            print("[InfluxWriter] Running in dry-run mode — data will be logged only.")

    def write(self, reading: EvaluatedReading) -> bool:
        """
        Write one evaluated EHS reading to InfluxDB.

        Creates two data points per reading (one for AQI, one for water pH)
        so each metric can be queried independently by dashboards and the
        Researcher API (Member 5).

        Tags:   node_id, metric_type, status  ← filterable dimensions
        Fields: value, forecast_value, confidence, trend  ← numeric data
        """
        try:
            points = []

            # ── AQI Data Point ──
            aqi_point = (
                Point("ehs_telemetry")
                .tag("domain", "ehs")
                .tag("node_id", reading.node_id)
                .tag("metric_type", "aqi")
                .tag("status", reading.aqi_status.value)
                .field("value", reading.aqi_value)
            )
            if reading.aqi_forecast:
                aqi_point = (
                    aqi_point
                    .field("forecast_value", reading.aqi_forecast.predicted_value)
                    .field("forecast_confidence", reading.aqi_forecast.confidence)
                    .tag("trend", reading.aqi_forecast.trend)
                    .tag("ml_model", reading.aqi_forecast.model)
                )
            points.append(aqi_point)

            # ── Water pH Data Point ──
            ph_point = (
                Point("ehs_telemetry")
                .tag("domain", "ehs")
                .tag("node_id", reading.node_id)
                .tag("metric_type", "water_ph")
                .tag("status", reading.water_ph_status.value)
                .field("value", reading.water_ph_value)
            )
            if reading.water_ph_forecast:
                ph_point = (
                    ph_point
                    .field("forecast_value", reading.water_ph_forecast.predicted_value)
                    .field("forecast_confidence", reading.water_ph_forecast.confidence)
                    .tag("trend", reading.water_ph_forecast.trend)
                )
            points.append(ph_point)

            # ── Bulk-write both points ──
            if self._write_api:
                self._write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=points,
                    write_precision=WritePrecision.S,
                )
                return True
            else:
                # Dry-run: log data for local development without InfluxDB
                for p in points:
                    print(f"[InfluxWriter|DRY-RUN] {p.to_line_protocol()}")
                return True

        except Exception as e:
            print(f"[InfluxWriter] ERROR writing data: {e}")
            return False

    def close(self):
        """Clean up InfluxDB client connections on shutdown."""
        if self._client:
            self._client.close()
            print("[InfluxWriter] Connection closed.")
