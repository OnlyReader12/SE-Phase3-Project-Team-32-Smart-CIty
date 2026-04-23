import threading
import time
from fastapi import FastAPI, Request
from broker.embedded_mqtt import start_embedded_broker_sync
from adapters.base import RabbitMQForwarder
from adapters.http_adapter import HttpAdapter
from adapters.mqtt_adapter import MqttAdapter

app = FastAPI(title="IoT Ingestion Engine")

# Wire dependencies (Dependency Injection)
forwarder = RabbitMQForwarder(host="localhost")
http_adapter = HttpAdapter(forwarder)
mqtt_adapter = MqttAdapter(forwarder)

@app.on_event("startup")
def startup_event():
    # 1. Start the embedded MQTT Broker in a background thread
    broker_thread = threading.Thread(target=start_embedded_broker_sync, daemon=True)
    broker_thread.start()
    
    # Give the broker 1 second to bind its port
    time.sleep(1)
    
    # 2. Start the MQTT Adapter to listen to our new broker
    mqtt_adapter.start_listening()
    print("[Ingestion Engine] Fully Operational. Listening on HTTP:8000 and MQTT:1883")

@app.post("/api/telemetry")
async def receive_http_telemetry(request: Request):
    """Catches HTTP incoming raw data from the external IoT Generator"""
    raw_payload = await request.json()
    # Adapter handles parsing and forwarding asynchronously
    http_adapter.process_and_forward(raw_payload)
    return {"status": "ingested"}

if __name__ == "__main__":
    import uvicorn
    # Serves the HTTP API on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
