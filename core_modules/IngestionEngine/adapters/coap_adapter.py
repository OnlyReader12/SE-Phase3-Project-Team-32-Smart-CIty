"""
CoAP server-side adapter for the Ingestion Engine.

Starts an aiocoap UDP server on port 5683.
Accepts PUT requests from CoAPSender simulator nodes at /telemetry.
Normalises the JSON body into SmartCityObject and forwards via
RabbitMQForwarder.

CoAP content-format 50 = application/json (IANA registered).
"""
import json
import asyncio
import aiocoap
import aiocoap.resource as resource

from models.domain import SmartCityObject


class TelemetryResource(resource.Resource):
    """
    aiocoap Resource mounted at coap://host:5683/telemetry.
    Handles CoAP PUT requests from IoT simulator CoAP nodes.
    """

    def __init__(self, forwarder):
        super().__init__()
        self.forwarder = forwarder

    async def render_put(self, request: aiocoap.Message) -> aiocoap.Message:
        """Parse the PUT body and forward to RabbitMQ."""
        try:
            raw_data = json.loads(request.payload.decode("utf-8"))

            obj = SmartCityObject(
                node_id=raw_data.get("node_id", "unknown"),
                node_type=raw_data.get("node_type", "unknown"),
                domain=raw_data.get("domain", "unknown"),
                timestamp=raw_data.get("timestamp", ""),
                state=raw_data.get("state"),
                health_status=raw_data.get("health_status", "OK"),
                location=raw_data.get("location"),
                payload=raw_data.get("payload", {}),
                protocol_source="CoAP_PUT",
            )

            # forwarder.forward() is a fast local pika publish — acceptable here
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.forwarder.forward, obj)

            return aiocoap.Message(code=aiocoap.CHANGED)

        except json.JSONDecodeError as exc:
            print(f"[CoAP Adapter] JSON decode error: {exc}")
            return aiocoap.Message(code=aiocoap.BAD_REQUEST)
        except Exception as exc:
            print(f"[CoAP Adapter] Processing error: {exc}")
            return aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR)


# Kept alive by holding a module-level reference
_coap_server_context = None


async def start_coap_server(forwarder):
    """
    Create and bind the aiocoap server context.
    Called once from IngestionEngine startup inside the FastAPI event loop.
    The returned context is kept alive by the module-level reference.
    """
    global _coap_server_context

    root = resource.Site()
    root.add_resource(["telemetry"], TelemetryResource(forwarder))

    _coap_server_context = await aiocoap.Context.create_server_context(
        root, bind=("0.0.0.0", 5683)
    )
    print("[CoAP Adapter] Server listening on UDP :5683 at /telemetry")
