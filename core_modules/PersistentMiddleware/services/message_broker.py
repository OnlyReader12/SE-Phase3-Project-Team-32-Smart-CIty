import pika
import json
import os

class RabbitMQPublisher:
    """
    Implements full RabbitMQ Publisher code.
    This acts as the out-bound router for the entire Smart City.
    """
    def __init__(self, host=None):
        self.host = host or os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.username = os.getenv("RABBITMQ_USERNAME", "guest")
        self.password = os.getenv("RABBITMQ_PASSWORD", "guest")
        self.exchange = os.getenv("RABBITMQ_EXCHANGE", "smartcity_exchange")
        # Connect immediately
        try:
            credentials = pika.PlainCredentials(self.username, self.password)
            params = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
            )
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            # Ensure the master exchange exists
            self.channel.exchange_declare(exchange=self.exchange, exchange_type='topic', durable=True)
            print("[RabbitMQ Publisher] Connected securely to Message Broker.")
        except pika.exceptions.AMQPConnectionError:
            print("[RabbitMQ Publisher] WARNING: RabbitMQ is offline. Messages will queue in SQLite.")
            self.connection = None

    def publish_telemetry(self, domain_type: str, message: dict):
        if not self.connection or self.connection.is_closed:
            return False
            
        routing_key = f"telemetry.{domain_type}"
        try:
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(message)
            )
            return True
        except Exception as e:
            print(f"[RabbitMQ] Failed to publish message: {e}")
            return False
