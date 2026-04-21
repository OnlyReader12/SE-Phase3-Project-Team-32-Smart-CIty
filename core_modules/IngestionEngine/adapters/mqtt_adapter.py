import json
from models.domain import SmartCityObject
from adapters.base import ProtocolAdapter
import paho.mqtt.client as mqtt

class MqttAdapter(ProtocolAdapter):
    """
    Listens to the embedded MQTT broker, parsing incoming Paho-MQTT messages.
    """
    def __init__(self, forwarder, broker_host="127.0.0.1", port=1883):
        super().__init__(forwarder)
        self.client = mqtt.Client(client_id="ingestion_adapter")
        self.broker_host = broker_host
        self.port = port

    def on_message(self, client, userdata, message):
        try:
            raw_json = json.loads(message.payload.decode("utf-8"))
            self.process_and_forward(raw_json)
        except Exception as e:
            print(f"[MQTT Adapter] Parse error: {e}")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[MQTT Adapter] Connected to embedded broker successfully.")
            self.client.subscribe("smartcity/telemetry/#")
        else:
            print(f"Failed to connect return code {rc}")

    def start_listening(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        try:
            self.client.connect(self.broker_host, self.port)
            self.client.loop_start()  # Runs in background thread
        except Exception as e:
            print(f"[MQTT Adapter] Failed to trace broker: {e}")
            
    def standard_parse(self, raw_data: dict) -> SmartCityObject:
        return SmartCityObject(
            node_id=raw_data.get("node_id", "unknown"),
            domain=raw_data.get("domain", "unknown"),
            timestamp=raw_data.get("timestamp", ""),
            payload=raw_data.get("data", {}),
            protocol_source="MQTT_PUB"
        )
