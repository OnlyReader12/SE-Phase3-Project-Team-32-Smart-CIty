import pika
import json
import threading
from database.db_core import SessionLocal
from database.models import TelemetryRecord
from services.message_broker import RabbitMQPublisher

class IngestionAMQPConsumer:
    """
    Listens to the 'ingestion.raw' queue from the Ingestion Engine.
    Persists data and forwards it to Domain Engines.
    """
    def __init__(self, host='localhost'):
        self.host = host
        self.publisher = RabbitMQPublisher(host=self.host)
        
    def start(self):
        try:
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(self.host))
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange='smartcity_exchange', exchange_type='topic')
            
            # Declare a specific queue for raw ingestion and bind it
            result = self.channel.queue_declare(queue='ingestion_raw_queue', durable=True)
            queue_name = result.method.queue
            self.channel.queue_bind(exchange='smartcity_exchange', queue=queue_name, routing_key='ingestion.raw')
            
            self.channel.basic_consume(queue=queue_name, on_message_callback=self.on_message, auto_ack=True)
            print("[Persistent Middleware] AMQP Consumer listening to 'ingestion.raw' loop...")
            self.channel.start_consuming()
        except Exception as e:
            print(f"[Persistent Middleware] AMQP Consumer failed to start: {e}")

    def on_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body)
            print(f"[Persistent Middleware] Received Payload from Ingestion: {json.dumps(payload)}")
            # 1. Guarantee Persistence
            db = SessionLocal()
            try:
                record = TelemetryRecord(
                    node_id=payload.get("node_id"),
                    domain=payload.get("domain"),
                    protocol_source=payload.get("protocol_source"),
                    timestamp=payload.get("timestamp"),
                    payload_json=json.dumps(payload.get("payload", {}))
                )
                db.add(record)
                db.commit()
            except Exception as e:
                print(f"[Persistent Middleware] DB Insert Error: {e}")
            finally:
                db.close()
                
            # 2. Forward to appropriate domain
            self.publisher.publish_telemetry(payload.get("domain"), payload)

        except Exception as e:
            print(f"[Persistent Middleware] Parse Error: {e}")

def start_amqp_consumer(host='localhost'):
    consumer = IngestionAMQPConsumer(host)
    consumer.start()
