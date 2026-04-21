# Smart City Living Lab — Project 3 Reference

**Team 32 | SE Phase 3 | Campus IoT System (300 Nodes)**

---

## Architecture: Microkernel (Plug-in)

**Core = RabbitMQ** (message bus/kernel). Each domain engine is an isolated plug-in container.  
Chosen over: Monolith (no fault isolation) and Full Microservices (too complex for a lab).

```
IoT Sensors → Ingestion Engine → RabbitMQ → Domain Engines → InfluxDB
                  (Sandeep)      (Kernel)   (EHS/Energy/CAM)  (TSDB)
                                    ↓
                              Alerting Engine → Twilio/SendGrid
                                (Bharat)
```

---

## Team Members & Modules

| Member | Module | Port | Key Pattern | Pub/Sub |
|---|---|---|---|---|
| **Sandeep (M1)** | IoT Ingestion Engine | 8000 | Adapter | Publisher: `telemetry.*` |
| **Saicharan (M2)** | EHS Domain Engine | 8002 | Strategy + Factory | Sub: `telemetry.enviro.#` → Pub: `alerts.critical` |
| **Raghuram (M3)** | Energy Domain Engine | 8003 | Command | Sub: `telemetry.power.*` |
| **Bharat (M4)** | Alerting Subsystem | 8004 | Chain of Responsibility | Sub: `alerts.*` |
| **Nikhil (M5)** | Privacy + RBAC API | 8005 | Strategy + Builder/Factory | HTTP (Flutter UI, Researchers) |

---

## Design Patterns (Quick Ref)

| Pattern | Where Used | Why |
|---|---|---|
| **Adapter** | M1 — IoT Ingestion | Translates MQTT/CoAP/HTTP → `SmartCityObject` |
| **Observer** | All engines via RabbitMQ | Decoupled pub/sub; engines subscribe to only their topics |
| **Strategy** | M2 (EHS ML), M5 (PII scrubbing) | Swap algorithms via config, zero code changes |
| **Factory Method** | M2 (evaluators), M5 (dashboard) | Creates correct object per metric/role |
| **Command** | M3 — Energy/lamppost control | Queue-able, reversible hardware commands |
| **Chain of Responsibility** | M4 — Alerting | Routes alerts by severity without if-else trees |
| **Builder** | M5 — Dashboard assembly | Builds role-based UI dynamically from RBAC DB |

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| **Backend** | Python + FastAPI | ML-native (sklearn/TF), async, fast |
| **Message Broker** | RabbitMQ | MQTT support for battery sensors, topic routing |
| **Telemetry DB** | InfluxDB | High-write TSDB, 30-day auto-retention |
| **Relational DB** | PostgreSQL | RBAC, user accounts, configs |
| **Frontend** | Flutter (Web + Mobile) | Single codebase for admin dashboard + resident app |
| **Alerts** | Twilio (SMS) + SendGrid (Email) | Offline user coverage, reliable delivery |
| **IoT Middleware** | Eclipse OM2M (OneM2M) | Standardises 300 heterogeneous sensor protocols |
| **PII Scrubbing** | Pandas | Strips PII in-memory before researcher API response |

---

## Monolith vs Microservices vs Microkernel

| | Monolith | Full Microservices | **Microkernel (Ours)** |
|---|---|---|---|
| Fault Isolation | ❌ One crash = all down | ✅ | ✅ |
| Complexity | Low | Very High (K8s etc.) | **Medium** |
| ML Integration | Easy | Hard | **Easy** |
| Team Independence | ❌ | ✅ | **✅ via RabbitMQ** |

---

## ADRs Summary

| ADR | Decision | Alternatives Rejected |
|---|---|---|
| ADR-001 | Microkernel Architecture | Monolith, Full Microservices |
| ADR-002 | OneM2M Semantic Middleware | Custom per-sensor wrappers |
| ADR-003 | Edge Processing for Auth (<1s) | Cloud processing, local server |
| ADR-004 | FastAPI for domain engines | Node.js, Django |
| ADR-005 | Flutter unified UI | Separate web/mobile codebases |
| ADR-006 | RabbitMQ as message broker | Direct HTTP, Apache Kafka |
| ADR-007 | InfluxDB for telemetry | PostgreSQL, MongoDB |
| ADR-008 | PostgreSQL for RBAC | NoSQL, in-memory |
| ADR-009 | Decoupled PII scrubbing layer | DB triggers, human trust |
| ADR-010 | Twilio + SendGrid gateways | Custom SMTP/GSM modem |

---

## M2 (Saicharan) — EHS Engine Quick Ref

**Location:** `core_modules/EHSEngine/`

```
EHSEngine/
├── main.py                     ← FastAPI app, port 8002
├── config.yaml                 ← Swap ML: ml_strategy: "scikit"|"tensorflow"
├── consumer/amqp_consumer.py   ← Observer: listens telemetry.enviro.#
├── evaluator/
│   ├── engine_evaluator.py     ← Core logic: orchestrates all patterns
│   ├── threshold_evaluator.py  ← AQIThresholdEvaluator, WaterPhEvaluator
│   └── evaluator_factory.py    ← Factory Method: creates right evaluator
├── ml/
│   ├── predictor_strategy.py   ← Abstract Strategy interface
│   ├── scikit_predictor.py     ← Concrete: Scikit-learn (DEFAULT)
│   └── tensorflow_predictor.py ← Concrete: TensorFlow LSTM
├── persistence/influx_writer.py ← Writes to InfluxDB (dry-run if offline)
├── publisher/alert_publisher.py ← Publishes to alerts.critical (NEVER Twilio)
└── models/schemas.py            ← Pydantic: EHSTelemetry, AlertPayload, etc.
```

**Run:** `cd core_modules/EHSEngine && pip install -r requirements.txt && python main.py`  
**Test (no RabbitMQ needed):** `POST http://localhost:8002/evaluate` with EHSTelemetry JSON  
**Docs:** `http://localhost:8002/docs`

**Requirements satisfied:** FR-H1, FR-H2, FR-H3, FR-H4

---

## Existing Core Modules (Pre-built)

- `core_modules/IngestionEngine/` — M1's Adapter engine (port 8000)
- `core_modules/PersistentMiddleware/` — Semantic middleware (port 8001)  
- `IOTDataGenerator/iot_generator.py` — Simulates 300 EHS + Energy nodes

---

## C4 Diagrams

| Level | File | Shows |
|---|---|---|
| C1 | `C4_Diagrams/C1/C1.png` | System Context |
| C2 | `C4_Diagrams/C2/C2.png` | Container Architecture |
| C3 | `C4_Diagrams/C3/3-Domain_Engines/DomainEngines.png` | EHS/Energy/CAM internals |

---

*Generated: 2026-04-21 | Conversation: 0563ed97*
