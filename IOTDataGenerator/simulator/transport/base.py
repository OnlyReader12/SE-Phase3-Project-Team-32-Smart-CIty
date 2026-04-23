"""
Abstract base class for all protocol senders.
Follows the Strategy Pattern: NodeSimulator calls sender.send()
without knowing which protocol is being used underneath.
"""
from abc import ABC, abstractmethod


class ProtocolSender(ABC):
    """
    Strategy interface for IoT transport protocols.

    Each concrete subclass handles ONE protocol (HTTP, MQTT, CoAP, WebSocket).
    All senders are shared across nodes using the same protocol — they are
    constructed once by NodeFactory and injected into the simulator instances.
    """

    #: Protocol identifier written into the IOT_Node envelope.
    protocol_name: str = "UNKNOWN"

    async def start(self):
        """
        Lifecycle hook — called once before the simulation loop begins.
        Used to open sessions, connect to brokers, etc.
        Subclasses override this as needed.
        """
        pass

    @abstractmethod
    async def send(self, iot_node: dict):
        """
        Emit the IOT_Node payload dict via this sender's protocol.

        Args:
            iot_node: A fully-formed IOT_Node envelope dict with
                      keys: node_id, node_type, domain, timestamp,
                            location, protocol_source, state,
                            health_status, payload.
        """
        ...
