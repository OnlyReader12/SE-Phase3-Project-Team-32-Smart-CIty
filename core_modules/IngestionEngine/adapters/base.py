from abc import ABC, abstractmethod
from typing import Dict, Any
from models.domain import SmartCityObject
import json
import pika

class ForwarderStrategy(ABC):
    @abstractmethod
    def forward(self, standard_obj: SmartCityObject) -> bool:
        pass

class RabbitMQForwarder(ForwarderStrategy):
    """
    Forwards the cleanly converted object to the Persistent Middleware via RabbitMQ.
    Uses Asynchronous Eventual Persistence.
    """
    def __init__(self, host="localhost"):
        self.host = host
        try:
            # We establish connection inside or keep a permanent connection.
            # For simplicity, keeping a persistent connection in init.
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(self.host))
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange='smartcity_exchange', exchange_type='topic')
            print("[Ingestion Engine] RabbitMQForwarder connected to broker.")
        except Exception as e:
            print(f"[Ingestion Engine] Failed to connect to RabbitMQ broker: {e}")
            self.connection = None

    def forward(self, standard_obj: SmartCityObject) -> bool:
        if not self.connection or self.connection.is_closed:
            print("[Ingestion Engine] Dropping message, RMQ connection down.")
            return False
            
        try:
            payload_json = json.dumps(standard_obj.dict())
            print(f"[Ingestion Engine] Forwarding Payload: {payload_json}")
            self.channel.basic_publish(
                exchange='smartcity_exchange',
                routing_key='ingestion.raw',
                body=payload_json
            )
            return True
        except Exception as e:
            print(f"[Ingestion] Failed to reach Middleware via RMQ: {e}")
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
