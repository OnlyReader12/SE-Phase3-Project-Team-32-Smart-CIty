"""
persistence/influx_writer.py — InfluxDB Bulk-Write Client.

Writes the fully-evaluated Energy readings to InfluxDB via TCP.
Uses the official influxdb-client Python SDK.

Why InfluxDB? (ADR-007):
  - 300 sensor nodes firing every few seconds = massive write throughput.
  - Built-in 30-day Data Retention Policy satisfies the Researcher API constraint.
  - Native time-series windowing queries for ML analytics.

Boundary rules:
  ✅ Writes evaluated Energy data with rich tags (node_id, status, metric_type)
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
    Handles all InfluxDB write operations for the Energy Engine.
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
            # Quick socket-level check to see if InfluxDB is reachable
            import socket
            host = self._url.replace("http://", "").replace("https://", "").split(":")[0]
            port = int(self._url.split(":")[-1].rstrip("/")) if ":" in self._url.split("//")[-1] else 8086
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                raise ConnectionError(f"Cannot reach {host}:{port}")

            self._client    = InfluxDBClient(url=self._url, token=self._token, org=self._org, timeout=2000)
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            print(f"[InfluxWriter] Connected to InfluxDB at {self._url}")
        except Exception as e:
            print(f"[InfluxWriter] WARNING: Could not connect to InfluxDB: {e}")
            print("[InfluxWriter] Running in dry-run mode -- data will be logged only.")
            self._client = None
            self._write_api = None

    def write(self, reading: EvaluatedReading) -> bool:
        """
        Write one evaluated Energy reading to InfluxDB.

        Creates one data point per metric evaluation so each metric can be
        queried independently by dashboards and the Researcher API (Member 5).

        Tags:   node_id, node_type, metric_type, status  ← filterable dimensions
        Fields: value, forecast_value, confidence, trend  ← numeric data
        """
        try:
            points = []

            for me in reading.metric_evaluations:
                point = (
                    Point("energy_telemetry")
                    .tag("domain", "energy")
                    .tag("node_id", reading.node_id)
                    .tag("node_type", reading.node_type)
                    .tag("metric_type", me.metric)
                    .tag("status", me.status.value)
                    .field("value", me.value)
                )
                if me.forecast:
                    point = (
                        point
                        .field("forecast_value", me.forecast.predicted_value)
                        .field("forecast_confidence", me.forecast.confidence)
                        .tag("trend", me.forecast.trend)
                        .tag("ml_model", me.forecast.model)
                    )
                points.append(point)

            # ── Bulk-write all points ──
            if self._write_api and points:
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
