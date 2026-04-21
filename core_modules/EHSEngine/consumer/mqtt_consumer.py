"""
consumer/mqtt_consumer.py -- MQTT Subscriber for direct IoT Generator integration.

PROTOCOL: MQTT (Message Queuing Telemetry Transport)
-----------------------------------------------------
While AMQP/RabbitMQ handles inter-SERVICE communication, MQTT handles
direct IoT DEVICE communication. Battery-powered sensors on campus use
MQTT because it's ultra-lightweight (~2 bytes overhead vs HTTP's ~700).

The IoT Generator (IOTDataGenerator/iot_generator.py) publishes EHS
telemetry to:
    Topic: smartcity/telemetry/ehs
    Broker: localhost:1883 (Mosquitto)

This consumer subscribes to that topic and feeds each message into the
same EHSEngineEvaluator pipeline -- reusing the exact same Strategy,
Factory, and persistence logic. Zero code duplication.

DESIGN PATTERN: Adapter
    This class ADAPTS the MQTT protocol into our internal EHSTelemetry
    schema.  The evaluator doesn't know or care whether data came via
    MQTT, AMQP, or HTTP POST. That's the power of the Adapter pattern.
"""

import json
import threading
from typing import Optional

import paho.mqtt.client as mqtt

from evaluator.engine_evaluator import EHSEngineEvaluator
from models.schemas import EHSTelemetry


class MQTTConsumer:
    """
    MQTT subscriber that listens on 'smartcity/telemetry/ehs' and
    dispatches each message to the EHSEngineEvaluator.

    Runs in a background daemon thread -- never blocks FastAPI.
    """

    def __init__(
        self,
        evaluator: EHSEngineEvaluator,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        topic: str = "smartcity/telemetry/ehs",
        client_id: str = "ehs_engine_subscriber",
    ):
        self._evaluator   = evaluator
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._topic       = topic
        self._client_id   = client_id
        self._client: Optional[mqtt.Client] = None
        self._connected   = False
        self._thread: Optional[threading.Thread] = None

    def start_listening(self):
        """Spin up the MQTT subscriber in a daemon background thread."""
        self._thread = threading.Thread(
            target=self._connect_and_loop,
            name="EHS-MQTT-Consumer",
            daemon=True,
        )
        self._thread.start()
        print(f"[MQTTConsumer] Starting MQTT subscriber for '{self._topic}'")

    def _connect_and_loop(self):
        """Connect to Mosquitto broker and block on the network loop."""
        try:
            self._client = mqtt.Client(client_id=self._client_id)

            # Assign callbacks
            self._client.on_connect    = self._on_connect
            self._client.on_message    = self._on_message
            self._client.on_disconnect = self._on_disconnect

            print(f"[MQTTConsumer] Connecting to Mosquitto at "
                  f"{self._broker_host}:{self._broker_port}...")

            self._client.connect(self._broker_host, self._broker_port, keepalive=60)

            # Blocking loop -- runs forever, reconnects automatically
            self._client.loop_forever()

        except ConnectionRefusedError:
            print(f"[MQTTConsumer] Mosquitto broker not running at "
                  f"{self._broker_host}:{self._broker_port}")
            print("[MQTTConsumer] Running in offline mode. "
                  "Install Mosquitto or test via POST /evaluate")
            self._connected = False
        except Exception as e:
            print(f"[MQTTConsumer] Connection error: {e}")
            self._connected = False

    def _on_connect(self, client, userdata, flags, rc):
        """Called when MQTT connection is established."""
        if rc == 0:
            print(f"[MQTTConsumer] Connected to Mosquitto broker!")
            # Subscribe to the EHS telemetry topic
            # Also subscribe to wildcard to catch subtopics
            client.subscribe(self._topic)
            client.subscribe(f"{self._topic}/#")
            self._connected = True
            print(f"[MQTTConsumer] Subscribed to: {self._topic}")
        else:
            print(f"[MQTTConsumer] Connection failed with code: {rc}")
            self._connected = False

    def _on_message(self, client, userdata, msg):
        """
        Called for each MQTT message on smartcity/telemetry/ehs.

        Parses the IoT Generator's JSON payload into EHSTelemetry and
        feeds it into the same evaluation pipeline as AMQP messages.
        """
        try:
            raw = json.loads(msg.payload.decode("utf-8"))

            # The IoT Generator produces the EXACT same schema:
            # {"node_id": "...", "domain": "ehs", "timestamp": "...",
            #  "data": {"aqi": N, "water_ph": N, "is_critical": bool}}
            telemetry = EHSTelemetry(
                node_id=raw.get("node_id", "UNKNOWN"),
                domain=raw.get("domain", "ehs"),
                timestamp=raw.get("timestamp", ""),
                data=raw.get("data", {}),
            )

            print(f"[MQTTConsumer] Received from {msg.topic}: "
                  f"node={telemetry.node_id} AQI={telemetry.data.aqi} "
                  f"pH={telemetry.data.water_ph}")

            # Reuse the SAME evaluation pipeline (Strategy + Factory + Persist + Alert)
            self._evaluator.evaluate(telemetry)

        except Exception as e:
            print(f"[MQTTConsumer] ERROR processing MQTT message: {e}")

    def _on_disconnect(self, client, userdata, rc):
        """Handle unexpected disconnections."""
        self._connected = False
        if rc != 0:
            print(f"[MQTTConsumer] Unexpected disconnect (rc={rc}). "
                  f"Paho will auto-reconnect...")

    def stop(self):
        """Gracefully disconnect from the broker."""
        if self._client:
            self._client.disconnect()
            print("[MQTTConsumer] Disconnected from Mosquitto.")
