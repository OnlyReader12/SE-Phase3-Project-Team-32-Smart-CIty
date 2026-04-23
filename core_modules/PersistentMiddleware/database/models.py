"""
SQLAlchemy ORM model for the Persistent Middleware.

TelemetryRecord stores the full SmartCityObject received from the
Ingestion Engine via RabbitMQ.  It adds node_type, state, and
health_status columns to support richer querying by Domain Engines.

NOTE: If you already have an existing edge_persistence.db from a previous
version, delete it and let SQLAlchemy recreate it with the new schema:
    rm core_modules/PersistentMiddleware/edge_persistence.db
"""
import json
from sqlalchemy import Column, Integer, String, Text
from database.db_core import Base


class TelemetryRecord(Base):
    """
    Persists one normalised SmartCityObject per IoT node emission.

    Columns
    -------
    node_id         Unique node identifier   e.g. SOLAR-PANEL-001
    node_type       Schema type key          e.g. solar_panel
    domain          energy | water | air
    protocol_source How it arrived           HTTP_POST / MQTT_PUB / CoAP_PUT / WebSocket
    timestamp       ISO-8601 UTC string from the node
    state           ON / OFF / RUNNING / OPEN / … (nullable)
    health_status   OK / DEGRADED / FAILED   (nullable)
    location_json   JSON string of {latitude, longitude, zone, name}
    payload_json    JSON string of domain-specific sensor readings
    """
    __tablename__ = "telemetry_records"

    id              = Column(Integer, primary_key=True, index=True)
    node_id         = Column(String, index=True, nullable=False)
    node_type       = Column(String, index=True, nullable=False, default="unknown")
    domain          = Column(String, index=True, nullable=False)
    protocol_source = Column(String, nullable=False)
    timestamp       = Column(String, nullable=False)
    state           = Column(String, nullable=True)
    health_status   = Column(String, nullable=True)
    location_json   = Column(Text,  nullable=True)   # JSON string
    payload_json    = Column(Text,  nullable=False)  # JSON string

    def payload_dict(self) -> dict:
        """Deserialise the stored JSON payload to a Python dict."""
        try:
            return json.loads(self.payload_json)
        except Exception:
            return {}

    def location_dict(self) -> dict:
        """Deserialise the stored JSON location to a Python dict."""
        try:
            return json.loads(self.location_json) if self.location_json else {}
        except Exception:
            return {}
