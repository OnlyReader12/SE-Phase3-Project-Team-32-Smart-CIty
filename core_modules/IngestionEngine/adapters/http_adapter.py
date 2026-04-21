import json
from models.domain import SmartCityObject
from adapters.base import ProtocolAdapter

class HttpAdapter(ProtocolAdapter):
    """
    Translates incoming HTTP POST raw JSON into the SmartCityObject.
    """
    def standard_parse(self, raw_data: dict) -> SmartCityObject:
        try:
            return SmartCityObject(
                node_id=raw_data.get("node_id", "unknown"),
                domain=raw_data.get("domain", "unknown"),
                timestamp=raw_data.get("timestamp", ""),
                payload=raw_data.get("data", {}),
                protocol_source="HTTP_POST"
            )
        except Exception as e:
            print(f"[HTTP Adapter] Parse error: {e}")
            return None
