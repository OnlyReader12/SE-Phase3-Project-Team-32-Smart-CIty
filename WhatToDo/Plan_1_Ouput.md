Continuing with the engine, factory, main, config, then Ingestion and Middleware.

Edited __init__.py
Edited generator_engine.py
Edited node_simulator.py
Edited node_factory.py
Edited __init__.py
Edited main.py

Now writing `node_schemas.json` (the master config) and requirements:

Edited node_schemas.json
Edited requirements.txt

Now the IngestionEngine — all 4 adapter files + updated domain model + main:

Edited domain.py
Edited http_adapter.py
Edited mqtt_adapter.py
Edited coap_adapter.py
Edited websocket_adapter.py
Edited main.py
Edited requirements.txt

Now the Persistent Middleware — updated DB model, AMQP consumer, and improved dashboard:

Edited models.py
Edited amqp_consumer.py
Edited routes.py
Edited main.py

Everything is written. Let me do a final verification of the file tree:

Ran command: `find IOTDataGenerator/simulator core_modules/IngestionEngine core_modules/PersistentMiddleware -type f | sort`
Ran command: `python3 -c "
import json
data = json.load(open('IOTDataGenerator/node_schemas.json'))
total = sum(t['count'] for t in data['node_types'])
by_domain = {}
by_proto  = {}
for t in data['node_types']:
    by_domain[t['domain']] = by_domain.get(t['domain'],0) + t['count']
    by_proto[t['protocol']] = by_proto.get(t['protocol'],0) + t['count']
print(f'Node types: {len(data[\"node_types\"])}')
print(f'Total nodes: {total}')
print(f'By domain:   {by_domain}')
print(f'By protocol: {by_proto}')
"
`

All files verified. Here's the complete delivery summary:

---

## ✅ What Was Built — All Three Folders

### `IOTDataGenerator/simulator/` — 12 new files
```
simulator/
├── main.py               asyncio entry point
├── node_factory.py       reads JSON → 100 NodeSimulator instances
├── engine/
│   ├── generator_engine.py   dispatches RandomWalk/Sine/StepChange from JSON spec
│   └── node_simulator.py     generic async node (no per-type subclasses)
├── generators/
│   ├── random_walk.py    bounded drift (voltage, pH, flow)
│   ├── sine_wave.py      daily cycle (solar, temperature, soil moisture)
│   └── step_change.py    probabilistic flip (ON/OFF, OPEN/CLOSED)
└── transport/
    ├── base.py           ProtocolSender ABC
    ├── http_sender.py    aiohttp POST → :8000
    ├── mqtt_sender.py    aiomqtt queue+worker → :1883
    ├── coap_sender.py    aiocoap PUT → :5683 (UDP)
    └── websocket_sender.py  websockets queue+worker → :8000/ws/actuator
```
+ `node_schemas.json` (**100 nodes**, 21 types, 4 protocols) + `requirements.txt`

### `IngestionEngine/` — 5 files updated/created
| File | Change |
|---|---|
| `models/domain.py` | Added `node_type`, `state`, `health_status`, `location` |
| `adapters/http_adapter.py` | Fixed `"data"` → `"payload"` key |
| `adapters/mqtt_adapter.py` | Fixed `"data"` → `"payload"` key |
| `adapters/coap_adapter.py` | **NEW** — aiocoap server on UDP :5683 |
| `adapters/websocket_adapter.py` | **NEW** — WS endpoint `/ws/actuator` |
| `main.py` | Async startup: boots all 4 protocols |
| `requirements.txt` | Added `aiocoap`, `websockets` |

### `PersistentMiddleware/` — 3 files updated
| File | Change |
|---|---|
| `database/models.py` | Added `node_type`, `state`, `health_status`, `location_json` |
| `services/amqp_consumer.py` | Persists all new fields |
| `api/routes.py` | 5 routes: `/health`, `/history/{id}`, `/nodes`, `/domain/{d}`, `/view` (dark theme dashboard) |

### Run order
```bash
cd core_modules/PersistentMiddleware && uvicorn main:app --port 8001
cd core_modules/IngestionEngine     && uvicorn main:app --port 8000
cd IOTDataGenerator                 && python simulator/main.py
# Dashboard → http://localhost:8001/view
```