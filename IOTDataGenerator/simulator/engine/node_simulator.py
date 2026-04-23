"""
Generic async IoT node simulator.

One class handles ALL 21 node types — no per-type subclasses needed.
All behaviour is driven by generator instances built from node_schemas.json.

The simulation loop:
    1. Call generate_payload()   → ask each field generator for its next value
    2. Call build_iot_node()     → wrap in canonical IOT_Node envelope
    3. await sender.send()       → dispatch via HTTP / MQTT / CoAP / WebSocket
    4. asyncio.sleep(interval)   → wait with jitter before next tick
"""
import asyncio
import random
import time as _time
from datetime import datetime, timezone
from typing import Any, Dict


class NodeSimulator:
    """
    A self-contained async coroutine that simulates one physical IoT node.

    Args:
        node_id:            Unique identifier string  e.g. "SOLAR-PANEL-001"
        node_type:          Schema type key           e.g. "solar_panel"
        domain:             "energy" | "water" | "air"
        location:           Dict with lat, lon, zone_id, name
        protocol_sender:    A ProtocolSender instance (HTTP/MQTT/CoAP/WS)
        payload_generators: { field_name: GeneratorInstance }
        is_actuator:        True if this node receives commands (sends feedback)
        interval:           Base emit interval in seconds
        jitter:             Maximum random deviation applied to interval (±jitter)
    """

    def __init__(
        self,
        node_id: str,
        node_type: str,
        domain: str,
        location: dict,
        protocol_sender,
        payload_generators: Dict[str, Any],
        is_actuator: bool,
        interval: float,
        jitter: float = 1.0,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.domain = domain
        self.location = location
        self.sender = protocol_sender
        self.generators = payload_generators
        self.is_actuator = is_actuator
        self.interval = interval
        self.jitter = jitter

        # Mutable node state (updated per tick and included in envelope)
        self.state: str = "RUNNING"
        self.health_status: str = "OK"

        # Tick counter for diagnostics
        self._tick: int = 0

        # Register command callback for actuator nodes using WebSocket
        if is_actuator and hasattr(protocol_sender, "register_command_callback"):
            protocol_sender.register_command_callback(node_id, self.on_command)

    # ------------------------------------------------------------------
    # Command handler (called by WebSocketSender when command arrives)
    # ------------------------------------------------------------------

    async def on_command(self, field: str, value: str):
        """
        Apply a remote command (e.g. toggle ON/OFF) to this node's state.
        The updated state will appear in the next tick's payload.
        """
        print(f"[{self.node_id}] Command received: {field}={value}")
        if field == "state":
            self.state = value.upper()
        elif field in self.generators:
            # For generators that support override (e.g. setpoint fields)
            gen = self.generators[field]
            if hasattr(gen, "force"):
                gen.force(float(value))
        # Force health OK when a command is successfully received
        self.health_status = "OK"

    # ------------------------------------------------------------------
    # Payload generation
    # ------------------------------------------------------------------

    def generate_payload(self) -> dict:
        """
        Evaluate all field generators and return the domain payload dict.
        SineWave uses value_at(epoch); RandomWalk and StepChange use next().
        """
        epoch = _time.time()
        out: dict = {}
        for field, gen in self.generators.items():
            if hasattr(gen, "value_at"):       # SineWave
                out[field] = gen.value_at(epoch)
            else:                              # RandomWalk / StepChange
                out[field] = gen.next()
        return out

    def build_iot_node(self, payload: dict) -> dict:
        """
        Wrap the domain payload in the canonical IOT_Node envelope
        defined in NodeObject.md.
        """
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "domain": self.domain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {
                "latitude": self.location["lat"],
                "longitude": self.location["lon"],
                "zone": self.location["zone_id"],
                "name": self.location.get("name", ""),
            },
            "protocol_source": self.sender.protocol_name,
            "state": self.state,
            "health_status": self.health_status,
            "payload": payload,
        }

    # ------------------------------------------------------------------
    # Async simulation loop
    # ------------------------------------------------------------------

    async def run(self):
        """
        Infinite async loop: generate → wrap → send → sleep.
        Catches and logs all exceptions so one bad node never kills others.
        """
        while True:
            try:
                payload = self.generate_payload()
                iot_node = self.build_iot_node(payload)
                await self.sender.send(iot_node)
                self._tick += 1
            except Exception as exc:
                print(f"[{self.node_id}] Tick error: {type(exc).__name__}: {exc}")

            # Randomised sleep so 100 nodes don't fire simultaneously
            sleep_s = max(0.5, self.interval + random.uniform(-self.jitter, self.jitter))
            await asyncio.sleep(sleep_s)

    def __repr__(self) -> str:
        return (
            f"<NodeSimulator id={self.node_id} type={self.node_type} "
            f"domain={self.domain} protocol={self.sender.protocol_name}>"
        )
