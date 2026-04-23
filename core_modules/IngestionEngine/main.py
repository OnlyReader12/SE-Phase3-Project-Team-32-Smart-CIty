"""
IngestionEngine — main application entry point.

Listens on FOUR protocols simultaneously:
  ┌──────────────────────────────────────────────────────────────┐
  │  Protocol   │ Endpoint                       │ Adapter        │
  ├─────────────┼────────────────────────────────┼────────────────│
  │  HTTP POST  │ :8000/api/telemetry            │ HttpAdapter    │
  │  MQTT PUB   │ :1883  (embedded AMQTT broker) │ MqttAdapter    │
  │  CoAP PUT   │ :5683/telemetry  (UDP)         │ coap_adapter   │
  │  WebSocket  │ :8000/ws/actuator              │ WebSocketAdapter│
  └──────────────────────────────────────────────────────────────┘

All four adapters normalise raw data into SmartCityObject and push it
to the Persistent Middleware via RabbitMQ (exchange: smartcity_exchange,
routing key: ingestion.raw).
"""
import asyncio
import threading
import time

from fastapi import FastAPI, Request, WebSocket

from adapters.base import RabbitMQForwarder
from adapters.http_adapter import HttpAdapter
from adapters.mqtt_adapter import MqttAdapter
from adapters.coap_adapter import start_coap_server
from adapters.websocket_adapter import WebSocketAdapter, pending_commands
from broker.embedded_mqtt import start_embedded_broker_sync

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Smart City — IoT Ingestion Engine",
    description=(
        "Unified multi-protocol gateway. Accepts HTTP, MQTT, CoAP and WebSocket "
        "telemetry from IoT nodes and forwards to Persistent Middleware via RabbitMQ."
    ),
    version="2.0.0",
)

# ── Shared forwarder (RabbitMQ publisher) ─────────────────────────────────
forwarder = RabbitMQForwarder(host="127.0.0.1")

# ── Protocol adapters (all share the same forwarder) ─────────────────────
http_adapter = HttpAdapter(forwarder)
mqtt_adapter = MqttAdapter(forwarder)
ws_adapter   = WebSocketAdapter(forwarder)


# ── Startup: wire all four protocols ──────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    # 1. Start embedded MQTT broker in a dedicated thread (own event loop)
    broker_thread = threading.Thread(
        target=start_embedded_broker_sync, daemon=True, name="mqtt-broker"
    )
    broker_thread.start()
    await asyncio.sleep(1)   # Let the broker bind its port

    # 2. MQTT adapter subscribes (Paho loop_start → background thread)
    mqtt_adapter.start_listening()

    # 3. CoAP server in the SAME asyncio event loop as FastAPI/uvicorn
    asyncio.create_task(start_coap_server(forwarder))

    print("\n" + "=" * 60)
    print("  Ingestion Engine — ALL PROTOCOLS LIVE")
    print("  HTTP POST  → :8000/api/telemetry")
    print("  MQTT SUB   → :1883  smartcity/telemetry/#")
    print("  CoAP PUT   → :5683  /telemetry  (UDP)")
    print("  WebSocket  → :8000/ws/actuator")
    print("=" * 60 + "\n")


# ── HTTP route ────────────────────────────────────────────────────────────
@app.post("/api/telemetry", summary="Ingest HTTP telemetry from IoT nodes")
async def receive_http_telemetry(request: Request):
    """
    Receives a raw IOT_Node JSON payload from HTTP POST nodes.
    Normalises → SmartCityObject → RabbitMQ.
    """
    raw_payload = await request.json()
    http_adapter.process_and_forward(raw_payload)
    return {"status": "ingested", "protocol": "HTTP_POST"}


# ── WebSocket route ───────────────────────────────────────────────────────
@app.websocket("/ws/actuator")
async def websocket_actuator_feedback(websocket: WebSocket):
    """
    Persistent WebSocket endpoint for actuator state feedback.
    Actuator simulator nodes (AC, valves, lighting, pumps, etc.) stream
    their state here after every tick.
    """
    await ws_adapter.handle(websocket)


# ── Health check ──────────────────────────────────────────────────────────
@app.get("/health", summary="Ingestion Engine health check")
def health():
    return {
        "status": "ok",
        "protocols": ["HTTP_POST", "MQTT_PUB", "CoAP_PUT", "WebSocket"],
        "pending_commands": len(pending_commands),
    }


# ── Actuator command endpoint ──────────────────────────────────────────────
# Called by UserService when a Flutter toggle is issued.
# The command is queued in pending_commands[node_id].
# The WebSocket adapter delivers it on the next heartbeat tick from that node.
@app.post("/api/actuator/{node_id}/command",
          summary="Queue an actuator command for a node")
async def queue_actuator_command(node_id: str, request: Request):
    """
    Accepts a command from UserService and queues it for the target node.
    The node must be connected via WebSocket (/ws/actuator) to receive it.
    The command is delivered on the node's next heartbeat tick (≤ node tick interval).

    Body: {"field": "state", "value": "OFF"}
    """
    body = await request.json()
    pending_commands[node_id] = {
        "field": body.get("field", "state"),
        "value": body.get("value", "OFF"),
    }
    print(f"[Ingestion] Command queued for {node_id}: {pending_commands[node_id]}")
    return {
        "status":  "queued",
        "node_id": node_id,
        "command": pending_commands[node_id],
    }


@app.get("/api/actuator/{node_id}/state",
         summary="Check pending command for a node")
def get_actuator_state(node_id: str):
    """Returns any queued (undelivered) command for this node, or None."""
    return {
        "node_id":         node_id,
        "pending_command": pending_commands.get(node_id),
    }


# ── Dev runner ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
