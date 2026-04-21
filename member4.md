# Member 4 — RBAC & API Gateway + Database Infrastructure

> **Role:** Security, Access Control & Infrastructure Lead  
> **Scope:** End-to-end Role-Based Access Control system, central API Gateway, JWT authentication, PostgreSQL schema design, and the shared database infrastructure that ALL services depend on.

---

## 1. Feature Overview

The RBAC & API Gateway subsystem is the **security backbone** of the Smart City platform:
- Central API Gateway that intercepts ALL frontend requests
- JWT-based stateless authentication
- Role-Based Access Control enforcing that each stakeholder sees only their permitted data
- PostgreSQL schema design for users, roles, permissions, and system configuration
- Tailored dashboard data aggregation per user role (Management, Serviceability, Analytics)
- Shared database infrastructure (PostgreSQL + InfluxDB schema coordination)

### Functional Requirements Covered
| ID | Requirement |
|:---|:---|
| **FR-E3** | Managers can configure lamppost timings (requires Manager role) |
| **FR-H2** | Managers can configure alert thresholds (requires Manager role) |
| **FR-O2** | Authentication event monitoring and logging |
| **6.2.1** | Management View: high-level status summaries |
| **6.2.2** | Serviceability View: heartbeat logs, battery, calibration |
| **6.2.3** | Analytics View: ML model accuracy, long-term trends |

---

## 2. Design Patterns & Architectural Rationale

### 2.1 Chain of Responsibility Pattern — Request Authentication Pipeline
**Problem:** Every incoming API request must pass through multiple security checks: token presence → token validity → token expiry → role extraction → permission verification. These checks should be modular and reorderable.  
**Solution:** Use **Chain of Responsibility** where each security check is a handler in a chain.

```
Incoming Request
  │
  ▼
[Token Presence Check] → 401 if no token
  │
  ▼
[JWT Signature Validator] → 401 if tampered
  │
  ▼
[Token Expiry Check] → 401 if expired
  │
  ▼
[Role Extractor] → extracts user_id + role from claims
  │
  ▼
[RBAC Permission Verifier] → 403 if role lacks permission for route
  │
  ▼
Request PASSES → forwarded to domain engine
```

```python
class SecurityHandler(ABC):
    def __init__(self):
        self._next: Optional[SecurityHandler] = None
    
    def set_next(self, handler: 'SecurityHandler') -> 'SecurityHandler':
        self._next = handler
        return handler
    
    @abstractmethod
    def handle(self, request: AuthContext) -> AuthContext: ...

class TokenPresenceCheck(SecurityHandler):
    def handle(self, ctx):
        if not ctx.token:
            raise HTTPException(401, "No authorization token provided")
        return self._next.handle(ctx) if self._next else ctx

class JWTSignatureValidator(SecurityHandler):
    def handle(self, ctx):
        try:
            ctx.claims = jwt.decode(ctx.token, SECRET_KEY, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid token signature")
        return self._next.handle(ctx) if self._next else ctx

class RBACPermissionVerifier(SecurityHandler):
    def handle(self, ctx):
        allowed = self._check_permission(ctx.role, ctx.requested_route)
        if not allowed:
            raise HTTPException(403, f"Role '{ctx.role}' cannot access '{ctx.requested_route}'")
        return self._next.handle(ctx) if self._next else ctx
```

**Monolith Tradeoff:** In a monolith, you'd use a single middleware function with nested if-else. Chain of Responsibility allows inserting new checks (e.g., IP whitelist, 2FA) by adding a new handler class — no existing code modified.

### 2.2 Flyweight Pattern — Permission Matrix Caching
**Problem:** Every API request queries PostgreSQL to check `role → route → permission`. With hundreds of concurrent users, this creates excessive DB load.  
**Solution:** Use the **Flyweight Pattern** to cache the entire permission matrix in memory. Since roles and permissions change rarely (admin action only), the cache is invalidated only on explicit admin updates.

```python
class PermissionFlyweight:
    """Singleton cache holding the permission matrix in-memory."""
    _instance = None
    _matrix: Dict[str, Set[str]] = {}  # role → set of allowed routes
    
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
            cls._load_from_db()
        return cls._instance
    
    def check(self, role: str, route: str) -> bool:
        return route in self._matrix.get(role, set())
    
    def invalidate(self):
        """Called when admin updates roles/permissions."""
        self._load_from_db()
```

### 2.3 Strategy Pattern — Dashboard Aggregation per Role
**Problem:** Different roles see entirely different dashboard content:
- **Management:** high-level KPIs, solar output, AQI summary, alert counts
- **Serviceability:** node heartbeats, battery levels, calibration status, maintenance queue
- **Analytics:** ML model accuracy, prediction confidence, trend charts, raw data tables

**Solution:** Use the **Strategy Pattern** for dashboard data aggregation.

```
┌───────────────────────────────────┐
│  DashboardAggregationStrategy     │ <<interface>>
│  + aggregate(user) → DashData     │
└───────────┬───────────────────────┘
            │ implements
   ┌────────┴───────┬──────────────────┐
   │                │                  │
┌──▼──────────┐ ┌───▼───────────┐ ┌───▼──────────┐
│Management   │ │Serviceability │ │Analytics     │
│Aggregator   │ │Aggregator     │ │Aggregator    │
└─────────────┘ └───────────────┘ └──────────────┘
```

```python
class ManagementAggregator(DashboardAggregationStrategy):
    def aggregate(self, user):
        return {
            "solar_output_kw": self._energy_api.get_current_solar(),
            "aqi_summary": self._ehs_api.get_current_aqi(),
            "active_alerts": self._alert_api.get_alert_count(),
            "lamppost_status": self._energy_api.get_lamppost_overview(),
        }

class ServiceabilityAggregator(DashboardAggregationStrategy):
    def aggregate(self, user):
        return {
            "node_heartbeats": self._ehs_api.get_device_health(),
            "battery_levels": self._ehs_api.get_battery_report(),
            "calibration_queue": self._ehs_api.get_calibration_status(),
            "offline_nodes": self._ehs_api.get_offline_nodes(),
        }
```

### 2.4 Mediator Pattern — API Gateway as Central Mediator
**Problem:** The Flutter frontend would need to know the URLs and APIs of every backend service (EHS Engine, Energy Engine, Alerting Engine, Privacy Gateway). This creates tight coupling.  
**Solution:** The **API Gateway acts as a Mediator**. The frontend talks to ONE endpoint. The gateway routes, authenticates, and aggregates responses from multiple backend services.

```
┌──────────────┐                ┌─────────────────────┐
│ Flutter App  │ ──HTTPS───→   │  API Gateway         │
│ (knows only  │                │  (Mediator)          │
│  1 URL)      │                │                      │
└──────────────┘                │  ├→ Energy Engine     │
                                │  ├→ EHS Engine        │
                                │  ├→ Alerting Engine   │
                                │  └→ Privacy Gateway   │
                                └─────────────────────┘
```

**Monolith Tradeoff:** In a monolith, direct imports replace the mediator. The mediator adds a network hop (~5ms) but enables:
- Independent scaling of backend services
- Backend URL changes without frontend redeployment
- Cross-cutting concerns (auth, logging, rate limiting) applied once

### 2.5 Decorator Pattern — Request Logging & Metrics
**Problem:** Every API request should be logged (who, what, when, response time) and metriced without polluting business logic.  
**Solution:** Use the **Decorator Pattern** as FastAPI middleware to wrap every route handler with logging and metrics.

```python
class RequestLoggingDecorator:
    def __init__(self, handler: Callable):
        self._handler = handler
    
    async def __call__(self, request: Request):
        start = time.time()
        user = request.state.user
        
        response = await self._handler(request)
        
        elapsed = time.time() - start
        logger.info(f"[{user.role}] {request.method} {request.url.path} → {response.status_code} ({elapsed:.3f}s)")
        metrics.histogram("api_latency", elapsed, tags={"route": request.url.path})
        
        return response
```

### 2.6 Abstract Factory Pattern — Database Connection Factories
**Problem:** The system uses TWO databases (PostgreSQL + InfluxDB) with different connection patterns, pooling strategies, and health checks.  
**Solution:** Use an **Abstract Factory** to produce the correct connection type.

```
┌───────────────────────────────────┐
│  DatabaseFactory                  │ <<abstract>>
│  + create_connection()            │
│  + create_pool()                  │
│  + create_health_check()          │
└───────────┬───────────────────────┘
    ┌───────┴──────────┐
    │                  │
┌───▼────────┐  ┌──────▼──────┐
│PostgreSQL  │  │InfluxDB     │
│Factory     │  │Factory      │
└────────────┘  └─────────────┘
```

### 2.7 State Pattern — User Session Management
**Problem:** A user session transitions through states: `CREATED → ACTIVE → IDLE → EXPIRED → REVOKED`. Each state allows different operations.  
**Solution:** Use the **State Pattern** to encapsulate state-specific behavior.

```python
class SessionState(ABC):
    @abstractmethod
    def handle_request(self, session: 'Session', request: Request): ...
    @abstractmethod
    def can_refresh(self) -> bool: ...

class ActiveState(SessionState):
    def handle_request(self, session, request):
        session.last_activity = datetime.utcnow()
        return True  # Allow
    
    def can_refresh(self) -> bool:
        return True

class ExpiredState(SessionState):
    def handle_request(self, session, request):
        raise HTTPException(401, "Session expired — please re-authenticate")
    
    def can_refresh(self) -> bool:
        return False  # Must re-login

class IdleState(SessionState):
    def handle_request(self, session, request):
        if session.idle_time > timedelta(minutes=30):
            session.transition_to(ExpiredState())
            raise HTTPException(401, "Session timed out")
        session.transition_to(ActiveState())
        return True
```

---

## 3. Microservices Architecture Patterns

### 3.1 API Gateway Pattern (Core Responsibility)
This service IS the **API Gateway Pattern** incarnation:
- **Single Entry Point:** All client traffic enters through one URL
- **Cross-Cutting Concerns:** Authentication, authorization, logging, rate limiting applied centrally
- **Request Routing:** Maps `/energy/*` → Energy Engine, `/ehs/*` → EHS Engine, etc.
- **Response Aggregation:** Dashboard endpoints fan-out to multiple services and merge results

### 3.2 Backend for Frontend (BFF) Pattern
The gateway acts as a **BFF** — it tailors responses for the Flutter frontend:
- Web dashboard gets paginated tables with full metadata
- Mobile app gets compact JSON with essential metrics only
- Both call the same gateway, but the `DashboardAggregator` formats differently per client type

```python
@router.get("/dashboard")
async def get_dashboard(request: Request, user: User = Depends(get_current_user)):
    strategy = STRATEGY_MAP[user.role]  # Strategy Pattern
    raw_data = strategy.aggregate(user)
    
    if request.headers.get("X-Client-Type") == "mobile":
        return MobileSerializer.compact(raw_data)  # BFF: mobile-optimized
    return WebSerializer.full(raw_data)             # BFF: web-optimized
```

### 3.3 Service Registry — Internal Service Discovery
The gateway maintains a **Service Registry** of backend service URLs:
```python
SERVICE_REGISTRY = {
    "energy_engine": "http://energy-engine:8001",
    "ehs_engine": "http://ehs-engine:8002",
    "alerting_engine": "http://alerting-engine:8003",
    "privacy_gateway": "http://privacy-gateway:8004",
}
```
In Docker Compose, these resolve via container names. In production, this would use Consul or DNS-based discovery.

### 3.4 Circuit Breaker — Backend Service Health
Each backend service call is circuit-breaker protected:
- If Energy Engine is down → dashboard shows "Energy data unavailable" instead of crashing
- If EHS Engine is down → return cached last-known AQI values

### 3.5 Token Bucket Rate Limiting
Global and per-user rate limiting at the gateway:
```python
RATE_LIMITS = {
    "manager": {"requests_per_minute": 120, "burst": 20},
    "serviceability": {"requests_per_minute": 60, "burst": 10},
    "analytics": {"requests_per_minute": 200, "burst": 50},  # Higher for data-heavy queries
    "resident": {"requests_per_minute": 30, "burst": 5},
}
```

### 3.6 Strangler Fig Pattern — Gradual Decomposition
The API Gateway enables the **Strangler Fig** migration pattern. If the team later decides to extract RBAC into its own microservice:
1. Deploy standalone RBAC service
2. Gateway routes auth calls to new service
3. Remove auth logic from gateway
4. Zero downtime, zero frontend changes

---

## 4. Monolith vs Microservice Tradeoffs

### Why a Dedicated API Gateway?
| Aspect | Monolith (No Gateway) | Our API Gateway |
|:---|:---|:---|
| **Security** | Each engine implements its own auth — inconsistent | Auth enforced centrally, once, correctly |
| **Frontend Coupling** | Flutter must know 5+ backend URLs | Flutter knows ONE gateway URL |
| **Cross-Cutting** | Logging, rate limiting duplicated per engine | Applied once at gateway level |
| **Evolution** | Can't swap an engine without frontend change | Backend URLs change without frontend impact |

### What We Sacrifice
| Concern | Cost |
|:---|:---|
| **Single Point of Failure** | Gateway down = entire system unreachable. Mitigated with health checks + auto-restart |
| **Added Latency** | Every request adds ~5-10ms for auth + routing. Acceptable for dashboard (not for CAM <1s) |
| **Complexity** | Gateway must be maintained as services evolve — routing table + schema changes |
| **Bottleneck Risk** | All traffic funnels through one service. Mitigated with horizontal scaling |
| **Over-Engineering** | For 5 services, a gateway is borderline. For 20+ services, it's essential |

### Hybrid Decision
The CAM Engine's <1s authentication **bypasses the gateway** and uses edge-local processing. All other (non-latency-critical) requests go through the gateway. This is a pragmatic hybrid:
- Gateway for: dashboards, config, alerts, research API
- Direct edge for: entrance authentication

---

## 5. Deliverables

### 5.1 API Gateway (`backend/api_gateway/`)

#### A. Security Chain (`security/`)
- [ ] `SecurityHandler` base + chain setup (**Chain of Responsibility**)
- [ ] `TokenPresenceCheck` — rejects requests without Authorization header
- [ ] `JWTValidator` — validates HS256 signature using `python-jose`
- [ ] `TokenExpiryCheck` — rejects expired tokens
- [ ] `RoleExtractor` — extracts role from JWT claims
- [ ] `RBACVerifier` — checks permission matrix (**Flyweight** cached)

#### B. Dashboard Aggregation (`aggregators/`)
- [ ] `DashboardAggregationStrategy` interface (**Strategy Pattern**)
- [ ] `ManagementAggregator` — KPI summaries, solar output, AQI, alert counts
- [ ] `ServiceabilityAggregator` — node heartbeats, battery, calibration
- [ ] `AnalyticsAggregator` — ML accuracy, trend data, prediction confidence

#### C. Request Routing & Mediation
- [ ] `router.py` — Routes `/energy/*`, `/ehs/*`, `/alerts/*`, `/research/*` to backend services (**Mediator**)
- [ ] `service_registry.py` — Service URL registry (**Service Registry Pattern**)
- [ ] Circuit breaker per backend service

#### D. Middleware Stack
- [ ] `logging_decorator.py` — Request/response logging (**Decorator Pattern**)
- [ ] `metrics_decorator.py` — Latency and throughput metrics
- [ ] `rate_limiter.py` — Token bucket per role per user
- [ ] `cors.py` — CORS configuration for Flutter web

#### E. Session Management
- [ ] `session.py` — State machine for session lifecycle (**State Pattern**)
- [ ] `SessionState`: `ActiveState`, `IdleState`, `ExpiredState`, `RevokedState`

#### F. Auth Routes
- [ ] `POST /auth/login` — Authenticate and issue JWT
- [ ] `POST /auth/refresh` — Refresh token (if state allows)
- [ ] `POST /auth/logout` — Revoke session
- [ ] `GET /auth/me` — Return current user profile and role

### 5.2 Database Infrastructure (`backend/database/`)

#### PostgreSQL Schema
- [ ] `users` (id, username, email, password_hash, role_id, zone, phone, created_at)
- [ ] `roles` (id, role_name: manager|serviceability|analytics|resident|researcher)
- [ ] `permissions` (id, role_id, route_pattern, method, allowed)
- [ ] `sessions` (id, user_id, token_hash, state, created_at, last_activity, expires_at)
- [ ] `lamppost_schedules` (id, node_id, on_time, off_time, override, created_by) — *used by Member 1*
- [ ] `alert_thresholds` (id, sensor_type, min_safe, max_safe, severity, updated_by) — *used by Member 2*
- [ ] `alert_history` (id, type, severity, zone, message, sms_sent, email_sent, created_at) — *used by Member 3*
- [ ] `alert_outbox` (id, alert_id, dispatched, retry_count, created_at) — *used by Member 3*
- [ ] `notification_preferences` (user_id, sms_enabled, email_enabled) — *used by Member 3*
- [ ] `researcher_keys` (id, api_key, researcher_name, rate_limit, active) — *used by Member 3*
- [ ] `hardware_whitelist` (node_id, mac, api_key, domain, active) — *used by Member 2*

#### Database Connection Factory
- [ ] `PostgreSQLFactory` and `InfluxDBFactory` (**Abstract Factory**)
- [ ] Connection pooling (SQLAlchemy `create_engine(pool_size=10)`)
- [ ] Health check endpoints

#### Migration Scripts
- [ ] Alembic migration files for PostgreSQL schema versioning
- [ ] Seed data: default roles, permissions, test users

---

## 6. Directory Structure

```
backend/
├── api_gateway/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app with middleware stack
│   ├── config.py
│   ├── security/
│   │   ├── __init__.py
│   │   ├── base.py              # SecurityHandler chain base
│   │   ├── token_presence.py
│   │   ├── jwt_validator.py
│   │   ├── expiry_check.py
│   │   ├── role_extractor.py
│   │   └── rbac_verifier.py     # Uses Flyweight permission cache
│   ├── aggregators/
│   │   ├── __init__.py
│   │   ├── base.py              # DashboardAggregationStrategy interface
│   │   ├── management.py
│   │   ├── serviceability.py
│   │   └── analytics.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── logging_decorator.py # Decorator Pattern
│   │   ├── metrics_decorator.py
│   │   ├── rate_limiter.py      # Token Bucket
│   │   └── cors.py
│   ├── session/
│   │   ├── __init__.py
│   │   ├── state_machine.py     # State Pattern
│   │   ├── active.py
│   │   ├── idle.py
│   │   ├── expired.py
│   │   └── revoked.py
│   ├── router.py                # Mediator / route mapping
│   ├── service_registry.py      # Service discovery
│   ├── routes.py                # Auth endpoints
│   ├── models.py
│   └── tests/
│       ├── test_security_chain.py
│       ├── test_aggregators.py
│       ├── test_rate_limiter.py
│       ├── test_session_states.py
│       ├── test_routes.py
│       └── test_integration.py
│
└── database/
    ├── __init__.py
    ├── factories/
    │   ├── __init__.py
    │   ├── base.py              # DatabaseFactory interface
    │   ├── postgres_factory.py
    │   └── influxdb_factory.py
    ├── migrations/
    │   ├── env.py               # Alembic config
    │   └── versions/
    │       ├── 001_create_users_roles.py
    │       ├── 002_create_permissions.py
    │       ├── 003_create_sessions.py
    │       ├── 004_create_alert_tables.py
    │       └── 005_create_research_tables.py
    ├── seeds/
    │   ├── seed_roles.py
    │   ├── seed_permissions.py
    │   └── seed_test_users.py
    └── models/
        └── sqlalchemy_models.py # SQLAlchemy ORM models
```

---

## 7. Design Pattern Summary Table

| Pattern | Where Used | Purpose |
|:---|:---|:---|
| **Chain of Responsibility** | Security Pipeline | Modular, reorderable auth checks |
| **Flyweight** | Permission Matrix | Cache roles/permissions in-memory for fast lookups |
| **Strategy** | Dashboard Aggregation | Different data views per role |
| **Mediator** | API Gateway Router | Decouple frontend from backend service URLs |
| **Decorator** | Request Logging/Metrics | Non-invasive cross-cutting concerns |
| **Abstract Factory** | Database Connections | Produce correct connection type per database |
| **State** | Session Management | Lifecycle transitions with state-specific behavior |
| **Singleton** | Config, Flyweight cache | One instance shared across the gateway |
| **Circuit Breaker** | Backend Service Calls | Graceful degradation per service |

---

## 8. Acceptance Criteria

- [ ] Chain of Responsibility: unauthorized token rejected at step 2, never reaches RBAC
- [ ] Flyweight: permission cache serves 1000 checks/sec without DB query
- [ ] Strategy: manager sees KPIs, serviceability sees heartbeats, analytics sees ML stats
- [ ] Mediator: Flutter calls ONE gateway URL; backend service swap is transparent
- [ ] Decorator: every request logged with user, route, latency, status code
- [ ] State: expired session returns 401; idle session auto-expires after 30min
- [ ] Abstract Factory: PostgreSQL and InfluxDB connections created through factory
- [ ] Rate Limiter: resident exceeding 30 req/min gets 429
- [ ] Alembic migrations create all tables correctly
- [ ] Seed data provides working test users for all 5 roles
- [ ] All unit & integration tests pass
