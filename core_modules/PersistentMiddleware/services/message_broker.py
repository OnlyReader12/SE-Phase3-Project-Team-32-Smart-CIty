import pika
import json

class RabbitMQPublisher:
    """
    Implements full RabbitMQ Publisher code.
    This acts as the out-bound router for the entire Smart City.
    """
    def __init__(self, host='localhost'):
        self.host = host
        # Connect immediately
        try:
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(self.host))
            self.channel = self.connection.channel()
            # Ensure the master exchange exists
            self.channel.exchange_declare(exchange='smartcity_exchange', exchange_type='topic')
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
                exchange='smartcity_exchange',
                routing_key=routing_key,
                body=json.dumps(message)
            )
            return True
        except Exception as e:
            print(f"[RabbitMQ] Failed to publish message: {e}")
            return False
