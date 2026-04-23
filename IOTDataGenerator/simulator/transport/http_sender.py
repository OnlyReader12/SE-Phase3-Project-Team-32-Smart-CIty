"""
Async HTTP sender using aiohttp.
Sends IOT_Node payloads as JSON POST to the Ingestion Engine HTTP endpoint.
A single shared ClientSession is reused across all HTTP nodes for efficiency.
"""
import json
import aiohttp
from transport.base import ProtocolSender


class HttpSender(ProtocolSender):
    """
    Sends telemetry via HTTP POST → IngestionEngine :8000/api/telemetry
    Uses aiohttp for non-blocking async requests.
    """

    protocol_name = "HTTP_POST"

    def __init__(self, url: str):
        self.url = url
        self._session: aiohttp.ClientSession = None

    async def start(self):
        """Open the shared aiohttp session."""
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50),
            timeout=aiohttp.ClientTimeout(total=3),
        )
        print(f"[HttpSender] Session ready → {self.url}")

    async def send(self, iot_node: dict):
        """POST the IOT_Node JSON to the ingestion endpoint."""
        if self._session is None or self._session.closed:
            await self.start()
        try:
            async with self._session.post(self.url, json=iot_node) as resp:
                # Fire-and-forget: we don't process the response body
                pass
        except aiohttp.ClientConnectorError:
            print(f"[HTTP] {iot_node['node_id']} — Ingestion unreachable, dropping packet.")
        except Exception as e:
            print(f"[HTTP] {iot_node['node_id']} → {type(e).__name__}: {e}")
