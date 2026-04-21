from abc import ABC, abstractmethod
from typing import Dict, Any
from models.domain import SmartCityObject
import requests

class ForwarderStrategy(ABC):
    @abstractmethod
    def forward(self, standard_obj: SmartCityObject) -> bool:
        pass

class MiddlewareForwarder(ForwarderStrategy):
    """
    Forwards the cleanly converted object to the Persistent Middleware.
    This fulfills the Single Responsibility Principle.
    """
    def __init__(self, target_url="http://localhost:8001/middleware/ingest"):
        self.target_url = target_url

    def forward(self, standard_obj: SmartCityObject) -> bool:
        try:
            requests.post(self.target_url, json=standard_obj.dict(), timeout=2)
            return True
        except Exception as e:
            print(f"[Ingestion] Failed to reach Middleware: {e}")
            return False

class ProtocolAdapter(ABC):
    """
    Open/Closed Principle Core:
    Any new protocol added to the Smart City must inherit from this and implement standard_parse.
    """
    def __init__(self, forwarder: ForwarderStrategy):
        self.forwarder = forwarder

    @abstractmethod
    def standard_parse(self, raw_data: Any) -> SmartCityObject:
        pass

    def process_and_forward(self, raw_data: Any):
        standard_obj = self.standard_parse(raw_data)
        if standard_obj:
            self.forwarder.forward(standard_obj)
