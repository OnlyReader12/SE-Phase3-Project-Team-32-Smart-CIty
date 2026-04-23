"""
Async WebSocket sender for actuator state feedback + command reception.
Actuator nodes (AC units, valves, lights, pumps, etc.) report their current
state to the IngestionEngine's WebSocket endpoint whenever they emit a tick.

The IngestionEngine receives these messages at ws://host:8000/ws/actuator,
parses them as IOT_Node envelopes, and forwards them through RabbitMQ to
the Persistent Middleware — completing the actuator feedback loop.

A single persistent WebSocket connection is shared by all actuator nodes
(via a queue+worker pattern identical to MqttSender). Auto-reconnects if
the server closes the connection.

Command reception (toggle flow):
  When a user toggles a node in Flutter:
    Flutter → UserService PATCH /actuators/{id}/command
           → IngestionEngine POST /api/actuator/{id}/command (queued)
           → next WS heartbeat from node triggers command delivery
           → IngestionEngine sends back: {"type":"command","node_id":"...","field":"state","value":"OFF"}
           → This sender broadcasts the command to all registered node callbacks
           → The matching NodeSimulator updates its internal state
           → Next tick sends updated state → Middleware → Engine → Flutter
"""
import json
import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
from transport.base import ProtocolSender


class WebSocketSender(ProtocolSender):
    """
    Streams actuator state feedback via WebSocket → ws://host:8000/ws/actuator

    Architecture: one persistent WS connection, one asyncio Queue.
    All actuator nodes enqueue payloads; the worker sends them.
    Command frames from the server are broadcast to registered node callbacks.
    """

    protocol_name = "WebSocket"

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=300)
        # node_id → async callable(field, value) registered by NodeSimulator
        self._command_callbacks: dict[str, callable] = {}

    def register_command_callback(self, node_id: str, callback):
        """
        Actuator NodeSimulator instances call this to receive commands.
        callback: async def on_command(field: str, value: str)
        """
        self._command_callbacks[node_id] = callback

    async def start(self):
        """Launch the background WebSocket worker coroutine."""
        asyncio.create_task(self._worker(), name="ws-actuator-worker")
        print(f"[WSSender] Worker started → {self.ws_url}")

    async def _worker(self):
        """
        Maintains the persistent WebSocket connection.
        Drains the queue and sends payloads. Reconnects on disconnect.
        Listens for command frames from IngestionEngine.
        """
        backoff = 2
        while True:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    print(f"[WSSender] Connected to {self.ws_url}")
                    backoff = 2
                    while True:
                        # Wait for next payload with a short timeout
                        # so we can also process incoming command frames
                        try:
                            iot_node = await asyncio.wait_for(
                                self._queue.get(), timeout=0.5
                            )
                            await ws.send(json.dumps(iot_node))
                            self._queue.task_done()

                            # Read server response (ACK or command frame)
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                                msg = json.loads(raw)
                                if msg.get("type") == "command":
                                    await self._dispatch_command(msg)
                            except asyncio.TimeoutError:
                                pass  # No response is fine
                            except json.JSONDecodeError:
                                pass

                        except asyncio.TimeoutError:
                            # No payload in queue — check for unsolicited server messages
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=0.1)
                                msg = json.loads(raw)
                                if msg.get("type") == "command":
                                    await self._dispatch_command(msg)
                            except (asyncio.TimeoutError, json.JSONDecodeError):
                                pass

            except ConnectionClosed as e:
                print(f"[WS Worker] Connection closed ({e.code}). Reconnecting in {backoff}s...")
            except OSError as e:
                print(f"[WS Worker] Cannot connect to {self.ws_url}: {e}. Retrying in {backoff}s...")
            except Exception as e:
                print(f"[WS Worker] Error: {e}. Retrying in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _dispatch_command(self, msg: dict):
        """Route a received command frame to the correct node's callback."""
        node_id = msg.get("node_id", "")
        field   = msg.get("field", "state")
        value   = msg.get("value", "OFF")
        cb = self._command_callbacks.get(node_id)
        if cb:
            print(f"[WSSender] Dispatching command to {node_id}: {field}={value}")
            try:
                await cb(field, value)
            except Exception as e:
                print(f"[WSSender] Command callback error for {node_id}: {e}")
        else:
            print(f"[WSSender] No callback registered for node {node_id}")

    async def send(self, iot_node: dict):
        """Enqueue the actuator payload for the worker."""
        try:
            self._queue.put_nowait(iot_node)
        except asyncio.QueueFull:
            self._queue.get_nowait()
            self._queue.put_nowait(iot_node)
