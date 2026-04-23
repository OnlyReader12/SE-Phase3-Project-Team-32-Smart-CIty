"""
MQTT adapter.
Subscribes to smartcity/telemetry/# on the embedded AMQTT broker.
Parses each message into SmartCityObject and forwards via RabbitMQForwarder.

Key fix: reads "payload" key (IOT_Node canonical field), NOT legacy "data".
"""
import json
from models.domain import SmartCityObject
from adapters.base import ProtocolAdapter
import paho.mqtt.client as mqtt


class MqttAdapter(ProtocolAdapter):
    """
    Listens to the embedded MQTT broker and processes incoming telemetry
    published by aiomqtt simulator nodes.

    Topic scheme: smartcity/telemetry/{domain}
    """

    def __init__(self, forwarder, broker_host: str = "127.0.0.1", port: int = 1883):
        super().__init__(forwarder)
        self.client = mqtt.Client(client_id="ingestion_mqtt_adapter")
        self.broker_host = broker_host
        self.port = port

    # ── Paho callbacks ────────────────────────────────────────────────

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[MQTT Adapter] Connected to embedded broker — subscribing.")
            self.client.subscribe("smartcity/telemetry/#")
        else:
            print(f"[MQTT Adapter] Connection failed, rc={rc}")

    def on_message(self, client, userdata, message):
        try:
            raw_data = json.loads(message.payload.decode("utf-8"))
            self.process_and_forward(raw_data)
        except Exception as exc:
            print(f"[MQTT Adapter] Parse error: {exc}")

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start_listening(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        try:
            self.client.connect(self.broker_host, self.port)
            self.client.loop_start()   # Background thread — non-blocking
        except Exception as exc:
            print(f"[MQTT Adapter] Failed to connect to broker: {exc}")

    # ── Normalisation ─────────────────────────────────────────────────

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
                protocol_source="MQTT_PUB",
            )
        except Exception as exc:
            print(f"[MQTT Adapter] Normalisation error: {exc}")
            return None
