"""
NodeFactory — reads node_schemas.json and assembles all NodeSimulator instances.

Design principle: Zero Python changes needed to add a new node type.
  → Add an entry to node_schemas.json["node_types"]
  → Set count, domain, protocol, payload_schema fields
  → Restart the simulator

The factory:
  1. Parses the JSON config
  2. Creates one shared ProtocolSender per protocol (HTTP, MQTT, CoAP, WS)
  3. For each node_type entry × count, instantiates one NodeSimulator
     with round-robin zone assignment and per-field generator objects
"""
import json
from engine.generator_engine import build_generator
from engine.node_simulator import NodeSimulator
from transport.http_sender import HttpSender
from transport.mqtt_sender import MqttSender
from transport.coap_sender import CoAPSender
from transport.websocket_sender import WebSocketSender


class NodeFactory:
    """
    Schema-driven factory for building all simulation nodes.

    Args:
        schema_path: Absolute or CWD-relative path to node_schemas.json
    """

    def __init__(self, schema_path: str):
        with open(schema_path, encoding="utf-8") as fh:
            self.config = json.load(fh)
        self._validate_config()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_config(self):
        required_top = {"simulation", "ingestion_endpoints", "campus_zones", "node_types"}
        missing = required_top - set(self.config.keys())
        if missing:
            raise ValueError(f"[NodeFactory] node_schemas.json missing top-level keys: {missing}")

        total = sum(t["count"] for t in self.config["node_types"])
        print(f"[NodeFactory] Config loaded: {len(self.config['node_types'])} node types, "
              f"{total} total nodes, {len(self.config['campus_zones'])} campus zones.")

    # ------------------------------------------------------------------
    # Sender pool — one instance per protocol
    # ------------------------------------------------------------------

    def _build_senders(self) -> dict:
        ep = self.config["ingestion_endpoints"]
        return {
            "HTTP":      HttpSender(ep["http"]),
            "MQTT":      MqttSender(
                            ep["mqtt_host"],
                            ep["mqtt_port"],
                            ep["mqtt_topic_prefix"],
                         ),
            "CoAP":      CoAPSender(ep["coap_uri"]),
            "WebSocket": WebSocketSender(ep["ws_url"]),
        }

    # ------------------------------------------------------------------
    # Main build
    # ------------------------------------------------------------------

    def build_all(self) -> tuple:
        """
        Build and return (nodes_list, senders_dict).

        Callers must call `await sender.start()` for each sender
        before running the node coroutines.
        """
        senders = self._build_senders()
        zones = self.config["campus_zones"]
        sim_cfg = self.config["simulation"]
        interval = float(sim_cfg["default_interval_s"])
        jitter   = float(sim_cfg["interval_jitter_s"])

        nodes: list[NodeSimulator] = []
        zone_cursor = 0

        for type_spec in self.config["node_types"]:
            protocol = type_spec["protocol"]
            if protocol not in senders:
                raise ValueError(
                    f"[NodeFactory] Unknown protocol '{protocol}' in node type "
                    f"'{type_spec['node_type']}'. Supported: {list(senders.keys())}"
                )
            sender = senders[protocol]

            for _ in range(type_spec["count"]):
                zone = zones[zone_cursor % len(zones)]
                zone_cursor += 1

                node_index = len(nodes) + 1
                raw_type   = type_spec["node_type"].upper().replace("_", "-")
                node_id    = f"{raw_type}-{node_index:03d}"

                # Build one generator per payload field from the JSON spec
                generators = {
                    field: build_generator(spec)
                    for field, spec in type_spec["payload_schema"].items()
                }

                nodes.append(NodeSimulator(
                    node_id=node_id,
                    node_type=type_spec["node_type"],
                    domain=type_spec["domain"],
                    location=zone,
                    protocol_sender=sender,
                    payload_generators=generators,
                    is_actuator=type_spec["is_actuator"],
                    interval=interval,
                    jitter=jitter,
                ))

        # Print summary table
        self._print_summary(nodes)
        return nodes, senders

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @staticmethod
    def _print_summary(nodes: list):
        from collections import Counter
        by_domain   = Counter(n.domain for n in nodes)
        by_protocol = Counter(n.sender.protocol_name for n in nodes)
        actuators   = sum(1 for n in nodes if n.is_actuator)

        print("\n" + "─" * 50)
        print(f"  Total nodes  : {len(nodes)}")
        print(f"  Actuators    : {actuators}  |  Sensors: {len(nodes) - actuators}")
        print(f"  By domain    : {dict(by_domain)}")
        print(f"  By protocol  : {dict(by_protocol)}")
        print("─" * 50 + "\n")
