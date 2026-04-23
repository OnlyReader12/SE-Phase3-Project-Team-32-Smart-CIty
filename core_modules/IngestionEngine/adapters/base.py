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
    Automatically attempts to reconnect if the connection is lost.
    """
    def __init__(self, host="127.0.0.1"):
        self.host = host
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        """Establish connection and declare exchange."""
        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(self.host, connection_attempts=3, retry_delay=2)
            )
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange='smartcity_exchange', exchange_type='topic')
            print(f"[Ingestion Engine] Connected to RabbitMQ at {self.host}")
        except Exception as e:
            print(f"[Ingestion Engine] Connection to RabbitMQ failed: {e}")
            self.connection = None

    def forward(self, standard_obj: SmartCityObject) -> bool:
        # Check if we need to reconnect
        if not self.connection or self.connection.is_closed:
            print("[Ingestion Engine] RMQ connection down. Attempting to reconnect...")
            self._connect()
            
        if not self.connection or self.connection.is_closed:
            print("[Ingestion Engine] Dropping message, RMQ still unreachable.")
            return False
            
        try:
            payload_json = json.dumps(standard_obj.dict())
            self.channel.basic_publish(
                exchange='smartcity_exchange',
                routing_key='ingestion.raw',
                body=payload_json
            )
            return True
        except Exception as e:
            print(f"[Ingestion] Failed to forward via RMQ: {e}")
            self.connection = None # Reset for next attempt
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
