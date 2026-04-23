"""
Async MQTT sender using aiomqtt.
Uses a persistent background worker task that holds a single MQTT connection
and drains an asyncio Queue.  All MQTT nodes share the same queue → one
connection to the broker regardless of how many MQTT nodes are running.

Reconnects automatically if the broker drops.
"""
import json
import asyncio
import aiomqtt
from transport.base import ProtocolSender


class MqttSender(ProtocolSender):
    """
    Publishes telemetry via MQTT topic: {topic_prefix}/{domain}
    e.g. smartcity/telemetry/energy

    Architecture:
      Multiple nodes call send() → messages enqueue
      worker() holds the persistent MQTT connection and publishes from the queue
    """

    protocol_name = "MQTT_PUB"

    def __init__(self, host: str, port: int, topic_prefix: str):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    async def start(self):
        """Launch the background MQTT worker coroutine."""
        asyncio.create_task(self._worker(), name="mqtt-worker")
        print(f"[MqttSender] Worker started → {self.host}:{self.port}")

    async def _worker(self):
        """
        Persistent worker: holds one MQTT connection, publishes messages
        from the shared queue. Retries with backoff on disconnect.
        """
        backoff = 2
        while True:
            try:
                async with aiomqtt.Client(hostname=self.host, port=self.port) as client:
                    print("[MqttSender] Connected to broker.")
                    backoff = 2  # Reset on successful connect
                    while True:
                        iot_node = await self._queue.get()
                        topic = f"{self.topic_prefix}/{iot_node['domain']}"
                        await client.publish(topic, json.dumps(iot_node))
                        self._queue.task_done()
            except aiomqtt.MqttError as e:
                print(f"[MQTT Worker] Broker error: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            except Exception as e:
                print(f"[MQTT Worker] Unexpected error: {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)

    async def send(self, iot_node: dict):
        """Enqueue the payload for the worker to publish."""
        try:
            self._queue.put_nowait(iot_node)
        except asyncio.QueueFull:
            # Drop oldest message to make room
            self._queue.get_nowait()
            self._queue.put_nowait(iot_node)
            print(f"[MQTT] Queue full — oldest message dropped for {iot_node['node_id']}")
