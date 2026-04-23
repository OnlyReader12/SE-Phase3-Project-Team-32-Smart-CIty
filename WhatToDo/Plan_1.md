# Plan 1 (Revised) — Schema-Driven Real-Time IoT Simulation System

**Author:** Senior Backend Engineer  
**Revision:** 2 (2026-04-23) — Adds CoAP protocol, JSON-driven schema config, full Ingestion update  
**Status:** Approved for Implementation

---

## 🎯 Goal

Build a **schema-driven**, fully async IoT simulator for 100 campus nodes.  
The simulator reads a single `node_schemas.json` file and auto-generates all nodes.  
Adding a new node type = editing JSON only. No code changes. No new Python classes.

Data flows through:

```
 ┌──────────────────────────────────────────────────────────┐
 │              IOTDataGenerator / simulator                │
 │  [JSON Config] ──► NodeFactory ──► 100 NodeSimulators   │
 │       ↓ each node picks its protocol:                    │
 │  HTTP POST  │  MQTT PUBLISH  │  CoAP PUT  │  WebSocket   │
 └──────┬──────┴───────┬────────┴──────┬─────┴──────┬───────┘
        │              │               │             │
        ▼              ▼               ▼             ▼  (actuator feedback)
 ┌────────────────────────────────────────────────────────────┐
 │                   IngestionEngine  :8000                   │
 │  HTTP Adapter │ MQTT Adapter │ CoAP Adapter │ WS Adapter   │
 │              ↓ (all 4 parse to SmartCityObject)            │
 │              RabbitMQForwarder → exchange: smartcity_exchange│
 └──────────────────────────────────┬─────────────────────────┘
                                    │
                                    ▼  (routing key: ingestion.raw)
 ┌────────────────────────────────────────────────────────────┐
 │              PersistentMiddleware  :8001                   │
 │  AMQP Consumer → SQLite (TelemetryRecord)                  │
 │  → RabbitMQ publish to domain queues (energy/water/air)    │
 └────────────────────────────────────────────────────────────┘
```

---

## 🔑 Three New Requirements vs Rev 1

| # | New Requirement | Impact |
|---|---|---|
| 1 | **CoAP transport sender** (simulator side) | New `coap_sender.py` using `aiocoap` |
| 2 | **CoAP adapter** (ingestion side) | New `coap_adapter.py` + CoAP server resource in Ingestion |
| 3 | **JSON-driven schema config** | Single JSON file controls all node types, counts, payload specs |

---

## 📁 Complete File Structure

```
IOTDataGenerator/
├── NodeObject.md                   ← (unchanged, canonical reference)
├── iot_generator.py                ← (original kept, superseded)
├── requirements.txt                ← UPDATED: aiohttp, aiomqtt, aiocoap, websockets
│
├── node_schemas.json               ← 🆕 MASTER CONFIG (all node types + counts)
│
└── simulator/                      ← 🆕 NEW PACKAGE
    ├── __init__.py
    ├── main.py                     ← asyncio entry point
    ├── node_factory.py             ← reads JSON → instantiates NodeSimulators
    ├── campus_map.py               ← 10 campus zones with lat/lon
    │
    ├── engine/
    │   ├── __init__.py
    │   ├── node_simulator.py       ← generic NodeSimulator class (no per-type subclassing)
    │   └── generator_engine.py     ← dispatches RandomWalk / Sine / StepChange per field spec
    │
    ├── generators/                 ← signal math primitives
    │   ├── __init__.py
    │   ├── random_walk.py
    │   ├── sine_wave.py
    │   └── step_change.py
    │
    └── transport/                  ← async protocol senders
        ├── __init__.py
        ├── base.py                 ← ProtocolSender ABC
        ├── http_sender.py          ← aiohttp → :8000/api/telemetry
        ├── mqtt_sender.py          ← aiomqtt → :1883/smartcity/telemetry/{domain}
        ├── coap_sender.py          ← aiocoap → coap://localhost:5683/telemetry
        └── websocket_sender.py     ← websockets → ws://localhost:8000/ws/actuator


core_modules/IngestionEngine/
├── main.py                         ← UPDATED: starts CoAP server + WS endpoint
├── requirements.txt                ← UPDATED: aiocoap, websockets
├── adapters/
│   ├── base.py                     ← (unchanged)
│   ├── http_adapter.py             ← FIX: "data" → "payload" key
│   ├── mqtt_adapter.py             ← FIX: "data" → "payload" key
│   ├── coap_adapter.py             ← 🆕 CoAP server resource + parser
│   └── websocket_adapter.py        ← 🆕 WS endpoint for actuator feedback
└── broker/
    └── embedded_mqtt.py            ← (unchanged)
```

---

## 📋 Part 1: `node_schemas.json` — The Master Config

This is the **single source of truth** for the entire simulation.

### Structure

```jsonc
{
  "simulation": {
    "default_interval_s": 3,
    "interval_jitter_s": 1.5
  },

  "ingestion_endpoints": {
    "http":      "http://localhost:8000/api/telemetry",
    "mqtt_host": "localhost",
    "mqtt_port": 1883,
    "mqtt_topic_prefix": "smartcity/telemetry",
    "coap_uri":  "coap://localhost:5683/telemetry",
    "ws_url":    "ws://localhost:8000/ws/actuator"
  },

  "campus_zones": [
    { "zone_id": "BLK-A",     "name": "Engineering Block A", "lat": 12.9716, "lon": 77.5946 },
    { "zone_id": "BLK-B",     "name": "Engineering Block B", "lat": 12.9720, "lon": 77.5952 },
    { "zone_id": "LIB",       "name": "Central Library",     "lat": 12.9712, "lon": 77.5940 },
    { "zone_id": "HOSTEL-N",  "name": "North Hostel",        "lat": 12.9730, "lon": 77.5960 },
    { "zone_id": "HOSTEL-S",  "name": "South Hostel",        "lat": 12.9705, "lon": 77.5935 },
    { "zone_id": "CAFETERIA", "name": "Main Cafeteria",      "lat": 12.9718, "lon": 77.5948 },
    { "zone_id": "SPORTS",    "name": "Sports Complex",      "lat": 12.9725, "lon": 77.5970 },
    { "zone_id": "ADMIN",     "name": "Administration Block","lat": 12.9710, "lon": 77.5938 },
    { "zone_id": "GARDEN",    "name": "Campus Garden",       "lat": 12.9700, "lon": 77.5930 },
    { "zone_id": "PARKING",   "name": "Parking Lot",         "lat": 12.9735, "lon": 77.5975 }
  ],

  "node_types": [

    {
      "node_type": "solar_panel",
      "domain": "energy",
      "protocol": "MQTT",
      "is_actuator": false,
      "count": 8,
      "payload_schema": {
        "power_w":     { "generator": "sine",        "amplitude": 500, "offset": 500, "period_s": 86400, "phase_h": 12, "min": 0,   "max": 1000 },
        "energy_kwh":  { "generator": "random_walk", "initial": 10,   "min": 0,   "max": 50,  "step": 0.4 },
        "voltage":     { "generator": "random_walk", "initial": 230,  "min": 220, "max": 240, "step": 0.5 },
        "current":     { "generator": "random_walk", "initial": 4.5,  "min": 0,   "max": 10,  "step": 0.1 },
        "status":      { "generator": "step_change", "states": ["ACTIVE","IDLE","FAULT"], "initial": "ACTIVE", "flip_prob": 0.01 }
      }
    },

    {
      "node_type": "smart_energy_meter",
      "domain": "energy",
      "protocol": "MQTT",
      "is_actuator": false,
      "count": 6,
      "payload_schema": {
        "voltage":      { "generator": "random_walk", "initial": 230,  "min": 210, "max": 250, "step": 1.0  },
        "current":      { "generator": "random_walk", "initial": 5.0,  "min": 0,   "max": 20,  "step": 0.3  },
        "power":        { "generator": "random_walk", "initial": 1150, "min": 500, "max": 5000,"step": 50   },
        "energy_kwh":   { "generator": "random_walk", "initial": 20,   "min": 0,   "max": 200, "step": 0.5  },
        "power_factor": { "generator": "random_walk", "initial": 0.95, "min": 0.8, "max": 1.0, "step": 0.01 }
      }
    },

    {
      "node_type": "battery_storage",
      "domain": "energy",
      "protocol": "HTTP",
      "is_actuator": false,
      "count": 4,
      "payload_schema": {
        "soc":         { "generator": "sine",        "amplitude": 40,  "offset": 50,  "period_s": 86400, "phase_h": 18, "min": 5, "max": 95 },
        "voltage":     { "generator": "random_walk", "initial": 48.0, "min": 44, "max": 54, "step": 0.2 },
        "charge_rate": { "generator": "random_walk", "initial": 1.5,  "min": -5, "max": 5,  "step": 0.1 },
        "status":      { "generator": "step_change", "states": ["CHARGING","DISCHARGING","IDLE"], "initial": "CHARGING", "flip_prob": 0.02 }
      }
    },

    {
      "node_type": "grid_transformer",
      "domain": "energy",
      "protocol": "HTTP",
      "is_actuator": false,
      "count": 3,
      "payload_schema": {
        "load_percent":  { "generator": "random_walk", "initial": 55, "min": 10, "max": 95, "step": 2.0 },
        "temperature":   { "generator": "random_walk", "initial": 45, "min": 30, "max": 80, "step": 0.5 },
        "fault_status":  { "generator": "step_change", "states": ["OK","WARNING","FAULT"], "initial": "OK", "flip_prob": 0.005 }
      }
    },

    {
      "node_type": "occupancy_footfall",
      "domain": "energy",
      "protocol": "CoAP",
      "is_actuator": false,
      "count": 4,
      "payload_schema": {
        "occupancy": { "generator": "step_change", "states": ["OCCUPIED","EMPTY"], "initial": "OCCUPIED", "flip_prob": 0.05 },
        "count":     { "generator": "random_walk", "initial": 20, "min": 0, "max": 300, "step": 5 }
      }
    },

    {
      "node_type": "ac_unit",
      "domain": "energy",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 5,
      "payload_schema": {
        "state":        { "generator": "step_change", "states": ["ON","OFF"], "initial": "ON", "flip_prob": 0.03 },
        "set_temp":     { "generator": "step_change", "states": [22,24,26], "initial": 24, "flip_prob": 0.02 },
        "mode":         { "generator": "step_change", "states": ["COOL","FAN","AUTO"], "initial": "COOL", "flip_prob": 0.01 },
        "current_temp": { "generator": "random_walk", "initial": 25.0, "min": 18, "max": 35, "step": 0.3 },
        "power_usage":  { "generator": "random_walk", "initial": 1500, "min": 0, "max": 3500, "step": 50 }
      }
    },

    {
      "node_type": "indoor_lighting",
      "domain": "energy",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 5,
      "payload_schema": {
        "state":       { "generator": "step_change", "states": ["ON","OFF"], "initial": "ON", "flip_prob": 0.04 },
        "brightness":  { "generator": "random_walk", "initial": 80, "min": 0, "max": 100, "step": 5 },
        "power_usage": { "generator": "random_walk", "initial": 40, "min": 0, "max": 200, "step": 3 }
      }
    },

    {
      "node_type": "outdoor_lamp",
      "domain": "energy",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 5,
      "payload_schema": {
        "state":        { "generator": "step_change", "states": ["ON","OFF"], "initial": "ON", "flip_prob": 0.02 },
        "brightness":   { "generator": "random_walk", "initial": 100, "min": 0, "max": 100, "step": 5 },
        "fault_status": { "generator": "step_change", "states": ["OK","FAULT"], "initial": "OK", "flip_prob": 0.005 }
      }
    },

    {
      "node_type": "water_quality",
      "domain": "water",
      "protocol": "CoAP",
      "is_actuator": false,
      "count": 5,
      "payload_schema": {
        "ph":                  { "generator": "random_walk", "initial": 7.2, "min": 6.5, "max": 8.5, "step": 0.05 },
        "turbidity":           { "generator": "random_walk", "initial": 1.5, "min": 0.1, "max": 10,  "step": 0.1  },
        "tds":                 { "generator": "random_walk", "initial": 250, "min": 50,  "max": 600, "step": 5    },
        "temperature":         { "generator": "random_walk", "initial": 22,  "min": 10,  "max": 35,  "step": 0.3  },
        "contamination_level": { "generator": "step_change", "states": ["SAFE","MODERATE","CRITICAL"], "initial": "SAFE", "flip_prob": 0.02 }
      }
    },

    {
      "node_type": "reservoir_level",
      "domain": "water",
      "protocol": "MQTT",
      "is_actuator": false,
      "count": 3,
      "payload_schema": {
        "level_percent": { "generator": "random_walk", "initial": 75,  "min": 5,  "max": 100, "step": 0.8 },
        "volume":        { "generator": "random_walk", "initial": 7500,"min": 500,"max": 10000,"step": 80 }
      }
    },

    {
      "node_type": "soil_moisture",
      "domain": "water",
      "protocol": "CoAP",
      "is_actuator": false,
      "count": 4,
      "payload_schema": {
        "moisture_level": { "generator": "sine", "amplitude": 30, "offset": 50, "period_s": 86400, "phase_h": 14, "min": 10, "max": 90 }
      }
    },

    {
      "node_type": "smart_water_meter",
      "domain": "water",
      "protocol": "MQTT",
      "is_actuator": false,
      "count": 4,
      "payload_schema": {
        "flow_rate":         { "generator": "random_walk", "initial": 5.0, "min": 0, "max": 30,  "step": 0.5 },
        "total_consumption": { "generator": "random_walk", "initial": 100, "min": 0, "max": 5000,"step": 2   },
        "leak_detected":     { "generator": "step_change", "states": [false, true], "initial": false, "flip_prob": 0.01 }
      }
    },

    {
      "node_type": "valve_control",
      "domain": "water",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 4,
      "payload_schema": {
        "state":       { "generator": "step_change", "states": ["OPEN","CLOSED"], "initial": "CLOSED", "flip_prob": 0.04 },
        "valve_level": { "generator": "random_walk", "initial": 50, "min": 0, "max": 100, "step": 5 }
      }
    },

    {
      "node_type": "water_treatment",
      "domain": "water",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 3,
      "payload_schema": {
        "state":         { "generator": "step_change", "states": ["RUNNING","STOPPED"], "initial": "RUNNING", "flip_prob": 0.03 },
        "chemical_dose": { "generator": "random_walk", "initial": 2.5, "min": 0, "max": 10, "step": 0.2 }
      }
    },

    {
      "node_type": "water_pump",
      "domain": "water",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 3,
      "payload_schema": {
        "state":       { "generator": "step_change", "states": ["ON","OFF"], "initial": "ON", "flip_prob": 0.03 },
        "flow_level":  { "generator": "random_walk", "initial": 60, "min": 0, "max": 100, "step": 4 },
        "power_usage": { "generator": "random_walk", "initial": 800,"min": 0, "max": 2000,"step": 30 }
      }
    },

    {
      "node_type": "air_quality",
      "domain": "air",
      "protocol": "MQTT",
      "is_actuator": false,
      "count": 5,
      "payload_schema": {
        "pm2_5": { "generator": "random_walk", "initial": 12, "min": 1,  "max": 250, "step": 2   },
        "pm10":  { "generator": "random_walk", "initial": 25, "min": 1,  "max": 400, "step": 3   },
        "co2":   { "generator": "random_walk", "initial": 420,"min": 350,"max": 2000,"step": 10  },
        "no2":   { "generator": "random_walk", "initial": 0.02,"min":0,  "max": 0.2, "step": 0.005},
        "o3":    { "generator": "random_walk", "initial": 0.03,"min":0,  "max": 0.1, "step": 0.002}
      }
    },

    {
      "node_type": "temp_humidity",
      "domain": "air",
      "protocol": "CoAP",
      "is_actuator": false,
      "count": 5,
      "payload_schema": {
        "temperature": { "generator": "sine",        "amplitude": 7,  "offset": 26, "period_s": 86400, "phase_h": 14, "min": 15, "max": 40 },
        "humidity":    { "generator": "random_walk", "initial": 55,   "min": 20,    "max": 95,  "step": 1.5 }
      }
    },

    {
      "node_type": "wind_monitor",
      "domain": "air",
      "protocol": "MQTT",
      "is_actuator": false,
      "count": 3,
      "payload_schema": {
        "wind_speed":     { "generator": "random_walk", "initial": 12,  "min": 0,   "max": 60,  "step": 1.5 },
        "wind_direction": { "generator": "random_walk", "initial": 180, "min": 0,   "max": 360, "step": 10  }
      }
    },

    {
      "node_type": "environmental_sensor",
      "domain": "air",
      "protocol": "CoAP",
      "is_actuator": false,
      "count": 5,
      "payload_schema": {
        "temperature": { "generator": "sine",        "amplitude": 6,  "offset": 27, "period_s": 86400, "phase_h": 14, "min": 15, "max": 40 },
        "humidity":    { "generator": "random_walk", "initial": 60,   "min": 20,    "max": 95,  "step": 1.5 },
        "pm2_5":       { "generator": "random_walk", "initial": 14,   "min": 1,     "max": 250, "step": 2   },
        "co2":         { "generator": "random_walk", "initial": 450,  "min": 350,   "max": 2000,"step": 10  },
        "noise_db":    { "generator": "random_walk", "initial": 52,   "min": 30,    "max": 110, "step": 1.5 }
      }
    },

    {
      "node_type": "ventilation_control",
      "domain": "air",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 6,
      "payload_schema": {
        "state": { "generator": "step_change", "states": ["ON","OFF"],              "initial": "ON",  "flip_prob": 0.03 },
        "speed": { "generator": "step_change", "states": ["LOW","MEDIUM","HIGH"],   "initial": "MEDIUM", "flip_prob": 0.05 }
      }
    },

    {
      "node_type": "air_purification",
      "domain": "air",
      "protocol": "WebSocket",
      "is_actuator": true,
      "count": 6,
      "payload_schema": {
        "state":             { "generator": "step_change", "states": ["ON","OFF"],                  "initial": "ON", "flip_prob": 0.03 },
        "mode":              { "generator": "step_change", "states": ["AUTO","TURBO","SLEEP"],      "initial": "AUTO","flip_prob": 0.02 },
        "air_quality_index": { "generator": "random_walk", "initial": 45, "min": 0, "max": 300,    "step": 3 }
      }
    }

  ]
}
```

**Total node count = sum of all `count` fields = 100.**

### Extensibility Rule

To add a new node type at runtime:
1. Add a new object to `node_types[]` in `node_schemas.json`
2. Set `count`, `protocol`, `domain`, and `payload_schema` with generator specs
3. Restart the simulator — the `NodeFactory` instantiates it automatically
4. **Zero Python code changes required**

---

## 📋 Part 2: Simulator Engine

### `generators/random_walk.py`
```python
class RandomWalk:
    def __init__(self, initial, lo, hi, step):
        self.value = initial
        self.lo, self.hi, self.step = lo, hi, step

    def next(self) -> float:
        self.value = max(self.lo, min(self.hi,
            self.value + random.uniform(-self.step, self.step)))
        return round(self.value, 3)
```

### `generators/sine_wave.py`
```python
class SineWave:
    def __init__(self, amplitude, offset, period_s, phase_h=0, lo=None, hi=None):
        self.amplitude = amplitude
        self.offset = offset
        self.period_s = period_s
        self.phase_s = phase_h * 3600
        self.lo = lo
        self.hi = hi

    def value_at(self, epoch: float) -> float:
        raw = self.offset + self.amplitude * math.sin(
            2 * math.pi * (epoch + self.phase_s) / self.period_s
        )
        if self.lo is not None: raw = max(self.lo, raw)
        if self.hi is not None: raw = min(self.hi, raw)
        return round(raw, 3)
```

### `generators/step_change.py`
```python
class StepChange:
    def __init__(self, states, initial, flip_prob=0.02):
        self.states = states
        self.state = initial
        self.flip_prob = flip_prob

    def next(self):
        if random.random() < self.flip_prob:
            others = [s for s in self.states if s != self.state]
            self.state = random.choice(others)
        return self.state
```

---

### `engine/generator_engine.py`

Reads a single field spec dict from JSON and returns the right generator object:

```python
def build_generator(spec: dict):
    g = spec["generator"]
    if g == "random_walk":
        return RandomWalk(spec["initial"], spec["min"], spec["max"], spec["step"])
    elif g == "sine":
        return SineWave(spec["amplitude"], spec["offset"], spec["period_s"],
                        spec.get("phase_h", 0), spec.get("min"), spec.get("max"))
    elif g == "step_change":
        return StepChange(spec["states"], spec["initial"], spec.get("flip_prob", 0.02))
    else:
        raise ValueError(f"Unknown generator: {g}")
```

---

### `engine/node_simulator.py` — Generic (No per-type subclasses)

```python
class NodeSimulator:
    def __init__(self, node_id, node_type, domain, location, protocol_sender,
                 payload_generators: dict, is_actuator: bool, interval: float):
        self.node_id = node_id
        self.node_type = node_type
        self.domain = domain
        self.location = location
        self.sender = protocol_sender
        self.generators = payload_generators   # { field_name: Generator }
        self.is_actuator = is_actuator
        self.interval = interval
        self.state = "RUNNING"
        self.health_status = "OK"

    def generate_payload(self) -> dict:
        epoch = time.time()
        out = {}
        for field, gen in self.generators.items():
            if hasattr(gen, 'value_at'):       # SineWave
                out[field] = gen.value_at(epoch)
            else:                              # RandomWalk, StepChange
                out[field] = gen.next()
        return out

    def build_iot_node(self, payload: dict) -> dict:
        return {
            "node_id":        self.node_id,
            "node_type":      self.node_type,
            "domain":         self.domain,
            "timestamp":      datetime.utcnow().isoformat() + "Z",
            "location": {
                "latitude":  self.location["lat"],
                "longitude": self.location["lon"],
                "zone":      self.location["zone_id"]
            },
            "protocol_source": self.sender.protocol_name,
            "state":           self.state,
            "health_status":   self.health_status,
            "payload":         payload
        }

    async def run(self):
        while True:
            payload = self.generate_payload()
            iot_node = self.build_iot_node(payload)
            await self.sender.send(iot_node)
            await asyncio.sleep(self.interval + random.uniform(-1, 1))
```

---

### `node_factory.py` — JSON → 100 NodeSimulator instances

```python
class NodeFactory:
    def __init__(self, schema_path: str):
        with open(schema_path) as f:
            self.config = json.load(f)

    def build_all(self) -> list[NodeSimulator]:
        nodes = []
        zones = self.config["campus_zones"]
        endpoints = self.config["ingestion_endpoints"]
        senders = {
            "HTTP":      HttpSender(endpoints["http"]),
            "MQTT":      MqttSender(endpoints["mqtt_host"], endpoints["mqtt_port"],
                                    endpoints["mqtt_topic_prefix"]),
            "CoAP":      CoAPSender(endpoints["coap_uri"]),
            "WebSocket": WebSocketSender(endpoints["ws_url"]),
        }

        zone_cursor = 0
        for type_spec in self.config["node_types"]:
            for i in range(type_spec["count"]):
                zone = zones[zone_cursor % len(zones)]
                zone_cursor += 1

                generators = {
                    field: build_generator(spec)
                    for field, spec in type_spec["payload_schema"].items()
                }

                node_id = f"{type_spec['node_type'].upper()}-{len(nodes)+1:03d}"

                nodes.append(NodeSimulator(
                    node_id=node_id,
                    node_type=type_spec["node_type"],
                    domain=type_spec["domain"],
                    location=zone,
                    protocol_sender=senders[type_spec["protocol"]],
                    payload_generators=generators,
                    is_actuator=type_spec["is_actuator"],
                    interval=self.config["simulation"]["default_interval_s"]
                ))
        return nodes
```

---

### `main.py` — asyncio entry point

```python
async def main():
    factory = NodeFactory("node_schemas.json")
    nodes = factory.build_all()
    print(f"[Simulator] Launching {len(nodes)} nodes...")
    await asyncio.gather(*[node.run() for node in nodes])

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📡 Part 3: Transport Senders

### `transport/base.py`
```python
class ProtocolSender(ABC):
    protocol_name: str

    @abstractmethod
    async def send(self, iot_node: dict): ...
```

### `transport/http_sender.py` — aiohttp
```python
class HttpSender(ProtocolSender):
    protocol_name = "HTTP_POST"

    def __init__(self, url: str):
        self.url = url
        self._session: aiohttp.ClientSession = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send(self, iot_node: dict):
        try:
            session = await self._get_session()
            async with session.post(self.url, json=iot_node, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                pass
        except Exception as e:
            print(f"[HTTP] Failed for {iot_node['node_id']}: {e}")
```

### `transport/mqtt_sender.py` — aiomqtt
```python
class MqttSender(ProtocolSender):
    protocol_name = "MQTT_PUB"

    def __init__(self, host, port, topic_prefix):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix
        self._client = None

    async def _ensure_client(self):
        if self._client is None:
            self._client = aiomqtt.Client(hostname=self.host, port=self.port)
            await self._client.__aenter__()

    async def send(self, iot_node: dict):
        try:
            await self._ensure_client()
            topic = f"{self.topic_prefix}/{iot_node['domain']}"
            await self._client.publish(topic, json.dumps(iot_node))
        except Exception as e:
            print(f"[MQTT] Failed for {iot_node['node_id']}: {e}")
```

### `transport/coap_sender.py` — aiocoap ✨ NEW
```python
class CoAPSender(ProtocolSender):
    protocol_name = "CoAP_PUT"

    def __init__(self, coap_uri: str):
        self.uri = coap_uri
        self._context = None

    async def _ensure_context(self):
        if self._context is None:
            self._context = await aiocoap.Context.create_client_context()

    async def send(self, iot_node: dict):
        try:
            await self._ensure_context()
            payload = json.dumps(iot_node).encode("utf-8")
            request = aiocoap.Message(
                code=aiocoap.PUT,
                uri=self.uri,
                payload=payload
            )
            request.opt.content_format = 50   # application/json (IANA 50)
            await self._context.request(request).response
        except Exception as e:
            print(f"[CoAP] Failed for {iot_node['node_id']}: {e}")
```

### `transport/websocket_sender.py` — actuators only
```python
class WebSocketSender(ProtocolSender):
    protocol_name = "WebSocket"

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None

    async def _ensure_connection(self):
        if self._ws is None or self._ws.closed:
            self._ws = await websockets.connect(self.ws_url)

    async def send(self, iot_node: dict):
        try:
            await self._ensure_connection()
            await self._ws.send(json.dumps(iot_node))
        except Exception as e:
            self._ws = None  # force reconnect next tick
            print(f"[WS] Reconnecting for {iot_node['node_id']}: {e}")
```

---

## 🔌 Part 4: IngestionEngine — Protocol Updates

### What changes

| File | Change Type | What |
|---|---|---|
| `adapters/http_adapter.py` | **FIX** | `raw_data.get("data")` → `raw_data.get("payload")` |
| `adapters/mqtt_adapter.py` | **FIX** | same fix |
| `adapters/coap_adapter.py` | **NEW** | aiocoap server resource, parses PUT body |
| `adapters/websocket_adapter.py` | **NEW** | FastAPI WebSocket route for actuator feedback |
| `main.py` | **UPDATE** | starts CoAP server + mounts WS route |
| `requirements.txt` | **UPDATE** | adds `aiocoap`, `websockets` |

---

### `adapters/http_adapter.py` — Fixed Key
```python
def standard_parse(self, raw_data: dict) -> SmartCityObject:
    return SmartCityObject(
        node_id=raw_data.get("node_id", "unknown"),
        domain=raw_data.get("domain", "unknown"),
        timestamp=raw_data.get("timestamp", ""),
        payload=raw_data.get("payload", {}),        # ← was "data"
        protocol_source="HTTP_POST"
    )
```

### `adapters/mqtt_adapter.py` — Fixed Key
```python
def standard_parse(self, raw_data: dict) -> SmartCityObject:
    return SmartCityObject(
        node_id=raw_data.get("node_id", "unknown"),
        domain=raw_data.get("domain", "unknown"),
        timestamp=raw_data.get("timestamp", ""),
        payload=raw_data.get("payload", {}),        # ← was "data"
        protocol_source="MQTT_PUB"
    )
```

---

### `adapters/coap_adapter.py` — NEW
```python
import json
import aiocoap
import aiocoap.resource as resource
from models.domain import SmartCityObject

class TelemetryResource(resource.Resource):
    """
    CoAP server-side resource mounted at /telemetry.
    Accepts PUT requests from CoAP sender nodes.
    Parses the JSON body and forwards via the RabbitMQForwarder.
    """
    def __init__(self, forwarder):
        super().__init__()
        self.forwarder = forwarder

    async def render_put(self, request):
        try:
            raw_data = json.loads(request.payload.decode("utf-8"))
            obj = SmartCityObject(
                node_id=raw_data.get("node_id", "unknown"),
                domain=raw_data.get("domain", "unknown"),
                timestamp=raw_data.get("timestamp", ""),
                payload=raw_data.get("payload", {}),
                protocol_source="CoAP_PUT"
            )
            self.forwarder.forward(obj)
            return aiocoap.Message(code=aiocoap.CHANGED)
        except Exception as e:
            print(f"[CoAP Adapter] Parse error: {e}")
            return aiocoap.Message(code=aiocoap.BAD_REQUEST)


async def start_coap_server(forwarder):
    """
    Starts the aiocoap server in the existing asyncio event loop.
    Called from Ingestion Engine startup.
    """
    root = resource.Site()
    root.add_resource(['telemetry'], TelemetryResource(forwarder))
    await aiocoap.Context.create_server_context(root, bind=("0.0.0.0", 5683))
    print("[CoAP Server] Listening on UDP :5683")
```

---

### `adapters/websocket_adapter.py` — NEW
```python
from fastapi import WebSocket, WebSocketDisconnect
from models.domain import SmartCityObject

class WebSocketAdapter:
    """
    Receives actuator state feedback sent via WebSocket.
    Mounted as a FastAPI route in main.py.
    """
    def __init__(self, forwarder):
        self.forwarder = forwarder

    async def handle(self, websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                raw_text = await websocket.receive_text()
                raw_data = json.loads(raw_text)
                obj = SmartCityObject(
                    node_id=raw_data.get("node_id", "unknown"),
                    domain=raw_data.get("domain", "unknown"),
                    timestamp=raw_data.get("timestamp", ""),
                    payload=raw_data.get("payload", {}),
                    protocol_source="WebSocket"
                )
                self.forwarder.forward(obj)
                await websocket.send_text(json.dumps({"ack": "received"}))
        except WebSocketDisconnect:
            print(f"[WS Adapter] Client disconnected")
```

---

### `main.py` — Updated Ingestion Engine
```python
import asyncio, threading, time
from fastapi import FastAPI, Request, WebSocket
from adapters.base import RabbitMQForwarder
from adapters.http_adapter import HttpAdapter
from adapters.mqtt_adapter import MqttAdapter
from adapters.coap_adapter import start_coap_server
from adapters.websocket_adapter import WebSocketAdapter
from broker.embedded_mqtt import start_embedded_broker_sync

app = FastAPI(title="IoT Ingestion Engine")

forwarder = RabbitMQForwarder(host="localhost")
http_adapter = HttpAdapter(forwarder)
mqtt_adapter = MqttAdapter(forwarder)
ws_adapter = WebSocketAdapter(forwarder)

@app.on_event("startup")
async def startup_event():
    # 1. Embedded MQTT Broker (thread with its own loop)
    threading.Thread(target=start_embedded_broker_sync, daemon=True).start()
    await asyncio.sleep(1)

    # 2. MQTT listener
    mqtt_adapter.start_listening()

    # 3. CoAP server (runs in same asyncio loop as FastAPI)
    asyncio.create_task(start_coap_server(forwarder))

    print("[Ingestion Engine] HTTP:8000 | MQTT:1883 | CoAP:5683 | WS:/ws/actuator — ALL LIVE")

@app.post("/api/telemetry")
async def receive_http(request: Request):
    raw = await request.json()
    http_adapter.process_and_forward(raw)
    return {"status": "ingested", "protocol": "HTTP"}

@app.websocket("/ws/actuator")
async def websocket_actuator(websocket: WebSocket):
    await ws_adapter.handle(websocket)
```

---

## 🔄 Part 5: Data Flow Per Protocol

| Protocol | Simulator → | Ingestion listens on | Parsed by | Forwarded via |
|---|---|---|---|---|
| HTTP POST | `aiohttp` → `:8000/api/telemetry` | FastAPI `@app.post` | `HttpAdapter` | `RabbitMQForwarder` |
| MQTT PUBLISH | `aiomqtt` → `:1883` topic | `MqttAdapter.start_listening()` | `MqttAdapter` | `RabbitMQForwarder` |
| CoAP PUT | `aiocoap` → `:5683/telemetry` | `aiocoap` resource server | `TelemetryResource` | `RabbitMQForwarder` |
| WebSocket | `websockets` → `:8000/ws/actuator`| FastAPI `@app.websocket` | `WebSocketAdapter` | `RabbitMQForwarder` |

**All 4 protocols converge to a single `SmartCityObject` → RabbitMQ → Middleware.**

---

## 📊 Part 6: Node Distribution Summary (100 Nodes)

| Domain | Node Type | Protocol | Count |
|--------|-----------|----------|-------|
| energy | solar_panel | MQTT | 8 |
| energy | smart_energy_meter | MQTT | 6 |
| energy | battery_storage | HTTP | 4 |
| energy | grid_transformer | HTTP | 3 |
| energy | occupancy_footfall | CoAP | 4 |
| energy | ac_unit | WebSocket | 5 |
| energy | indoor_lighting | WebSocket | 5 |
| energy | outdoor_lamp | WebSocket | 5 |
| water | water_quality | CoAP | 5 |
| water | reservoir_level | MQTT | 3 |
| water | soil_moisture | CoAP | 4 |
| water | smart_water_meter | MQTT | 4 |
| water | valve_control | WebSocket | 4 |
| water | water_treatment | WebSocket | 3 |
| water | water_pump | WebSocket | 3 |
| air | air_quality | MQTT | 5 |
| air | temp_humidity | CoAP | 5 |
| air | wind_monitor | MQTT | 3 |
| air | environmental_sensor | CoAP | 5 |
| air | ventilation_control | WebSocket | 6 |
| air | air_purification | WebSocket | 6 |
| **TOTAL** | **21 types** | **4 protocols** | **100** |

---

## 🔧 Dependencies

### `IOTDataGenerator/requirements.txt`
```
aiohttp>=3.9.0
aiomqtt>=1.2.0
aiocoap>=0.4.7
websockets>=12.0
pydantic>=2.0
```

### `IngestionEngine/requirements.txt` (additions)
```
fastapi==0.103.1
uvicorn==0.23.2
paho-mqtt==1.6.1
amqtt==0.11.0
pika==1.3.2
aiocoap>=0.4.7
websockets>=12.0
```

---

## ✅ Implementation Checklist

```
[ ] 1.  Write node_schemas.json (all 21 types, 100 nodes total)
[ ] 2.  Create simulator/ package skeleton (__init__.py files)
[ ] 3.  Implement generators/random_walk.py
[ ] 4.  Implement generators/sine_wave.py
[ ] 5.  Implement generators/step_change.py
[ ] 6.  Implement engine/generator_engine.py (dispatcher)
[ ] 7.  Implement engine/node_simulator.py (generic, no per-type subclasses)
[ ] 8.  Implement campus_map.py (10 zones)
[ ] 9.  Implement transport/base.py (ProtocolSender ABC)
[ ] 10. Implement transport/http_sender.py
[ ] 11. Implement transport/mqtt_sender.py
[ ] 12. Implement transport/coap_sender.py  ← NEW
[ ] 13. Implement transport/websocket_sender.py
[ ] 14. Implement node_factory.py (JSON reader + factory)
[ ] 15. Implement simulator/main.py (asyncio entry)
[ ] 16. Update IOTDataGenerator/requirements.txt
[ ] 17. FIX IngestionEngine/adapters/http_adapter.py ("data" → "payload")
[ ] 18. FIX IngestionEngine/adapters/mqtt_adapter.py ("data" → "payload")
[ ] 19. NEW  IngestionEngine/adapters/coap_adapter.py
[ ] 20. NEW  IngestionEngine/adapters/websocket_adapter.py
[ ] 21. UPDATE IngestionEngine/main.py (CoAP server + WS route + async startup)
[ ] 22. Update IngestionEngine/requirements.txt
[ ] 23. Write README_SIMULATOR.md
```

---

## 🚀 How to Run

```bash
# Terminal 1 — Persistent Middleware (DB + RabbitMQ consumer)
cd core_modules/PersistentMiddleware
pip install -r requirements.txt
uvicorn main:app --port 8001

# Terminal 2 — Ingestion Engine (HTTP + MQTT + CoAP + WebSocket)
cd core_modules/IngestionEngine
pip install -r requirements.txt
uvicorn main:app --port 8000

# Terminal 3 — IoT Simulator (reads node_schemas.json, emits 100 nodes)
cd IOTDataGenerator
pip install -r requirements.txt
python -m simulator.main

# View Middleware Dashboard
open http://localhost:8001/view
```

---

## 🏗️ Design Principles

| Principle | Enforcement |
|---|---|
| **Open/Closed** | New node type = JSON edit only; `NodeFactory` handles the rest |
| **Strategy Pattern** | 4 protocol senders are injected; `NodeSimulator` calls `sender.send()` |
| **Single Responsibility** | `generators/` = math only; `engine/` = node lifecycle; `transport/` = network only |
| **DRY** | One generic `NodeSimulator` class replaces 21 per-type subclasses |
| **async-first** | `asyncio.gather` on 100 coroutines; no `threading`, no `time.sleep` |
| **Schema-Driven** | All node topology, payload fields, and generator config live in one JSON |
