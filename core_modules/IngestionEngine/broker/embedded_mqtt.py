import asyncio
from amqtt.broker import Broker

async def run_broker():
    """
    Spawns a pure Python embedded MQTT broker so external heavy software 
    is not required. Satisfies the user constraint.
    """
    config = {
        'listeners': {
            'default': {
                'type': 'tcp',
                'bind': '0.0.0.0:1883',
            }
        },
        'sys_interval': 10,
        'auth': {
            'allow-anonymous': True,
        }
    }
    broker = Broker(config)
    await broker.start()
    print("[Embedded Broker] AMQTT Server live on port 1883...")

def start_embedded_broker_sync():
    """Wrapper to run the broker in a dedicated thread/loop avoiding FastAPI conflicts."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_broker())
    loop.run_forever()
