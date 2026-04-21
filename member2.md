# Member 2 — EHS Engine + Data Ingestion & Semantic Middleware

> **Role:** Environmental Health & Safety Lead + Data Pipeline Owner  
> **Scope:** End-to-end EHS Engine implementation AND the upstream data pipeline (Ingestion Gateway + Semantic Middleware) that feeds ALL domain engines.

---

## 1. Feature Overview

### Feature A — EHS (Environmental Health & Safety) Engine
A **FastAPI microservice plugin** that:
- Consumes standardized `EHS.*` topic events from RabbitMQ
- Monitors real-time Air Quality Index (AQI) and water quality (pH, turbidity)
- Runs ready-made ML models to forecast water quality trends
- Evaluates safety thresholds and publishes emergency alerts
- Persists all environmental telemetry to InfluxDB

### Feature B — Data Ingestion & Semantic Middleware (Shared Infrastructure)
The foundational pipeline that ALL other engines depend on:
- IoT Ingestion Gateway (MQTT/HTTP endpoints for 300 heterogeneous nodes)
- Semantic Middleware (OneM2M ontology translation + RabbitMQ publishing)

### Functional Requirements Covered
| ID | Requirement |
|:---|:---|
| **FR-H1** | Visualize real-time AQI and water quality (pH, turbidity) data |
| **FR-H2** | Configure SMS/Email alert thresholds for hazardous conditions |
| **FR-H3** | Report calibration status and heartbeat of all 300 sensor nodes |
| **FR-H4** | Generate water quality forecasts using predictive algorithms |

---

## 2. Design Patterns & Architectural Rationale

### 2.1 Adapter Pattern — Protocol Heterogeneity (Ingestion Gateway)
**Problem:** 300 IoT nodes speak different protocols — MQTT, CoAP, HTTP REST, raw TCP camera streams. The system cannot embed protocol-specific parsing into the core.  
**Solution:** Use the **Adapter Pattern** to wrap each protocol behind a unified `SensorAdapter` interface. Each adapter translates its native protocol into a common `RawSensorPayload` object.

```
┌─────────────────────────┐
│    SensorAdapter        │ <<interface>>
│  + ingest() → RawPayload│
│  + healthcheck() → bool │
└────────┬────────────────┘
         │ implements
   ┌─────┴──────┬──────────────┬────────────────┐
   │            │              │                │
┌──▼───┐  ┌────▼────┐  ┌──────▼─────┐  ┌───────▼─────┐
│MQTT  │  │HTTP REST│  │CoAP        │  │Camera Stream│
│Adapt.│  │Adapter  │  │Adapter     │  │Adapter      │
└──────┘  └─────────┘  └────────────┘  └─────────────┘
```

**Monolith Tradeoff:** In a monolith, you'd write one giant `parse_input()` function with nested if-else. The Adapter Pattern enables **adding new hardware protocols without modifying existing adapter code** (Open/Closed Principle). The cost is more classes and files, but the maintainability gain is enormous for 300+ heterogeneous nodes.

### 2.2 Chain of Responsibility Pattern — Ingestion Validation Pipeline
**Problem:** Incoming raw data needs sequential checks: authentication → rate limiting → format validation → deduplication. Adding or reordering checks should be easy.  
**Solution:** Use **Chain of Responsibility**. Each validator is a link in a chain. If one fails, the chain short-circuits.

```
Request → [AuthValidator] → [RateLimiter] → [FormatValidator] → [DeduplicationFilter] → Accepted
                │                 │                  │                    │
              Reject           Throttle           Reject              Drop Duplicate
```

```python
class ValidationHandler(ABC):
    def __init__(self):
        self._next: Optional[ValidationHandler] = None
    
    def set_next(self, handler: 'ValidationHandler'):
        self._next = handler
        return handler
    
    def handle(self, payload: RawPayload) -> RawPayload:
        if self._next:
            return self._next.handle(payload)
        return payload

class AuthValidator(ValidationHandler):
    def handle(self, payload):
        if not self._check_whitelist(payload.mac):
            raise UnauthorizedNodeError(payload.node_id)
        return super().handle(payload)
```

### 2.3 Abstract Factory Pattern — Ontology Translation (Semantic Middleware)
**Problem:** Different IoT domains (EHS, Energy, CAM) require different ontology mappings when translating raw payloads to `SmartCityObject` format.  
**Solution:** Use an **Abstract Factory** that produces the correct family of translators based on the domain.

```
┌───────────────────────────┐
│  OntologyFactory          │ <<abstract>>
│  + create_translator()    │
│  + create_validator()     │
│  + create_enricher()      │
└───────────┬───────────────┘
    ┌───────┴──────┬──────────────┐
    │              │              │
┌───▼───┐  ┌──────▼─────┐  ┌────▼────┐
│EHS    │  │Energy      │  │CAM      │
│Factory│  │Factory     │  │Factory  │
└───────┘  └────────────┘  └─────────┘
```

Each factory produces domain-specific translators that know the correct units, thresholds, and location mappings for that domain.

### 2.4 Strategy Pattern — EHS ML Model Selection
**Problem:** Water quality forecasting can use multiple algorithms depending on the parameter (pH follows linear trends; turbidity follows non-linear patterns).  
**Solution:** Use the **Strategy Pattern** with `WaterForecastStrategy` interface and concrete implementations.

```python
class WaterForecastStrategy(ABC):
    @abstractmethod
    def predict(self, history: pd.DataFrame) -> ForecastResult: ...

class PHLinearStrategy(WaterForecastStrategy):
    """pH tends to change linearly — use linear regression."""
    
class TurbidityRFStrategy(WaterForecastStrategy):
    """Turbidity is non-linear — use Random Forest."""
```

### 2.5 Observer Pattern — EHS Threshold Monitoring
**Problem:** When AQI exceeds hazardous levels, multiple systems must react simultaneously (alert engine, dashboard update, device health logger).  
**Solution:** `EHSEvaluator` as **Subject** notifies observers when thresholds breach:
- `AlertPublisher` → publishes `Alerts.EHS.*` to RabbitMQ
- `TSDBWriter` → logs the breach event with severity
- `DeviceHealthMonitor` → flags the sensor for calibration check

### 2.6 Decorator Pattern — Data Enrichment Pipeline
**Problem:** Raw sensor data needs progressive enrichment: add location → add calibration offset → add unit conversion → add timestamp normalization. These enrichments should be composable and optional.  
**Solution:** Use the **Decorator Pattern** to wrap the base `SmartCityObject` with enrichment layers.

```python
class EnrichedReading(SensorReadingDecorator):
    def __init__(self, base: SensorReading):
        self._base = base
    
class LocationEnriched(EnrichedReading):
    def get_value(self):
        reading = self._base.get_value()
        reading["location"] = self._lookup_location(reading["node_id"])
        return reading

class CalibrationCorrected(EnrichedReading):
    def get_value(self):
        reading = self._base.get_value()
        reading["value"] += self._get_offset(reading["node_id"])
        return reading

# Composable pipeline:
reading = CalibrationCorrected(LocationEnriched(UnitConverted(raw_reading)))
```

### 2.7 Proxy Pattern — Device Health Monitor with Caching
**Problem:** Querying heartbeat status for all 300 nodes on every dashboard refresh is expensive.  
**Solution:** Use a **Proxy Pattern** — the `CachedHealthProxy` serves cached heartbeat data and only queries the real source every 30 seconds.

```python
class DeviceHealthProxy:
    def __init__(self, real_monitor: DeviceHealthMonitor):
        self._real = real_monitor
        self._cache = {}
        self._ttl = 30  # seconds
    
    def get_health(self, node_id):
        if self._is_stale(node_id):
            self._cache[node_id] = self._real.get_health(node_id)
        return self._cache[node_id]
```

---

## 3. Microservices Architecture Patterns

### 3.1 Anti-Corruption Layer (ACL) — Semantic Middleware
The Semantic Middleware IS an **Anti-Corruption Layer** in DDD terms. It prevents the messy, unstandardized IoT protocols from corrupting the clean domain model used by downstream engines.
- **External Model:** Raw MQTT JSON `{"id": "44A", "v": 142, "t": 1713700800}`
- **Internal Model:** Clean `SmartCityObject` with full context and typing
- **Benefit:** If a sensor vendor changes their payload format, only the ACL adapter changes — no domain engine is touched.

### 3.2 Event-Driven Architecture (EDA) — Topic-Based Routing
The Semantic Middleware uses a **Topic Exchange** pattern in RabbitMQ:
```
Exchange: smartcity.events (type: topic)
  ├── EHS.air_quality     → bound by EHS Engine
  ├── EHS.water_ph        → bound by EHS Engine
  ├── EHS.water_turbidity → bound by EHS Engine
  ├── Energy.solar        → bound by Energy Engine
  ├── Energy.ac_load      → bound by Energy Engine
  ├── Energy.lamppost     → bound by Energy Engine
  ├── CAM.crowd           → bound by CAM Engine
  └── CAM.auth            → bound by CAM Engine
```

### 3.3 Circuit Breaker — InfluxDB and RabbitMQ Resilience
Both the Middleware publisher and EHS TSDB writer are wrapped in Circuit Breakers:
- If RabbitMQ is down → Middleware buffers data in an in-memory queue (max 10,000 messages)
- If InfluxDB is down → EHS Engine buffers telemetry, returns last-known values to dashboards

### 3.4 Sidecar Pattern — Health Check Agent
A lightweight sidecar process monitors:
- Ingestion Gateway's MQTT broker health
- Semantic Middleware's RabbitMQ connection
- EHS Engine's consumer lag (how far behind real-time)
Exposes `/health` and `/metrics` endpoints for the orchestrator.

### 3.5 Dead-Letter Queue (DLQ) Pattern
Messages that fail processing 3 times in the EHS Engine are routed to a **Dead-Letter Exchange** for manual inspection:
```
EHS.air_quality → [EHS Consumer] → FAIL (3x) → DLQ: ehs.failed
```
This prevents poison messages from blocking the entire queue.

---

## 4. Monolith vs Microservice Tradeoffs

### Why Separate Ingestion + Middleware + EHS Engine?
| Aspect | Monolith (All-in-One) | Our Approach (3 Separate Services) |
|:---|:---|:---|
| **Scalability** | Can't scale ingestion separately from ML forecasting | Scale ingestion gateway to handle 300 nodes; EHS ML can run on GPU node |
| **Fault Isolation** | MQTT broker crash kills EHS dashboard | Gateway down → Middleware buffers → EHS serves cached data |
| **Protocol Evolution** | Adding CoAP requires redeploying the ML models too | Add a new Adapter in Gateway only |
| **Team Independence** | One merge-conflict-prone codebase | Member 2 owns 3 clear directories independently |

### What We Sacrifice
| Concern | Cost |
|:---|:---|
| **Latency** | Raw sensor → SmartCityObject → RabbitMQ → EHS Engine adds ~20-50ms end-to-end vs ~1ms in-process |
| **Consistency** | If Middleware publishes but EHS Engine is down, data sits in RabbitMQ — eventual consistency only |
| **Deployment Complexity** | Must start 3 services in correct order (Gateway → Middleware → EHS) |
| **Debugging** | Need correlation IDs to trace a reading from MQTT → Gateway → Middleware → RabbitMQ → EHS → InfluxDB |
| **Shared Schema** | `SmartCityObject` model is duplicated across services — schema changes need careful coordination |

### Mitigation Strategies
- **Correlation IDs:** Every `SmartCityObject` carries a UUID `trace_id` from ingestion to persistence
- **Shared Schema Library:** `backend/shared/models.py` contains `SmartCityObject` Pydantic model used by all services
- **Docker Compose Ordering:** `depends_on` ensures startup sequence
- **Contract Testing:** Middleware and EHS Engine agree on `SmartCityObject` schema via Pydantic validation

---

## 5. Deliverables

### Part A — Ingestion Gateway (`backend/ingestion_gateway/`)
- [ ] `SensorAdapter` interface + `MQTTAdapter`, `HTTPAdapter` implementations (**Adapter Pattern**)
- [ ] `ValidationHandler` chain: `AuthValidator` → `RateLimiter` → `FormatValidator` → `DeduplicationFilter` (**Chain of Responsibility**)
- [ ] `RawDispatcher` forwards validated data to Semantic Middleware
- [ ] Hardware whitelist lookup (PostgreSQL or config file)
- [ ] `/health` endpoint for sidecar monitoring

### Part B — Semantic Middleware (`backend/semantic_middleware/`)
- [ ] `OntologyFactory` + `EHSFactory`, `EnergyFactory`, `CAMFactory` (**Abstract Factory**)
- [ ] `OntologyTranslator` converts raw → `SmartCityObject` (OneM2M-inspired)
- [ ] Enrichment decorators: `LocationEnriched`, `CalibrationCorrected`, `UnitConverted` (**Decorator Pattern**)
- [ ] `knowledge_graph.json` — static node-ID-to-concept mapping
- [ ] `AMQPPublisher` — publishes to topic exchange with domain-based routing keys
- [ ] Circuit Breaker on RabbitMQ publisher
- [ ] Dead-Letter Queue configuration

### Part C — EHS Engine (`backend/ehs_engine/`)
- [ ] AMQP Consumer bound to `EHS.*` topics
- [ ] `EHSEvaluator` as Observer Subject with threshold checking
- [ ] Strategy Pattern for ML forecasting: `PHLinearStrategy`, `TurbidityRFStrategy`
- [ ] `CachedHealthProxy` for device heartbeat monitoring (**Proxy Pattern**)
- [ ] TSDB Synchronizer with Circuit Breaker
- [ ] Action Publisher for `Alerts.EHS.*` events
- [ ] FastAPI routes: `GET /ehs/dashboard`, `GET /ehs/forecast`, `GET /ehs/devices/health`, `POST /ehs/alerts/config`

### Part D — Shared Library (`backend/shared/`)
- [ ] `SmartCityObject` Pydantic model — the canonical data contract
- [ ] `RabbitMQConnection` helper (Singleton)
- [ ] `InfluxDBClient` wrapper (Singleton + Circuit Breaker)
- [ ] `CorrelationID` middleware for distributed tracing

---

## 6. Directory Structure

```
backend/
├── shared/
│   ├── __init__.py
│   ├── models.py              # SmartCityObject, shared Pydantic models
│   ├── rabbitmq.py            # Singleton RabbitMQ connection helper
│   ├── influxdb.py            # Singleton InfluxDB client + Circuit Breaker
│   └── tracing.py             # Correlation ID middleware
│
├── ingestion_gateway/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py            # SensorAdapter interface
│   │   ├── mqtt_adapter.py    # MQTT protocol adapter
│   │   ├── http_adapter.py    # HTTP REST adapter
│   │   └── coap_adapter.py    # CoAP protocol adapter (extensible)
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── base.py            # ValidationHandler chain base
│   │   ├── auth_validator.py
│   │   ├── rate_limiter.py
│   │   ├── format_validator.py
│   │   └── dedup_filter.py
│   ├── dispatcher.py
│   └── tests/
│       ├── test_adapters.py
│       ├── test_validators.py
│       └── test_dispatcher.py
│
├── semantic_middleware/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── factories/
│   │   ├── __init__.py
│   │   ├── base.py            # OntologyFactory interface
│   │   ├── ehs_factory.py
│   │   ├── energy_factory.py
│   │   └── cam_factory.py
│   ├── decorators/
│   │   ├── __init__.py
│   │   ├── base.py            # EnrichedReading decorator base
│   │   ├── location.py
│   │   ├── calibration.py
│   │   └── unit_conversion.py
│   ├── knowledge_graph.json
│   ├── translator.py
│   ├── publisher.py           # AMQP Publisher + Circuit Breaker
│   └── tests/
│       ├── test_factories.py
│       ├── test_decorators.py
│       ├── test_translator.py
│       └── test_publisher.py
│
└── ehs_engine/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── consumer.py
    ├── evaluator.py           # Observer Subject + threshold logic
    ├── strategies/
    │   ├── __init__.py
    │   ├── base.py            # WaterForecastStrategy interface
    │   ├── ph_linear.py
    │   └── turbidity_rf.py
    ├── device_health.py       # Real monitor
    ├── health_proxy.py        # CachedHealthProxy (Proxy Pattern)
    ├── tsdb_writer.py         # Circuit Breaker wrapped
    ├── action_publisher.py    # Observer implementation
    ├── routes.py
    ├── models.py
    ├── pretrained_models/
    │   └── water_quality_model.pkl
    └── tests/
        ├── test_evaluator.py
        ├── test_strategies.py
        ├── test_health_proxy.py
        ├── test_routes.py
        └── test_integration.py
```

---

## 7. Design Pattern Summary Table

| Pattern | Where Used | Purpose |
|:---|:---|:---|
| **Adapter** | Ingestion Gateway | Translate heterogeneous IoT protocols to unified format |
| **Chain of Responsibility** | Ingestion Validators | Sequential validation pipeline, easily extensible |
| **Abstract Factory** | Semantic Middleware | Produce domain-specific translator families |
| **Decorator** | Data Enrichment | Composable enrichment layers on sensor readings |
| **Strategy** | EHS ML Forecasting | Swap ML algorithms without changing evaluator |
| **Observer** | EHS Evaluator | Multi-subscriber threshold breach notification |
| **Proxy** | Device Health | Cache expensive 300-node heartbeat queries |
| **Singleton** | Connections | One RabbitMQ/InfluxDB instance per service |
| **Circuit Breaker** | TSDB Writer, Publisher | Graceful degradation on downstream failures |

---

## 8. Acceptance Criteria

- [ ] Adapter Pattern: new protocol added by creating one new class (no existing code modified)
- [ ] Chain of Responsibility: unauthorized node rejected at auth stage, never reaches dispatcher
- [ ] Abstract Factory: EHS, Energy, CAM factories produce correct translators
- [ ] Decorator: enrichments composable in any order
- [ ] Strategy: evaluator picks PHLinear for pH, TurbidityRF for turbidity
- [ ] Observer: threshold breach notifies AlertPublisher + TSDBWriter + DeviceHealth
- [ ] Proxy: cache serves 300-node health in < 10ms (vs ~500ms uncached)
- [ ] Circuit Breaker: InfluxDB failure → breaker opens → buffered data → auto-recovery
- [ ] DLQ: poison message routed to dead-letter after 3 retries
- [ ] End-to-end: MQTT payload → Ingestion → Middleware → RabbitMQ → EHS → InfluxDB ✓
