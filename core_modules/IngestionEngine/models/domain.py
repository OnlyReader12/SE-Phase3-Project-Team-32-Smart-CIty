from pydantic import BaseModel
from typing import Dict, Any

class SmartCityObject(BaseModel):
    """
    The unified, canonical data structure for the entire backend.
    Regardless of whether it came from ZigBee, CoAP, HTTP, or MQTT,
    it must be translated into this object before moving forward.
    """
    node_id: str
    domain: str
    timestamp: str
    payload: Dict[str, Any]
    protocol_source: str
