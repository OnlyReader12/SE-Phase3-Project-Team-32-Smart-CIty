# Member 1 — Energy Management Engine (Core Feature)

> **Role:** Energy Domain Lead  
> **Scope:** End-to-end implementation of the Energy Management Engine — from sensor data consumption to ML forecasting, automated lamppost control, and dashboard API exposure.

---

## 1. Feature Overview

The Energy Management Engine is a **FastAPI microservice plugin** that operates as an isolated domain service within the Microkernel (Plug-in) Architecture. It:
- Consumes standardized `Energy.*` topic events from RabbitMQ
- Evaluates real-time solar generation vs AC load consumption
- Runs ready-made ML models to forecast future energy usage
- Automates smart lamppost on/off scheduling
- Publishes action commands back to RabbitMQ for physical device control
- Persists all telemetry and predictions to InfluxDB

### Functional Requirements Covered
| ID | Requirement |
|:---|:---|
| **FR-E1** | Real-time dashboards for solar power generation and AC energy consumption |
| **FR-E2** | Energy savings recommendations based on historical usage patterns |
| **FR-E3** | Configure automated on/off timings for campus smart lamp posts |
| **FR-E4** | Maintenance dashboard for health status of solar devices and AC IoT nodes |
| **FR-E5** | Ready-made models to forecast future energy consumption |

---

## 2. Design Patterns & Architectural Rationale

### 2.1 Strategy Pattern — ML Model Selection
**Problem:** Different energy forecasting scenarios need different ML models (linear regression for short-term, LSTM for long-term, seasonal decomposition for weekly patterns).  
**Solution:** Use the **Strategy Pattern** to encapsulate each ML algorithm behind a common `ForecastStrategy` interface. The Evaluator dynamically selects the correct strategy at runtime based on the forecast horizon requested.

```
┌────────────────────────┐
│   ForecastStrategy     │ <<interface>>
│  + predict(data) → []  │
└────────┬───────────────┘
         │ implements
   ┌─────┴──────┬──────────────────┐
   │            │                  │
┌──▼───┐  ┌────▼─────┐  ┌─────────▼──────┐
│Linear│  │RandomFor.│  │SeasonalDecomp. │
│Strat.│  │Strategy  │  │Strategy        │
└──────┘  └──────────┘  └────────────────┘
```

**Why not just if-else?** The Strategy Pattern obeys the **Open/Closed Principle** — adding a new model (e.g., a neural net) requires only a new class, never modifying the evaluator core.

### 2.2 Observer Pattern — Event-Driven Threshold Monitoring
**Problem:** When the solar panel output drops below critical, multiple subsystems must react (alert engine, dashboard, lamppost scheduler).  
**Solution:** Implement the **Observer Pattern**. The `EnergyEvaluator` is the **Subject**. When a threshold breach occurs, it notifies all registered **Observers** — the Action Publisher (alerts), the TSDB Writer (logging), and the Lamppost Scheduler (emergency shutdown).

```
Subject (EnergyEvaluator)
  │── notify_all(event)
  │
  ├── Observer: ActionPublisher.on_threshold_breach()
  ├── Observer: TSDBWriter.on_threshold_breach()
  └── Observer: LamppostScheduler.on_threshold_breach()
```

**Monolith Tradeoff:** In a monolith, you'd use direct function calls. Here, observers decouple components — if one observer fails, others still execute. This trades simplicity for resilience.

### 2.3 Template Method Pattern — Telemetry Processing Pipeline
**Problem:** All sensor readings (solar, AC, lamppost) follow a similar pipeline: validate → enrich → evaluate → persist. But each sensor type has unique evaluation logic.  
**Solution:** Use the **Template Method Pattern** where an abstract `TelemetryProcessor` defines the skeleton pipeline, and concrete subclasses (`SolarProcessor`, `ACLoadProcessor`, `LamppostProcessor`) override only the `evaluate()` step.

```python
class TelemetryProcessor(ABC):         # Template
    def process(self, reading):        # Invariant skeleton
        validated = self.validate(reading)
        enriched = self.enrich(validated)
        result = self.evaluate(enriched)  # Varies per subclass
        self.persist(result)
        return result

class SolarProcessor(TelemetryProcessor):
    def evaluate(self, data):          # Concrete step
        # Solar-specific threshold checks
```

### 2.4 Factory Pattern — Processor Instantiation
**Problem:** When an `Energy.*` event arrives, the system must create the correct processor (Solar, AC, Lamppost) based on the `sensorType` field.  
**Solution:** Use a **Simple Factory** that maps sensor types to processor classes.

```python
class ProcessorFactory:
    _registry = {
        "solar": SolarProcessor,
        "ac_load": ACLoadProcessor,
        "lamppost": LamppostProcessor,
    }
    
    @staticmethod
    def create(sensor_type: str) -> TelemetryProcessor:
        return ProcessorFactory._registry[sensor_type]()
```

### 2.5 Command Pattern — Lamppost Automation
**Problem:** Lamppost control actions (ON, OFF, DIM, SCHEDULE) need to be queued, logged, undone, and replayed.  
**Solution:** Use the **Command Pattern** where each action is encapsulated as a command object with `execute()` and `undo()` methods. Commands are serialized to RabbitMQ and logged to PostgreSQL.

```
┌──────────────┐
│  LampCommand │ <<interface>>
│  + execute() │
│  + undo()    │
└──────┬───────┘
  ┌────┴──────┬──────────────┐
  │           │              │
┌─▼──┐  ┌────▼────┐  ┌──────▼─────┐
│ ON │  │  OFF    │  │ SCHEDULE   │
│Cmd │  │  Cmd    │  │ Cmd        │
└────┘  └─────────┘  └────────────┘
```

### 2.6 Singleton Pattern — Configuration Manager
**Problem:** Database connections, RabbitMQ channels, and ML model instances are expensive to create.  
**Solution:** Use the **Singleton Pattern** for `ConfigManager`, `RabbitMQConnection`, and `ModelLoader` to ensure one shared instance across the engine.

---

## 3. Microservices Architecture Patterns

### 3.1 Event-Driven Architecture (EDA)
The Energy Engine is a **pure event consumer**. It does NOT expose synchronous endpoints to other engines. Instead:
- **Inbound:** RabbitMQ delivers `Energy.*` events asynchronously
- **Outbound:** Publishes `Alerts.Energy.*` and `Energy.Lamppost.*` action events
- **Benefit:** Complete temporal decoupling — the engine can be restarted without losing events (RabbitMQ persists unacknowledged messages)

### 3.2 CQRS (Command Query Responsibility Segregation)
- **Command Side:** `POST /energy/lamppost/schedule` writes to PostgreSQL (commands)
- **Query Side:** `GET /energy/dashboard` reads from InfluxDB (queries)
- **Separation:** Write-optimized store (PostgreSQL) vs read-optimized store (InfluxDB TSDB) — each tuned for its workload

### 3.3 Circuit Breaker Pattern
**Problem:** If InfluxDB goes down, the energy engine shouldn't crash.  
**Solution:** Wrap InfluxDB and RabbitMQ calls in a **Circuit Breaker** (using `pybreaker` library).
- **CLOSED** state: Normal operation
- **OPEN** state: After 5 consecutive failures, stop calling InfluxDB, buffer data in memory, return cached data to dashboards
- **HALF-OPEN** state: Periodically test if InfluxDB is back

```python
import pybreaker
influx_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)

@influx_breaker
def write_telemetry(data):
    influx_client.write(data)
```

### 3.4 Bulkhead Pattern — Resource Isolation
**Problem:** A flood of solar sensor data shouldn't exhaust the thread pool used for lamppost control.  
**Solution:** Assign separate **thread pools** (bulkheads):
- Pool A (8 threads): Telemetry ingestion & TSDB writes
- Pool B (4 threads): ML forecast computation
- Pool C (2 threads): Lamppost command execution

### 3.5 Saga Pattern — Multi-Step Lamppost Scheduling
When a manager creates a new lamppost schedule:
1. Validate schedule → 2. Persist to PostgreSQL → 3. Publish to RabbitMQ → 4. Confirm via API
If step 3 fails, the **compensating transaction** rolls back step 2 (delete the schedule row).

---

## 4. Monolith vs Microservice Tradeoffs

### Why NOT a Monolith?
| Aspect | Monolith Approach | Our Microservice Approach |
|:---|:---|:---|
| **Fault Isolation** | If ML forecast crashes (OOM), entire dashboard goes down | Energy Engine crashes → EHS, CAM engines unaffected |
| **Deployment** | Redeploy ALL features for a lamppost fix | Redeploy only `energy_engine` container |
| **Scaling** | Scale entire app if forecast is slow | Scale only the ML forecast worker horizontally |
| **Team Ownership** | One codebase = merge conflicts | Member 1 owns `energy_engine/` independently |

### What We Sacrifice (Honest Tradeoffs)
| Concern | Cost |
|:---|:---|
| **Network Latency** | Inter-service calls via RabbitMQ add ~5-15ms vs in-process function calls (~0.01ms) |
| **Data Consistency** | No ACID transactions across engines — we use eventual consistency |
| **Operational Complexity** | Must monitor RabbitMQ queues, dead-letter exchanges, and circuit breaker states |
| **Debugging Difficulty** | Distributed tracing needed (correlation IDs in every event) — harder than a single stack trace |
| **Duplication** | Each engine has its own `config.py`, `models.py` — some boilerplate is repeated |

### Hybrid Decision
We adopt a **Microkernel (Plug-in)** model — a **middle ground** between monolith and full microservices. The central RabbitMQ bus acts as the kernel, and each engine is a plug-in. This gives us:
- Monolith-like simplicity in deployment (Docker Compose, not Kubernetes)
- Microservice-like isolation (each engine is a separate process)
- Avoids the full network mesh complexity of pure microservices

---

## 5. Deliverables

### 5.1 Backend — `backend/energy_engine/`

#### A. AMQP Consumer (`consumer.py`) — *uses Observer Pattern internally*
- [ ] Connect to RabbitMQ using `pika` library
- [ ] Bind to exchange with routing key `Energy.*`
- [ ] Deserialize incoming OneM2M `SmartCityObject` JSON payloads
- [ ] Route to correct processor via **Factory Pattern**

#### B. Engine Evaluator (`evaluator.py`) — *uses Template Method + Observer*
- [ ] Abstract `TelemetryProcessor` base class with template pipeline
- [ ] `SolarProcessor` — threshold checks for voltage/current
- [ ] `ACLoadProcessor` — threshold checks for power draw
- [ ] `LamppostProcessor` — status monitoring
- [ ] Observer notifications on threshold breach

#### C. ML Forecast Module (`ml_forecast.py`) — *uses Strategy Pattern*
- [ ] `ForecastStrategy` interface with `predict(data) → ForecastResult`
- [ ] `LinearRegressionStrategy` — short-term (1-6 hour)
- [ ] `RandomForestStrategy` — medium-term (6-24 hour)
- [ ] `SeasonalDecompStrategy` — weekly pattern analysis
- [ ] `StrategySelector` — picks strategy based on horizon parameter
- [ ] Circuit breaker wrapping model inference

#### D. Lamppost Automation (`lamppost_scheduler.py`) — *uses Command Pattern*
- [ ] `LampCommand` interface with `execute()` and `undo()`
- [ ] `TurnOnCommand`, `TurnOffCommand`, `ScheduleCommand` implementations
- [ ] `CommandInvoker` — executes and logs commands
- [ ] `APScheduler` integration for time-based triggers
- [ ] Saga: rollback schedule on RabbitMQ publish failure

#### E. TSDB Synchronizer (`tsdb_writer.py`) — *uses Circuit Breaker*
- [ ] Batch telemetry data points with configurable flush intervals
- [ ] Circuit breaker wrapper for InfluxDB writes
- [ ] In-memory buffer during OPEN circuit state
- [ ] Write to `energy_telemetry` and `energy_predictions` measurements

#### F. Action Publisher (`action_publisher.py`) — *implements Observer interface*
- [ ] Publish lamppost control commands to `Energy.Lamppost.*`
- [ ] Publish `Alerts.Energy.*` emergency events
- [ ] Include correlation IDs for distributed tracing

#### G. FastAPI Routes (`routes.py`) — *CQRS separation*
- [ ] `GET /energy/dashboard` — Query side (reads from InfluxDB)
- [ ] `GET /energy/forecast` — Query side (invokes Strategy Pattern)
- [ ] `GET /energy/recommendations` — Query side
- [ ] `GET /energy/devices/health` — Query side
- [ ] `POST /energy/lamppost/schedule` — Command side (writes to PostgreSQL)
- [ ] `POST /energy/lamppost/override` — Command side (publishes Command)

### 5.2 Data Models — `models.py`
- [ ] `EnergyTelemetry` — Pydantic model for solar/AC sensor readings
- [ ] `EnergyForecast` — Pydantic model for ML prediction output
- [ ] `LamppostSchedule` — Pydantic model for scheduling config
- [ ] `LampCommand` — Command pattern base
- [ ] `DeviceHealthStatus` — Device health with heartbeat
- [ ] `ThresholdBreachEvent` — Observer notification payload

### 5.3 Database Schema
- [ ] InfluxDB: `energy_telemetry` (solar_watts, ac_load_watts, node_id, block)
- [ ] InfluxDB: `energy_predictions` (predicted_watts, confidence, horizon_h, strategy_used)
- [ ] PostgreSQL: `lamppost_schedules` (id, node_id, on_time, off_time, override_flag, created_by)
- [ ] PostgreSQL: `lamppost_command_log` (id, command_type, node_id, executed_at, undone, correlation_id)

### 5.4 Tests
- [ ] Unit test for each Strategy implementation (mock data in → prediction out)
- [ ] Unit test for Template Method processors
- [ ] Unit test for Factory creates correct processor
- [ ] Unit test for Command execute + undo
- [ ] Unit test for Observer notification chain
- [ ] Integration test: Circuit breaker opens after 5 InfluxDB failures
- [ ] Integration test: Publish mock `Energy.*` event → verify pipeline end-to-end
- [ ] API endpoint tests with `pytest` + `httpx`

---

## 6. Directory Structure

```
backend/
└── energy_engine/
    ├── __init__.py
    ├── main.py                  # FastAPI app factory (Singleton config)
    ├── config.py                # Singleton ConfigManager
    ├── consumer.py              # RabbitMQ AMQP consumer + Factory routing
    ├── evaluator.py             # Template Method processors + Observer subject
    ├── strategies/
    │   ├── __init__.py
    │   ├── base.py              # ForecastStrategy interface
    │   ├── linear.py            # LinearRegressionStrategy
    │   ├── random_forest.py     # RandomForestStrategy
    │   └── seasonal.py          # SeasonalDecompStrategy
    ├── commands/
    │   ├── __init__.py
    │   ├── base.py              # LampCommand interface
    │   ├── turn_on.py
    │   ├── turn_off.py
    │   └── schedule.py
    ├── lamppost_scheduler.py    # CommandInvoker + APScheduler
    ├── tsdb_writer.py           # InfluxDB writer + Circuit Breaker
    ├── action_publisher.py      # RabbitMQ publisher (Observer)
    ├── routes.py                # FastAPI REST endpoints (CQRS)
    ├── models.py                # Pydantic data models
    ├── circuit_breaker.py       # pybreaker configuration
    ├── pretrained_models/
    │   └── energy_model.pkl
    └── tests/
        ├── test_evaluator.py
        ├── test_strategies.py
        ├── test_commands.py
        ├── test_circuit_breaker.py
        ├── test_routes.py
        └── test_integration.py
```

---

## 7. Integration Points

| System | Direction | Protocol | Pattern |
|:---|:---|:---|:---|
| **RabbitMQ** | Inbound | AMQP Sub | Event-Driven (EDA) |
| **RabbitMQ** | Outbound | AMQP Pub | Observer publishes alerts/commands |
| **InfluxDB** | Outbound | TCP | Circuit Breaker wrapped writes |
| **PostgreSQL** | Read/Write | psycopg2 | CQRS command side |
| **Alerting Engine** *(M3)* | Indirect | Via RabbitMQ | Your alerts → their SMS/Email |
| **RBAC Gateway** *(M4)* | Serves | HTTPS | Gateway forwards authenticated requests |

---

## 8. Acceptance Criteria

- [ ] Engine starts, connects to RabbitMQ, and consumes `Energy.*` events
- [ ] Factory correctly routes solar/AC/lamppost readings to proper processors
- [ ] Each Strategy produces valid forecasts for its horizon
- [ ] Command Pattern logs all lamppost actions and supports undo
- [ ] Circuit breaker opens after 5 InfluxDB failures, recovers on HALF-OPEN
- [ ] Observer chain notifies all subscribers on threshold breach
- [ ] CQRS: writes go to PostgreSQL, reads come from InfluxDB
- [ ] All design pattern unit tests pass
- [ ] End-to-end integration test passes
