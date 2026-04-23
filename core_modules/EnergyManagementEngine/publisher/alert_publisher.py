"""
publisher/alert_publisher.py — RabbitMQ Alert Publisher.

When the Energy Engine detects a CRITICAL condition (grid overload, battery
critically low, water leak), it publishes a minimal, structured warning payload
to the 'alerts.critical' exchange on RabbitMQ.

What happens next:
  → Member 4's Alerting Engine (Bharat) consumes this topic.
  → Member 4 implements the Chain of Responsibility Pattern to route the alert
    to Twilio (SMS) and/or SendGrid (Email).

What we NEVER do here:
  ❌ Call Twilio or SendGrid APIs directly.
  ❌ Store alert history (no DB writes from here).
  ❌ Know which residents to contact (that's Member 4's concern).

This strict boundary means: if Twilio crashes, ONLY Member 4's container
is affected. Our grid overload detection keeps running perfectly.
"""

import json
import pika
from typing import Optional

from models.schemas import AlertPayload, SafetyStatus


class AlertPublisher:
    """
    Publishes critical Energy alerts to the RabbitMQ 'alerts.critical' topic.
    Uses a topic exchange so future alerting engines can subscribe selectively.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5672,
        username: str = "guest",
        password: str = "guest",
        exchange: str = "smartcity",
        publish_topic: str = "alerts.critical",
    ):
        self._host         = host
        self._port         = port
        self._credentials  = pika.PlainCredentials(username, password)
        self._exchange     = exchange
        self._publish_topic = publish_topic
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self._connect()

    def _connect(self):
        """Establish connection to RabbitMQ. Graceful if broker is offline."""
        try:
            # Quick socket check to avoid pika blocking the GIL
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((self._host, self._port))
            sock.close()
            if result != 0:
                raise ConnectionError(f"RabbitMQ unreachable at {self._host}:{self._port}")

            params = pika.ConnectionParameters(
                host=self._host,
                port=self._port,
                credentials=self._credentials,
                heartbeat=60,
                blocked_connection_timeout=5,
                socket_timeout=2,
                connection_attempts=1,
                retry_delay=0.5,
            )
            self._connection = pika.BlockingConnection(params)
            self._channel    = self._connection.channel()
            self._channel.exchange_declare(
                exchange=self._exchange,
                exchange_type="topic",
                durable=True,
            )
            print(f"[AlertPublisher] Connected to RabbitMQ at {self._host}:{self._port}")
        except Exception as e:
            print(f"[AlertPublisher] WARNING: Cannot connect to RabbitMQ: {e}")
            print("[AlertPublisher] Running in dry-run mode -- alerts will be logged only.")
            self._connection = None
            self._channel = None

    def publish(
        self,
        metric: str,
        value: float,
        threshold: float,
        severity: SafetyStatus,
        node_id: str,
        timestamp: str,
        message: str,
    ) -> bool:
        """
        Publish a critical alert payload to the alerts.critical topic.

        The payload is intentionally minimal — just enough for Member 4 to
        dispatch the right notification. We never embed PII or contact lists here.
        """
        payload = AlertPayload(
            source="energy_engine",
            metric=metric,
            value=value,
            threshold=threshold,
            severity=severity,
            node_id=node_id,
            timestamp=timestamp,
            message=message,
        )

        payload_json = payload.json()

        try:
            if self._channel and self._channel.is_open:
                self._channel.basic_publish(
                    exchange=self._exchange,
                    routing_key=self._publish_topic,
                    body=payload_json.encode("utf-8"),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Persistent message — survives broker restart
                        content_type="application/json",
                    ),
                )
                print(f"[AlertPublisher] 🚨 Published CRITICAL alert: {message}")
                return True
            else:
                # Dry-run: log the alert when RabbitMQ is unavailable
                print(f"[AlertPublisher|DRY-RUN] Would publish to '{self._publish_topic}':")
                print(f"  {payload_json}")
                return True

        except Exception as e:
            print(f"[AlertPublisher] ERROR publishing alert: {e}")
            return False

    def close(self):
        """Close the RabbitMQ connection cleanly on service shutdown."""
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
                print("[AlertPublisher] Connection closed.")
        except Exception:
            pass
