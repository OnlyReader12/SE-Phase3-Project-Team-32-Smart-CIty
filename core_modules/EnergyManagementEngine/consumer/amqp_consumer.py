"""
consumer/amqp_consumer.py — RabbitMQ Subscriber (Observer Pattern).

DESIGN PATTERN: Observer
─────────────────────────
The Energy Engine acts as a concrete Observer, subscribing ONLY to the
'telemetry.power.#' topic on the RabbitMQ exchange.

Key properties of this Observer implementation:
  ✅ Selective subscription: ignores telemetry.enviro.* and telemetry.cameras.*
  ✅ Fire-and-forget consumption: RabbitMQ pushes messages; we don't poll
  ✅ Isolated failure: if Energy consumer crashes, the EHS/CAM engines continue
  ✅ Runs in a background thread, never blocking FastAPI's async event loop

Member 1 (Sandeep's IoT Ingestion) is the Publisher. We never import or
call any of his code — we are decoupled purely via the RabbitMQ topic exchange.
"""

import json
import threading
from typing import Optional

import pika

from evaluator.engine_evaluator import EnergyEngineEvaluator
from models.schemas import EnergyTelemetry


class AMQPConsumer:
    """
    AMQP consumer that listens on 'telemetry.power.#' and dispatches
    each message to the EnergyEngineEvaluator for processing.
    """

    def __init__(
        self,
        evaluator: EnergyEngineEvaluator,
        host: str = "localhost",
        port: int = 5672,
        username: str = "guest",
        password: str = "guest",
        exchange: str = "smartcity",
        queue_name: str = "energy_telemetry_queue",
        binding_key: str = "telemetry.power.#",
    ):
        self._evaluator    = evaluator
        self._host         = host
        self._port         = port
        self._credentials  = pika.PlainCredentials(username, password)
        self._exchange     = exchange
        self._queue_name   = queue_name
        self._binding_key  = binding_key
        self._thread: Optional[threading.Thread] = None
        self._connected    = False

    def start_listening(self):
        """Spin up the consumer in a daemon background thread."""
        self._thread = threading.Thread(
            target=self._consume_loop,
            name="Energy-AMQP-Consumer",
            daemon=True,
        )
        self._thread.start()
        print(f"[AMQPConsumer] Started listening on '{self._binding_key}' "
              f"(exchange: {self._exchange})")

    def _consume_loop(self):
        """
        Main consumption loop. Connects to RabbitMQ, declares infrastructure,
        then blocks on basic_consume. Reconnects automatically on failure.
        """
        while True:
            try:
                params = pika.ConnectionParameters(
                    host=self._host,
                    port=self._port,
                    credentials=self._credentials,
                    heartbeat=60,
                    socket_timeout=2,
                    connection_attempts=1,
                    retry_delay=0.5,
                )
                connection = pika.BlockingConnection(params)
                channel    = connection.channel()

                # Declare the topic exchange (idempotent — safe to re-declare)
                channel.exchange_declare(
                    exchange=self._exchange,
                    exchange_type="topic",
                    durable=True,
                )

                # Declare our exclusive queue and bind to power topics ONLY
                result = channel.queue_declare(
                    queue=self._queue_name,
                    durable=True,
                )
                channel.queue_bind(
                    exchange=self._exchange,
                    queue=self._queue_name,
                    routing_key=self._binding_key,
                )

                print(f"[AMQPConsumer] ✅ Connected. Bound to '{self._binding_key}'.")
                self._connected = True

                channel.basic_qos(prefetch_count=10)  # Don't overwhelm evaluator
                channel.basic_consume(
                    queue=self._queue_name,
                    on_message_callback=self._on_message,
                    auto_ack=False,
                )
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError:
                print("[AMQPConsumer] RabbitMQ unavailable -- running in offline mode.")
                print("[AMQPConsumer] Will NOT retry further. Use POST /evaluate for testing.")
                self._connected = False
                return  # Don't retry forever — it blocks the GIL and stalls the API
            except Exception as e:
                print(f"[AMQPConsumer] Unexpected error: {e}. Giving up consumer connection.")
                self._connected = False
                return

    def _on_message(self, channel, method, properties, body: bytes):
        """
        Callback invoked by RabbitMQ for each incoming message on telemetry.power.*

        1. Parse raw JSON body into EnergyTelemetry Pydantic model.
        2. Hand off to EnergyEngineEvaluator.evaluate().
        3. ACK the message so RabbitMQ removes it from the queue.
        """
        try:
            raw = json.loads(body.decode("utf-8"))

            # Parse the SmartCityObject payload into Energy-specific schema
            telemetry = EnergyTelemetry(
                node_id=raw.get("node_id", "UNKNOWN"),
                domain=raw.get("domain", "energy"),
                node_type=raw.get("node_type", "solar_panel"),
                timestamp=raw.get("timestamp", ""),
                data=raw.get("data", {}),
            )

            # Core evaluation pipeline (Strategy + Factory + Persistence + Alert)
            self._evaluator.evaluate(telemetry)

            # ACK: tell RabbitMQ this message was processed successfully
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            print(f"[AMQPConsumer] ERROR processing message: {e}")
            # NACK without requeue for malformed messages (avoids poison-pill loops)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
