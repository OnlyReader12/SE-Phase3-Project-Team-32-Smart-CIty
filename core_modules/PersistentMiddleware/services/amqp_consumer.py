"""
AMQP Consumer for the Persistent Middleware.

Listens to the 'ingestion_raw_queue' bound to the smartcity_exchange
on routing key 'ingestion.raw'.  For every message:

  1. Persists the full SmartCityObject into SQLite (TelemetryRecord)
  2. Republishes to the domain-specific topic queue so Domain Engines
     (EHSEngine, EnergyManagementEngine) can consume it

Updated to persist all new SmartCityObject fields:
  node_type, state, health_status, location
"""
import json
import pika
from database.db_core import SessionLocal
from database.models import TelemetryRecord
from services.message_broker import RabbitMQPublisher


class IngestionAMQPConsumer:
    """
    Blocking RabbitMQ consumer that persists inbound SmartCityObjects
    and routes them onward to Domain Engine queues.
    """

    def __init__(self, host: str = "localhost"):
        self.host = host
        self.publisher = RabbitMQPublisher(host=self.host)

    def start(self):
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(self.host)
            )
            channel = connection.channel()

            channel.exchange_declare(
                exchange="smartcity_exchange", exchange_type="topic"
            )

            result = channel.queue_declare(
                queue="ingestion_raw_queue", durable=True
            )
            channel.queue_bind(
                exchange="smartcity_exchange",
                queue="ingestion_raw_queue",
                routing_key="ingestion.raw",
            )

            channel.basic_consume(
                queue="ingestion_raw_queue",
                on_message_callback=self._on_message,
                auto_ack=True,
            )
            print("[Middleware] AMQP Consumer ready — listening on 'ingestion.raw' …")
            channel.start_consuming()

        except Exception as exc:
            print(f"[Middleware] AMQP Consumer failed to start: {exc}")

    # ── Message handler ───────────────────────────────────────────────

    def _on_message(self, ch, method, properties, body: bytes):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            print(f"[Middleware] Bad JSON in AMQP message: {exc}")
            return

        node_id   = payload.get("node_id", "unknown")
        domain    = payload.get("domain",  "unknown")
        print(f"[Middleware] ← {node_id} ({domain}) via {payload.get('protocol_source')}")

        # 1. Persist to SQLite
        self._persist(payload)

        # 2. Route to domain-specific exchange topic
        self.publisher.publish_telemetry(domain, payload)

    def _persist(self, payload: dict):
        """Insert one TelemetryRecord into the local SQLite database."""
        db = SessionLocal()
        try:
            location = payload.get("location")
            record = TelemetryRecord(
                node_id=payload.get("node_id", "unknown"),
                node_type=payload.get("node_type", "unknown"),
                domain=payload.get("domain", "unknown"),
                protocol_source=payload.get("protocol_source", "unknown"),
                timestamp=payload.get("timestamp", ""),
                state=payload.get("state"),
                health_status=payload.get("health_status", "OK"),
                location_json=json.dumps(location) if location else None,
                payload_json=json.dumps(payload.get("payload", {})),
            )
            db.add(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"[Middleware] DB insert error: {exc}")
        finally:
            db.close()


def start_amqp_consumer(host: str = "localhost"):
    """Thread target: creates and starts the AMQP consumer (blocking)."""
    consumer = IngestionAMQPConsumer(host)
    consumer.start()
