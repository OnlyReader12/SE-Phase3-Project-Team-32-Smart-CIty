# Member 3 — Alerting & Notification Subsystem + Data Privacy & Researcher Gateway

> **Role:** Alerting & Data Privacy Lead  
> **Scope:** End-to-end Alerting/Notification engine AND the Privacy Scrubbing Researcher API — two critical cross-cutting subsystems.

---

## 1. Feature Overview

### Feature A — Alerting & Notification Subsystem
A **FastAPI microservice** that:
- Subscribes to `Alerts.*` topics on RabbitMQ (published by EHS, Energy, and CAM engines)
- Formats emergency payloads into human-readable SMS/Email messages
- Dispatches via Twilio (SMS) and SendGrid (Email) external gateways
- Ensures residents WITHOUT smartphones still receive critical safety information (FR-U1)

### Feature B — Data Privacy & Researcher Gateway
A **FastAPI microservice** that:
- Exposes secure REST APIs for external researchers to query historical data
- Enforces the strict 30-day lookback window
- Strips all PII from datasets before transmission using Pandas
- Supports filtering by IoT node type (FR-R2)

### Functional Requirements Covered
| ID | Requirement |
|:---|:---|
| **FR-U1** | Real-time alerts via SMS/Email to users without smartphones |
| **FR-H2** | SMS/Email alerts for hazardous air or water (consumed from EHS Engine) |
| **FR-R1** | REST APIs for 30-day historical dataset query and export |
| **FR-R2** | Data filtering based on specific IoT node types |

---

## 2. Design Patterns & Architectural Rationale

### 2.1 Observer Pattern — Alert Subscription & Fan-Out
**Problem:** Multiple domain engines (EHS, Energy, CAM) independently publish alerts. The Alerting Engine must react to ALL of them without being tightly coupled to any specific engine.  
**Solution:** The Alerting Engine implements the **Observer Pattern** at the messaging level. RabbitMQ acts as the **Subject** (using a topic exchange), and the Alerting Engine is a **registered Observer** via wildcard binding `Alerts.*`.

```
[EHS Engine]    ──publishes──→  Alerts.EHS.AirQuality     ─┐
[EHS Engine]    ──publishes──→  Alerts.EHS.WaterQuality    ─┤
[Energy Engine] ──publishes──→  Alerts.Energy.SolarFailure ─┤ RabbitMQ Topic Exchange
[CAM Engine]    ──publishes──→  Alerts.CAM.Intrusion       ─┤     (Subject)
                                                            │
                    Alerting Engine (Observer) ◄─────────────┘
                    Binds to: Alerts.* (wildcard)
```

**Monolith Tradeoff:** In a monolith, domain engines would directly call `send_alert()`. Observer + RabbitMQ decouples the caller from delivery — the EHS Engine doesn't know or care whether alerts go via SMS, email, push notification, or all three.

### 2.2 Strategy Pattern — Notification Channel Selection
**Problem:** Different alert types need different delivery strategies: critical AQI alerts → SMS + Email; informational energy tips → Email only; intrusion → SMS + Push.  
**Solution:** Use the **Strategy Pattern** to encapsulate channel selection logic.

```
┌──────────────────────────────┐
│  NotificationStrategy        │ <<interface>>
│  + dispatch(alert, recipients)│
└──────────┬───────────────────┘
           │ implements
   ┌───────┴───────┬─────────────────┬──────────────────┐
   │               │                 │                  │
┌──▼──────┐  ┌─────▼──────┐  ┌──────▼──────┐  ┌───────▼───────┐
│SMSOnly  │  │EmailOnly   │  │SMSAndEmail  │  │BroadcastAll   │
│Strategy │  │Strategy    │  │Strategy     │  │Strategy       │
└─────────┘  └────────────┘  └─────────────┘  └───────────────┘
```

```python
class NotificationStrategy(ABC):
    @abstractmethod
    def dispatch(self, alert: FormattedAlert, recipients: List[Recipient]) -> DispatchResult: ...

class SMSAndEmailStrategy(NotificationStrategy):
    def __init__(self, twilio: TwilioClient, sendgrid: SendGridClient):
        self._twilio = twilio
        self._sendgrid = sendgrid
    
    def dispatch(self, alert, recipients):
        sms_results = [self._twilio.send(r.phone, alert.short_text) for r in recipients if r.phone]
        email_results = [self._sendgrid.send(r.email, alert.subject, alert.html_body) for r in recipients if r.email]
        return DispatchResult(sms=sms_results, email=email_results)
```

**Strategy selection based on severity:**
```python
STRATEGY_MAP = {
    Severity.CRITICAL: SMSAndEmailStrategy,   # e.g., AQI > 300
    Severity.WARNING: SMSAndEmailStrategy,    # e.g., AQI > 150
    Severity.INFO: EmailOnlyStrategy,          # e.g., weekly summary
    Severity.EMERGENCY: BroadcastAllStrategy,  # e.g., gas leak
}
```

### 2.3 Template Method Pattern — Message Formatting Pipeline
**Problem:** All alerts follow the same pipeline: parse → enrich → format → validate. But the formatting step varies drastically between SMS (160 chars) and HTML email (full template).  
**Solution:** Use the **Template Method Pattern** where the skeleton is fixed but `format()` varies.

```python
class AlertFormatter(ABC):
    def process(self, raw_alert: AlertPayload) -> FormattedAlert:  # Template
        parsed = self.parse(raw_alert)          # Step 1: always same
        enriched = self.enrich(parsed)           # Step 2: always same
        formatted = self.format(enriched)        # Step 3: VARIES
        validated = self.validate(formatted)      # Step 4: always same
        return validated
    
    @abstractmethod
    def format(self, enriched: EnrichedAlert) -> str: ...

class SMSFormatter(AlertFormatter):
    def format(self, enriched):
        return f"⚠️ {enriched.severity}: {enriched.summary[:120]} — SmartCity"

class EmailFormatter(AlertFormatter):
    def format(self, enriched):
        return self._jinja_env.get_template("email_alert.html").render(alert=enriched)
```

### 2.4 Facade Pattern — External Gateway Abstraction
**Problem:** Twilio and SendGrid have complex REST APIs with authentication, rate limiting, retry logic, and response parsing. Domain code shouldn't deal with these details.  
**Solution:** Use the **Facade Pattern** to expose simple `send_sms(phone, text)` and `send_email(to, subject, body)` interfaces that hide all API complexity.

```
┌─────────────────────────────────────────────────┐
│            NotificationFacade                    │
│  + send_sms(phone, text) → DeliveryStatus       │
│  + send_email(to, subject, body) → DeliveryStatus│
│  + check_health() → bool                        │
├─────────────────────────────────────────────────┤
│  Hides:                                         │
│  - Twilio auth token management                 │
│  - SendGrid API key rotation                    │
│  - Exponential backoff retry logic               │
│  - Rate limit tracking                          │
│  - Response status code parsing                 │
│  - Delivery receipt callbacks                   │
└─────────────────────────────────────────────────┘
```

### 2.5 Builder Pattern — Complex Alert Construction
**Problem:** An alert object has many optional fields (severity, zone, affected_nodes, readings, recommended_actions, escalation_level, expiry_time). Constructor telescoping is unreadable.  
**Solution:** Use the **Builder Pattern** for fluent alert construction.

```python
class AlertBuilder:
    def __init__(self, alert_type: str):
        self._alert = AlertPayload(type=alert_type)
    
    def with_severity(self, severity: Severity) -> 'AlertBuilder':
        self._alert.severity = severity
        return self
    
    def with_zone(self, zone: str) -> 'AlertBuilder':
        self._alert.zone = zone
        return self
    
    def with_readings(self, readings: dict) -> 'AlertBuilder':
        self._alert.readings = readings
        return self
    
    def with_expiry(self, minutes: int) -> 'AlertBuilder':
        self._alert.expiry = datetime.utcnow() + timedelta(minutes=minutes)
        return self
    
    def build(self) -> AlertPayload:
        self._validate()
        return self._alert

# Usage:
alert = (AlertBuilder("EHS.AirQuality")
    .with_severity(Severity.CRITICAL)
    .with_zone("Block_A")
    .with_readings({"aqi": 420, "pm25": 180})
    .with_expiry(60)
    .build())
```

### 2.6 Pipeline Pattern (Pipes & Filters) — PII Scrubbing (Privacy Gateway)
**Problem:** PII scrubbing requires multiple sequential transformations: column removal → k-anonymization → timestamp rounding → field masking. Each step must be independently testable and reorderable.  
**Solution:** Use the **Pipes & Filters Pattern** — each scrubbing step is a filter in a pipeline.

```
Raw DataFrame
  │
  ▼
[PII Column Remover] → removes resident_id, phone, email
  │
  ▼
[K-Anonymizer] → generalizes locations to block-level
  │
  ▼
[Timestamp Rounder] → rounds to nearest hour (prevents re-identification)
  │
  ▼
[Field Masker] → replaces MAC addresses with hashes
  │
  ▼
Clean DataFrame
```

```python
class ScrubFilter(ABC):
    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.DataFrame: ...

class PIIColumnRemover(ScrubFilter):
    PII_COLUMNS = ["resident_id", "user_name", "phone_number", "email", "ip_address"]
    def apply(self, df):
        return df.drop(columns=[c for c in self.PII_COLUMNS if c in df.columns])

class KAnonymizer(ScrubFilter):
    def apply(self, df):
        if "location" in df.columns:
            df["location"] = df["location"].apply(lambda x: x.split("_")[0] + "_Zone")
        return df

class ScrubPipeline:
    def __init__(self, filters: List[ScrubFilter]):
        self._filters = filters
    
    def execute(self, df: pd.DataFrame) -> pd.DataFrame:
        for f in self._filters:
            df = f.apply(df)
        return df
```

### 2.7 Proxy Pattern — Rate-Limited Researcher API
**Problem:** External researchers could flood the API with queries, overwhelming InfluxDB.  
**Solution:** Use a **Protection Proxy** that enforces rate limits per API key before forwarding to the real controller.

```python
class RateLimitedProxy:
    def __init__(self, real_controller: ResearcherController, max_per_hour: int = 100):
        self._real = real_controller
        self._counters: Dict[str, int] = defaultdict(int)
    
    def query(self, api_key: str, params: QueryParams):
        if self._counters[api_key] >= self._max_per_hour:
            raise RateLimitExceeded(api_key)
        self._counters[api_key] += 1
        return self._real.query(params)
```

### 2.8 Repository Pattern — Alert History Persistence
**Problem:** Alert history queries need to work against PostgreSQL today but might move to Elasticsearch for full-text search later.  
**Solution:** Use the **Repository Pattern** to abstract the data access layer.

```python
class AlertRepository(ABC):
    @abstractmethod
    def save(self, alert: AlertHistoryRecord) -> str: ...
    @abstractmethod
    def find_by_id(self, alert_id: str) -> AlertHistoryRecord: ...
    @abstractmethod
    def find_by_zone(self, zone: str, limit: int) -> List[AlertHistoryRecord]: ...

class PostgresAlertRepository(AlertRepository):
    def save(self, alert):
        # SQLAlchemy INSERT into alert_history table
        ...

class ElasticsearchAlertRepository(AlertRepository):  # Future
    def save(self, alert):
        # Elasticsearch index document
        ...
```

---

## 3. Microservices Architecture Patterns

### 3.1 Event-Driven Architecture (EDA) — Pure Reactive Consumer
The Alerting Engine is a **pure event-driven service**:
- No polling, no cron jobs — it **wakes up only when RabbitMQ pushes** an `Alerts.*` event
- This is the purest form of reactive microservice — zero CPU usage when no alerts exist
- Contrast with a monolith where the alert module would be loaded in memory even when idle

### 3.2 Retry with Exponential Backoff — External Gateway Resilience
Twilio and SendGrid are external services that can fail temporarily:
```python
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(ExternalGatewayError)
)
def send_sms(phone: str, message: str):
    response = twilio_client.messages.create(to=phone, body=message)
    if response.status_code >= 500:
        raise ExternalGatewayError("Twilio 5xx")
```

### 3.3 Circuit Breaker — Gateway Health
Wrap Twilio and SendGrid in separate Circuit Breakers:
- If Twilio is down → open circuit → fallback to **Email-only mode** (graceful degradation)
- If SendGrid is down → open circuit → fallback to **SMS-only mode**
- If BOTH are down → buffer alerts in PostgreSQL → retry when circuits close

```python
twilio_breaker = CircuitBreaker(fail_max=3, reset_timeout=60)
sendgrid_breaker = CircuitBreaker(fail_max=3, reset_timeout=60)

def dispatch_alert(alert, recipients):
    try:
        twilio_breaker.call(send_sms, alert.short_text, recipients)
    except CircuitBreakerError:
        logger.warn("Twilio circuit OPEN — falling back to email-only")
    
    try:
        sendgrid_breaker.call(send_email, alert.html_body, recipients)
    except CircuitBreakerError:
        logger.warn("SendGrid circuit OPEN — buffering alert")
        buffer_for_retry(alert)
```

### 3.4 Outbox Pattern — Guaranteed Alert Delivery
**Problem:** After persisting an alert to PostgreSQL AND dispatching via Twilio, a crash between the two operations could lose the dispatch.  
**Solution:** Implement the **Transactional Outbox Pattern**:
1. Write alert AND delivery intent to PostgreSQL in a single transaction
2. A background worker polls the outbox table and dispatches pending alerts
3. Mark as "dispatched" only after Twilio/SendGrid confirm delivery

```
┌─────────────────────────────────────────┐
│ PostgreSQL Transaction                  │
│  1. INSERT INTO alert_history (...)     │
│  2. INSERT INTO alert_outbox (...)      │ ← delivery intent
│  COMMIT                                 │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Outbox Poller (Background Worker)       │
│  SELECT * FROM alert_outbox             │
│    WHERE dispatched = false             │
│  → dispatch via Twilio/SendGrid         │
│  → UPDATE alert_outbox SET dispatched=T │
└─────────────────────────────────────────┘
```

### 3.5 API Gateway Pattern — Researcher Authentication
The Privacy Gateway implements its own **lightweight API Gateway** for researchers:
- API Key validation
- Rate limiting (per-key sliding window)
- Request logging for compliance audit
- This is separate from the main RBAC gateway (Member 4) because researchers are external users with different auth patterns

### 3.6 Data Mesh Principle — Domain Data Ownership
The Privacy Gateway does NOT own any sensor data. It is a **read-only consumer** of InfluxDB data owned by the domain engines. It adds a **data product** layer:
- Schema documentation via `/research/schema`
- Quality guarantees (PII-free certification)
- Access controls (API keys + rate limits)
- This follows the Data Mesh principle of treating data-as-a-product.

---

## 4. Monolith vs Microservice Tradeoffs

### Why Separate Alerting and Privacy Services?
| Aspect | Monolith | Our Approach |
|:---|:---|:---|
| **Availability** | Alert module down = privacy API down | Each runs independently |
| **Scaling** | Can't scale alerting during emergencies | Scale alerting horizontally during AQI spikes |
| **Security** | Researcher API has access to alert internals | Researcher API can ONLY read InfluxDB — no access to Twilio keys |
| **Compliance** | PII scrubbing logic mixed with SMS code | Privacy Gateway is auditable in isolation |
| **Team Ownership** | Merge conflicts between alert and privacy code | Member 3 owns two clear, independent directories |

### What We Sacrifice
| Concern | Cost |
|:---|:---|
| **Shared State** | Alert history in PostgreSQL is accessed by both Alerting and RBAC Gateway — shared DB anti-pattern |
| **Deployment** | Two separate services to deploy, monitor, and maintain |
| **Code Duplication** | Both services have their own `config.py`, PostgreSQL connection setup |
| **Testing Complexity** | Integration tests require RabbitMQ + PostgreSQL + InfluxDB all running |
| **Network Calls** | Researcher queries go: Flutter → API Gateway → Privacy Gateway → InfluxDB (3 network hops vs 1 in monolith) |

### Mitigation
- **Shared DB:** Acceptable because Alerting writes and Privacy reads — no contention. Future: split into separate DBs
- **Shared Library:** Use `backend/shared/` for common connection helpers
- **Docker Compose:** Both services start together with health checks
- **Correlation IDs:** Trace researcher queries end-to-end

---

## 5. Deliverables

### Part A — Alerting & Notification Engine (`backend/alerting_engine/`)

- [ ] `subscriber.py` — RabbitMQ consumer bound to `Alerts.*` (**Observer Pattern**)
- [ ] `formatter.py` — Abstract `AlertFormatter` with `SMSFormatter` and `EmailFormatter` (**Template Method**)
- [ ] `strategies/` — `NotificationStrategy` with `SMSOnly`, `EmailOnly`, `SMSAndEmail`, `BroadcastAll` (**Strategy Pattern**)
- [ ] `alert_builder.py` — Fluent `AlertBuilder` for complex alert construction (**Builder Pattern**)
- [ ] `facade.py` — `NotificationFacade` hiding Twilio/SendGrid complexity (**Facade Pattern**)
- [ ] `twilio_client.py` — Twilio REST adapter with retry + circuit breaker
- [ ] `sendgrid_client.py` — SendGrid REST adapter with retry + circuit breaker
- [ ] `resolver.py` — Recipient lookup from PostgreSQL (by zone, preferences)
- [ ] `repository.py` — `AlertRepository` interface + `PostgresAlertRepository` (**Repository Pattern**)
- [ ] `outbox.py` — Transactional outbox worker for guaranteed delivery (**Outbox Pattern**)
- [ ] `routes.py` — Alert history API endpoints
- [ ] `templates/` — Jinja2 SMS and HTML email templates

### Part B — Data Privacy & Researcher Gateway (`backend/privacy_gateway/`)

- [ ] `api_controller.py` — FastAPI REST endpoints for researchers
- [ ] `query_validator.py` — 30-day time-bound enforcement
- [ ] `influxdb_reader.py` — Safe read-only InfluxDB DAO
- [ ] `scrubber/` — **Pipes & Filters** pipeline:
  - `pipeline.py` — `ScrubPipeline` orchestrator
  - `pii_remover.py` — Column removal filter
  - `k_anonymizer.py` — Location generalization filter
  - `timestamp_rounder.py` — Temporal rounding filter
  - `field_masker.py` — MAC/IP hash masking filter
- [ ] `rate_limiter.py` — `RateLimitedProxy` per API key (**Proxy Pattern**)
- [ ] `auth.py` — API key validation against PostgreSQL
- [ ] `routes.py` — Research data endpoints

---

## 6. Directory Structure

```
backend/
├── alerting_engine/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── subscriber.py           # RabbitMQ Observer consumer
│   ├── formatter.py            # Template Method: SMS + Email formatters
│   ├── alert_builder.py        # Builder Pattern
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py             # NotificationStrategy interface
│   │   ├── sms_only.py
│   │   ├── email_only.py
│   │   ├── sms_and_email.py
│   │   └── broadcast_all.py
│   ├── facade.py               # NotificationFacade
│   ├── twilio_client.py        # Retry + Circuit Breaker
│   ├── sendgrid_client.py      # Retry + Circuit Breaker
│   ├── resolver.py             # Recipient resolution
│   ├── repository.py           # Repository Pattern (PostgreSQL)
│   ├── outbox.py               # Transactional Outbox worker
│   ├── routes.py
│   ├── models.py
│   ├── templates/
│   │   ├── sms_alert.txt
│   │   └── email_alert.html
│   └── tests/
│       ├── test_formatter.py
│       ├── test_strategies.py
│       ├── test_builder.py
│       ├── test_facade.py
│       ├── test_repository.py
│       ├── test_outbox.py
│       └── test_integration.py
│
└── privacy_gateway/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── api_controller.py
    ├── query_validator.py
    ├── influxdb_reader.py
    ├── rate_limiter.py          # Proxy Pattern
    ├── auth.py
    ├── scrubber/
    │   ├── __init__.py
    │   ├── pipeline.py          # Pipes & Filters orchestrator
    │   ├── pii_remover.py       # Filter 1
    │   ├── k_anonymizer.py      # Filter 2
    │   ├── timestamp_rounder.py # Filter 3
    │   └── field_masker.py      # Filter 4
    ├── routes.py
    ├── models.py
    └── tests/
        ├── test_query_validator.py
        ├── test_scrubber_pipeline.py
        ├── test_rate_limiter.py
        ├── test_auth.py
        └── test_integration.py
```

---

## 7. Design Pattern Summary Table

| Pattern | Where Used | Purpose |
|:---|:---|:---|
| **Observer** | Alert Subscriber | React to events from ANY domain engine via wildcard binding |
| **Strategy** | Notification Channel | Swap SMS/Email/Both based on severity level |
| **Template Method** | Alert Formatter | Fixed pipeline with variable format step (SMS vs HTML) |
| **Builder** | Alert Construction | Fluent construction of complex alert objects |
| **Facade** | Gateway Clients | Hide Twilio/SendGrid API complexity behind simple interface |
| **Repository** | Alert History | Abstract PostgreSQL persistence; swappable to Elasticsearch |
| **Pipes & Filters** | PII Scrubbing | Composable, testable, reorderable scrubbing steps |
| **Proxy** | Rate Limiter | Protect real controller with per-key rate enforcement |
| **Circuit Breaker** | Twilio/SendGrid | Graceful degradation when external gateways fail |
| **Outbox** | Alert Dispatch | Guaranteed delivery via transactional outbox pattern |

---

## 8. Acceptance Criteria

### Alerting Engine
- [ ] Observer: receives alerts from EHS, Energy, and CAM via `Alerts.*` wildcard
- [ ] Strategy: CRITICAL alerts use SMS+Email; INFO alerts use Email-only
- [ ] Template Method: SMS format ≤ 160 chars; Email uses HTML template
- [ ] Builder: constructs valid alert with severity, zone, readings, expiry
- [ ] Facade: `send_sms()` and `send_email()` work with Twilio/SendGrid sandbox
- [ ] Repository: alert history persisted and queryable via API
- [ ] Circuit Breaker: Twilio down → fallback to email-only mode
- [ ] Outbox: crash between persist and dispatch → outbox worker retries

### Privacy Gateway
- [ ] Pipeline: all 4 scrubbing filters applied in sequence
- [ ] PII Remover: `resident_id`, `phone`, `email` columns completely absent from output
- [ ] K-Anonymizer: location generalized to zone-level
- [ ] Proxy: 101st request from same API key returns 429 Too Many Requests
- [ ] Validator: query for 31-day-old data returns 400 Bad Request
- [ ] CSV export: anonymized data downloadable as clean CSV
- [ ] All unit & integration tests pass
