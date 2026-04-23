"""
HTTP POST adapter.
Receives raw JSON from aiohttp HttpSender nodes (POST /api/telemetry)
and normalises it into SmartCityObject.

Key fix: reads "payload" key (IOT_Node canonical field), NOT legacy "data".
"""
from models.domain import SmartCityObject
from adapters.base import ProtocolAdapter


class HttpAdapter(ProtocolAdapter):
    """
    Translates an HTTP POST body into SmartCityObject and forwards it
    to the Persistent Middleware via RabbitMQForwarder.

    Expected body keys (IOT_Node schema):
        node_id, node_type, domain, timestamp, state, health_status,
        location, payload
    """

    def standard_parse(self, raw_data: dict) -> SmartCityObject:
        try:
            return SmartCityObject(
                node_id=raw_data.get("node_id", "unknown"),
                node_type=raw_data.get("node_type", "unknown"),
                domain=raw_data.get("domain", "unknown"),
                timestamp=raw_data.get("timestamp", ""),
                state=raw_data.get("state"),
                health_status=raw_data.get("health_status", "OK"),
                location=raw_data.get("location"),
                payload=raw_data.get("payload", {}),
                protocol_source="HTTP_POST",
            )
        except Exception as exc:
            print(f"[HTTP Adapter] Parse error: {exc}")
            return None
