"""
Async CoAP sender using aiocoap.
Sends IOT_Node payloads as CoAP PUT requests with Content-Format 50
(application/json, IANA registered).

CoAP (Constrained Application Protocol, RFC 7252) runs over UDP and is
designed for resource-constrained IoT devices.  Nodes that use this protocol
simulate low-power sensors such as temperature/humidity, soil moisture,
occupancy counters, and water quality monitors.

A single aiocoap client Context is shared (created once in start()) and
reused for all subsequent CoAP requests.
"""
import json
import asyncio
import aiocoap
from transport.base import ProtocolSender

# IANA Content-Format code for application/json
_COAP_JSON_FORMAT = 50


class CoAPSender(ProtocolSender):
    """
    Sends telemetry via CoAP PUT → coap://host:5683/telemetry

    The CoAP server in IngestionEngine/adapters/coap_adapter.py listens
    on UDP port 5683 for these PUT requests.
    """

    protocol_name = "CoAP_PUT"

    def __init__(self, coap_uri: str):
        self.uri = coap_uri
        self._context: aiocoap.Context = None

    async def start(self):
        """Create the shared CoAP client context."""
        self._context = await aiocoap.Context.create_client_context()
        print(f"[CoAPSender] Client context ready → {self.uri}")

    async def send(self, iot_node: dict):
        """Send one CoAP PUT request carrying the IOT_Node JSON payload."""
        if self._context is None:
            await self.start()
        try:
            body = json.dumps(iot_node).encode("utf-8")
            request = aiocoap.Message(
                code=aiocoap.PUT,
                uri=self.uri,
                payload=body,
            )
            request.opt.content_format = _COAP_JSON_FORMAT
            response = await asyncio.wait_for(
                self._context.request(request).response,
                timeout=5.0,
            )
            if not response.code.is_successful():
                print(f"[CoAP] {iot_node['node_id']} → server error: {response.code}")
        except asyncio.TimeoutError:
            print(f"[CoAP] {iot_node['node_id']} → request timed out")
        except Exception as e:
            print(f"[CoAP] {iot_node['node_id']} → {type(e).__name__}: {e}")
