"""
WebSocket adapter for actuator state feedback + command delivery.

Actuator nodes (AC units, valves, pumps, lights, etc.) connect to
ws://host:8000/ws/actuator and stream their current state after every
state change or heartbeat tick.

This adapter:
  1. Accepts the WebSocket connection
  2. Receives IOT_Node JSON frames
  3. Normalises them into SmartCityObject
  4. Forwards via RabbitMQForwarder to Persistent Middleware
  5. Checks pending_commands dict for any queued command for this node
  6. If found: sends a command frame back to the simulator node
  7. Sends a lightweight ACK so the sender can detect dropped connections

The route is mounted in IngestionEngine/main.py as:
    @app.websocket("/ws/actuator")
    async def ws_route(ws: WebSocket):
        await ws_adapter.handle(ws)

Command delivery flow:
  UserService PATCH /actuators/{id}/command
    → POST :8000/api/actuator/{id}/command   (HTTP endpoint in main.py)
    → pending_commands["AC-UNIT-001"] = {"field": "state", "value": "OFF"}
    → next WS heartbeat from "AC-UNIT-001" triggers command send
    → simulator node processes command and updates its state
    → simulator sends updated state frame on next tick
    → middleware stores new state → Engine reads it → UI reflects it
"""
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect

from models.domain import SmartCityObject

# ── Global pending commands store ─────────────────────────────────────────
# key: node_id (str)  value: {"field": str, "value": str}
# Commands are consumed (deleted) once delivered to the WS-connected node.
pending_commands: dict[str, dict] = {}


class WebSocketAdapter:
    """
    Handles a single persistent WebSocket connection from an actuator sender.
    FastAPI calls this for every new connection on /ws/actuator.
    """

    def __init__(self, forwarder):
        self.forwarder = forwarder

    async def handle(self, websocket: WebSocket):
        """Accept the connection and process incoming actuator frames."""
        await websocket.accept()
        client = websocket.client
        print(f"[WS Adapter] Actuator connected from {client.host}:{client.port}")

        try:
            while True:
                raw_text = await websocket.receive_text()
                try:
                    raw_data = json.loads(raw_text)
                    node_id  = raw_data.get("node_id", "unknown")

                    obj = SmartCityObject(
                        node_id=node_id,
                        node_type=raw_data.get("node_type", "unknown"),
                        domain=raw_data.get("domain", "unknown"),
                        timestamp=raw_data.get("timestamp", ""),
                        state=raw_data.get("state"),
                        health_status=raw_data.get("health_status", "OK"),
                        location=raw_data.get("location"),
                        payload=raw_data.get("payload", {}),
                        protocol_source="WebSocket",
                    )

                    # Publish to RabbitMQ
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.forwarder.forward, obj)

                    # ── Command delivery ─────────────────────────────────
                    # Check if a command is pending for this node.
                    # If yes, send it back as a command frame and remove from queue.
                    if node_id in pending_commands:
                        cmd = pending_commands.pop(node_id)
                        await websocket.send_text(json.dumps({
                            "type":    "command",
                            "node_id": node_id,
                            "field":   cmd.get("field", "state"),
                            "value":   cmd.get("value", "OFF"),
                        }))
                        print(f"[WS Adapter] Command delivered to {node_id}: {cmd}")
                    else:
                        # Normal ACK
                        await websocket.send_text(
                            json.dumps({"ack": "ok", "node_id": node_id})
                        )

                except (json.JSONDecodeError, KeyError) as exc:
                    print(f"[WS Adapter] Bad frame: {exc}")
                    await websocket.send_text(json.dumps({"ack": "error", "detail": str(exc)}))

        except WebSocketDisconnect:
            print(f"[WS Adapter] Actuator disconnected from {client.host}:{client.port}")
        except Exception as exc:
            print(f"[WS Adapter] Unexpected error: {exc}")
