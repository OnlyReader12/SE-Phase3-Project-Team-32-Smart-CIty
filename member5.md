# Member 5 — Flutter Frontend + Docker Infrastructure & Integration Testing

> **Role:** Frontend & DevOps Lead  
> **Scope:** Unified Flutter UI application (Web + Mobile), Docker Compose orchestration for all microservices, end-to-end integration testing, and CI/CD pipeline configuration.

---

## 1. Feature Overview

### Feature A — Unified Flutter Dashboard Application
A **cross-platform Flutter application** (Web + iOS + Android) providing:
- Role-tailored dashboards (Management, Serviceability, Analytics)
- Real-time telemetry visualization (charts, gauges, heatmaps)
- Alert notification display and configuration
- Lamppost automation UI
- Responsive design adapting from desktop dashboards to mobile compact views

### Feature B — Docker Infrastructure & Orchestration
Complete **Docker Compose** setup orchestrating all microservices:
- 7 containers: API Gateway, Ingestion, Middleware, EHS Engine, Energy Engine, Alerting, Privacy Gateway
- 2 databases: PostgreSQL + InfluxDB
- 1 message broker: RabbitMQ
- Health checks, dependency ordering, restart policies

### Feature C — End-to-End Integration Testing
- Cross-service integration tests validating the entire pipeline
- Contract tests between services
- Load testing for critical paths

### Functional Requirements Covered
| ID | Requirement |
|:---|:---|
| **FR-E1** | Real-time dashboards for solar/AC energy |
| **FR-H1** | Visualize real-time AQI and water quality |
| **FR-O1** | Real-time crowd density and heatmaps |
| **FR-U2** | Automated control of fans, lights, ACs in smart classrooms |
| **FR-U3** | Residents view parameter visualizations via mobile and web |
| **6.2.1** | Management View: high-level summaries |
| **6.2.2** | Serviceability View: heartbeat, battery, calibration |
| **6.2.3** | Analytics View: ML accuracy, trends |

---

## 2. Design Patterns & Architectural Rationale

### 2.1 MVC / MVVM Pattern — Application Architecture
**Problem:** Flutter UI code can become a monolithic mess of business logic mixed with UI rendering.  
**Solution:** Use **MVVM (Model-View-ViewModel)** to separate concerns:

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────┐
│   Model     │ ←── │   ViewModel      │ ←── │   View         │
│ (Data DTOs) │     │ (State + Logic)  │     │ (Flutter Widgets)│
│             │     │                  │     │                │
│ EnergyData  │     │ EnergyVM         │     │ EnergyDashboard│
│ EHSData     │     │  - fetchData()   │     │  - build()     │
│ AlertData   │     │  - state: Loading│     │  - StreamBuilder│
└─────────────┘     │  - state: Ready  │     └────────────────┘
                    │  - state: Error  │
                    └──────────────────┘
```

**Why not raw StatefulWidgets?** MVVM enables:
- Unit testing ViewModels without a Flutter test harness
- Reusing the same ViewModel across web and mobile (different Views, same ViewModel)
- Clear separation of API calls from UI rendering

### 2.2 Observer Pattern — Real-Time Data Streams
**Problem:** Dashboard data must update in real-time as sensor readings arrive, without polling.  
**Solution:** Use Flutter's `Stream` + `StreamBuilder` as an implementation of the **Observer Pattern**. The ViewModel is the Subject emitting state changes; the View is the Observer re-rendering on each emission.

```dart
class EnergyViewModel {
  final _stateController = StreamController<DashboardState>.broadcast();
  Stream<DashboardState> get stateStream => _stateController.stream;
  
  void fetchDashboard() async {
    _stateController.add(DashboardState.loading());
    try {
      final data = await _apiService.getEnergyDashboard();
      _stateController.add(DashboardState.ready(data));
    } catch (e) {
      _stateController.add(DashboardState.error(e.toString()));
    }
  }
}

// In the View:
StreamBuilder<DashboardState>(
  stream: viewModel.stateStream,
  builder: (context, snapshot) {
    if (snapshot.data is Loading) return CircularProgressIndicator();
    if (snapshot.data is Ready) return EnergyCharts(data: snapshot.data.data);
    if (snapshot.data is Error) return ErrorWidget(message: snapshot.data.message);
  },
)
```

### 2.3 Factory Pattern — Widget Factory per Role
**Problem:** The dashboard layout changes completely based on user role. Management sees KPI cards; Serviceability sees device tables; Analytics sees charts.  
**Solution:** Use a **Factory Pattern** to produce the correct dashboard widget tree based on the authenticated user's role.

```dart
abstract class DashboardFactory {
  Widget createHeader();
  Widget createMainContent();
  Widget createSidebar();
  Widget createAlertPanel();
}

class ManagementDashboardFactory implements DashboardFactory {
  Widget createMainContent() => KPISummaryGrid();    // Cards with solar, AQI, alerts
  Widget createSidebar() => LamppostControlPanel();   // FR-E3
  Widget createAlertPanel() => AlertConfigPanel();    // FR-H2
}

class ServiceabilityDashboardFactory implements DashboardFactory {
  Widget createMainContent() => DeviceHealthTable();  // Heartbeats for 300 nodes
  Widget createSidebar() => CalibrationQueue();
  Widget createAlertPanel() => MaintenanceAlerts();
}

class AnalyticsDashboardFactory implements DashboardFactory {
  Widget createMainContent() => MLAccuracyCharts();
  Widget createSidebar() => TrendAnalysisPanel();
  Widget createAlertPanel() => PredictionConfidence();
}

// Router uses factory:
DashboardFactory factory = _getFactory(user.role);
Scaffold(
  appBar: factory.createHeader(),
  body: factory.createMainContent(),
  drawer: factory.createSidebar(),
  bottomSheet: factory.createAlertPanel(),
)
```

### 2.4 Adapter Pattern — API Response Normalization
**Problem:** Different backend engines return different JSON structures. The Energy Engine returns `{"solar_watts": 450}`, the EHS Engine returns `{"aqi_value": 142}`. The UI needs a uniform data model.  
**Solution:** Use the **Adapter Pattern** to convert each engine's response into a unified `DashboardDataModel`.

```dart
abstract class APIResponseAdapter {
  DashboardDataModel adapt(Map<String, dynamic> json);
}

class EnergyResponseAdapter implements APIResponseAdapter {
  DashboardDataModel adapt(Map<String, dynamic> json) {
    return DashboardDataModel(
      title: "Solar Output",
      value: json["solar_watts"],
      unit: "W",
      trend: json["trend"],
    );
  }
}

class EHSResponseAdapter implements APIResponseAdapter {
  DashboardDataModel adapt(Map<String, dynamic> json) {
    return DashboardDataModel(
      title: "Air Quality Index",
      value: json["aqi_value"],
      unit: "AQI",
      severity: _mapAQISeverity(json["aqi_value"]),
    );
  }
}
```

### 2.5 Composite Pattern — Dashboard Widget Tree
**Problem:** Dashboards are composed of nested widgets: a page contains sections, sections contain cards, cards contain charts or gauges. We need to treat individual widgets and groups uniformly.  
**Solution:** Use the **Composite Pattern** where a `DashboardComponent` can be a leaf (single chart) or a composite (group of charts).

```
DashboardComponent (interface)
├── LeafWidget (gauge, chart, number card)
└── CompositeWidget (section, grid, row)
    ├── LeafWidget
    ├── LeafWidget
    └── CompositeWidget
        ├── LeafWidget
        └── LeafWidget
```

```dart
abstract class DashboardComponent {
  Widget render();
}

class GaugeWidget implements DashboardComponent {
  final double value;
  final String label;
  Widget render() => RadialGauge(value: value, label: label);
}

class SectionComposite implements DashboardComponent {
  final String title;
  final List<DashboardComponent> children;
  
  Widget render() => Column(
    children: [
      Text(title, style: sectionHeaderStyle),
      ...children.map((c) => c.render()),
    ],
  );
}
```

### 2.6 Singleton Pattern — API Service & Auth Token Manager
**Problem:** The API service holds the base URL and auth token. Multiple ViewModels shouldn't create separate instances.  
**Solution:** Singleton `APIService` and `AuthManager`.

```dart
class APIService {
  static final APIService _instance = APIService._internal();
  factory APIService() => _instance;
  APIService._internal();
  
  String? _authToken;
  final String _baseUrl = "https://gateway.smartcity.local";
  
  Future<Map<String, dynamic>> get(String path) async {
    final response = await http.get(
      Uri.parse("$_baseUrl$path"),
      headers: {"Authorization": "Bearer $_authToken"},
    );
    return jsonDecode(response.body);
  }
}
```

### 2.7 Strategy Pattern — Chart Rendering
**Problem:** The same data can be visualized as a line chart, bar chart, or gauge depending on user preference or data type.  
**Solution:** Use the **Strategy Pattern** for chart rendering.

```dart
abstract class ChartStrategy {
  Widget render(List<DataPoint> data, ChartConfig config);
}

class LineChartStrategy implements ChartStrategy {
  Widget render(data, config) => LineChart(data: data, color: config.color);
}

class BarChartStrategy implements ChartStrategy {
  Widget render(data, config) => BarChart(data: data, color: config.color);
}

class GaugeStrategy implements ChartStrategy {
  Widget render(data, config) => RadialGauge(value: data.last.value);
}
```

### 2.8 State Pattern — App Navigation States
**Problem:** The app transitions between states: `Unauthenticated → Authenticating → Authenticated → SessionExpired`. Each state determines what screens are accessible.  
**Solution:** Use the **State Pattern** for app-level navigation.

```dart
abstract class AppState {
  List<Widget> getAccessibleScreens();
  Widget getInitialScreen();
}

class UnauthenticatedState implements AppState {
  Widget getInitialScreen() => LoginScreen();
  List<Widget> getAccessibleScreens() => [LoginScreen(), ForgotPasswordScreen()];
}

class AuthenticatedState implements AppState {
  final User user;
  Widget getInitialScreen() => DashboardScreen(user: user);
  List<Widget> getAccessibleScreens() => [
    DashboardScreen(user: user),
    SettingsScreen(),
    if (user.role == 'manager') ConfigScreen(),
  ];
}
```

---

## 3. Microservices Architecture Patterns (Infrastructure)

### 3.1 Service Mesh via Docker Compose
All microservices are orchestrated via **Docker Compose** with:
- **Internal DNS:** Services reference each other by container name (`energy-engine:8001`)
- **Network Isolation:** All services on a private `smartcity-net` bridge network
- **Health Checks:** Each service reports `/health` status
- **Dependency Ordering:** `depends_on` with health conditions

```yaml
services:
  rabbitmq:
    image: rabbitmq:3-management
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
    
  postgres:
    image: postgres:16
    healthcheck:
      test: ["CMD-SHELL", "pg_isready"]
    
  influxdb:
    image: influxdb:2.7
    healthcheck:
      test: ["CMD", "influx", "ping"]
    
  api-gateway:
    build: ./backend/api_gateway
    depends_on:
      postgres: { condition: service_healthy }
    ports: ["8000:8000"]
    
  ingestion-gateway:
    build: ./backend/ingestion_gateway
    depends_on:
      rabbitmq: { condition: service_healthy }
    ports: ["1883:1883", "8010:8010"]
    
  semantic-middleware:
    build: ./backend/semantic_middleware
    depends_on:
      rabbitmq: { condition: service_healthy }
      ingestion-gateway: { condition: service_healthy }
    
  ehs-engine:
    build: ./backend/ehs_engine
    depends_on:
      rabbitmq: { condition: service_healthy }
      influxdb: { condition: service_healthy }
    
  energy-engine:
    build: ./backend/energy_engine
    depends_on:
      rabbitmq: { condition: service_healthy }
      influxdb: { condition: service_healthy }
    
  alerting-engine:
    build: ./backend/alerting_engine
    depends_on:
      rabbitmq: { condition: service_healthy }
      postgres: { condition: service_healthy }
    
  privacy-gateway:
    build: ./backend/privacy_gateway
    depends_on:
      influxdb: { condition: service_healthy }
      postgres: { condition: service_healthy }
```

### 3.2 Sidecar Pattern — Log Aggregation
Each microservice container runs with a logging sidecar that:
- Captures stdout/stderr
- Formats logs with correlation IDs and timestamps
- Forwards to a central log aggregator (ELK stack or Loki)

### 3.3 Health Check Pattern — Deep Health Verification
Each service exposes `/health` with:
```json
{
  "service": "energy-engine",
  "status": "healthy",
  "dependencies": {
    "rabbitmq": "connected",
    "influxdb": "connected",
    "circuit_breaker_influx": "CLOSED"
  },
  "uptime_seconds": 3420,
  "version": "1.2.0"
}
```

### 3.4 Contract Testing — Service Compatibility
Use **Pact** or manual schema validation to ensure:
- Middleware's `SmartCityObject` JSON matches what EHS/Energy engines expect
- API Gateway's aggregated response matches what Flutter expects
- Alert payload format matches Alerting Engine's expectations

### 3.5 Chaos Engineering (Bonus)
Docker Compose profiles for testing resilience:
```yaml
profiles:
  - chaos
services:
  chaos-monkey:
    image: chaostoolkit
    command: ["kill", "energy-engine"]  # Test fault isolation
```

---

## 4. Monolith vs Microservice Tradeoffs (Infrastructure Perspective)

### Deployment Comparison
| Aspect | Monolith Deployment | Our Docker Compose Approach |
|:---|:---|:---|
| **Startup** | `python main.py` — one process | `docker compose up` — 10 containers boot in dependency order |
| **Memory** | ~200MB for one Python process | ~1.5-2GB total (each container + DBs + RabbitMQ) |
| **Debugging** | Single stack trace, single log file | Distributed logs across 10 containers — need correlation IDs |
| **Configuration** | One `.env` file | Each service has its own config — risk of drift |
| **Rolling Updates** | Redeploy everything | `docker compose up -d energy-engine` — update one service |

### Frontend Complexity Tradeoff
| Aspect | Monolith Frontend | Our Multi-Service Frontend |
|:---|:---|:---|
| **API Calls** | `fetch("/api/dashboard")` — one call | Calls gateway → gateway fans out to 4 services |
| **Error Handling** | Simple: either works or doesn't | Partial failure: energy data available but EHS engine down |
| **State Management** | One data source | Multiple async streams merged in ViewModel |
| **Offline Support** | Cache one API response | Cache multiple service responses independently |

### Flutter as Monolith Mitigation
Interestingly, the **Flutter frontend itself IS a monolith** — a single codebase compiled to web + mobile. This is intentional:
- UI has no fault isolation requirement (if the app crashes, it crashes)
- Single codebase reduces engineering effort
- The backend microservices handle the fault isolation
- This is the **best of both worlds**: monolith frontend + microservice backend

---

## 5. Deliverables

### Part A — Flutter Application (`frontend/`)

#### A1. Core Architecture
- [ ] MVVM setup with ViewModels and Streams (**MVVM + Observer**)
- [ ] `APIService` singleton for all HTTP calls (**Singleton**)
- [ ] `AuthManager` singleton for JWT token handling
- [ ] `AppState` navigation state machine (**State Pattern**)

#### A2. Authentication Screens
- [ ] `LoginScreen` — Email/password login form
- [ ] `ForgotPasswordScreen` — Reset flow
- [ ] JWT token storage in secure local storage

#### A3. Dashboard Framework
- [ ] `DashboardFactory` interface + 3 implementations (**Factory Pattern**)
  - `ManagementDashboardFactory`
  - `ServiceabilityDashboardFactory`
  - `AnalyticsDashboardFactory`
- [ ] `DashboardComponent` composite tree (**Composite Pattern**)
- [ ] Role-based routing based on JWT claims

#### A4. Energy Dashboard Widgets
- [ ] Solar output real-time gauge
- [ ] AC load consumption line chart
- [ ] Lamppost status grid with ON/OFF controls (FR-E3)
- [ ] Energy forecast chart (24-hour prediction)
- [ ] Savings recommendation cards (FR-E2)

#### A5. EHS Dashboard Widgets
- [ ] AQI gauge with color-coded severity
- [ ] Water quality cards (pH, turbidity)
- [ ] Water quality forecast chart
- [ ] Alert threshold configuration form (FR-H2)

#### A6. Serviceability Widgets
- [ ] Device health table (300 nodes with heartbeat status)
- [ ] Battery level progress bars
- [ ] Calibration queue list
- [ ] Offline node alerts

#### A7. Analytics Widgets
- [ ] ML model accuracy charts (actual vs predicted)
- [ ] Long-term trend line charts
- [ ] Prediction confidence intervals  
- [ ] Data export controls

#### A8. Alert Widgets
- [ ] Real-time alert feed (newest first)
- [ ] Alert history with filters (severity, zone, date range)
- [ ] Alert detail view

#### A9. Response Adapters
- [ ] `EnergyResponseAdapter` (**Adapter Pattern**)
- [ ] `EHSResponseAdapter`
- [ ] `AlertResponseAdapter`
- [ ] `DeviceHealthAdapter`

#### A10. Chart Strategies
- [ ] `ChartStrategy` interface + `LineChartStrategy`, `BarChartStrategy`, `GaugeStrategy` (**Strategy Pattern**)

### Part B — Docker Infrastructure (`infra/`)

- [ ] `docker-compose.yml` — Full 10-container orchestration
- [ ] `docker-compose.override.yml` — Dev overrides (port mapping, volumes)
- [ ] `docker-compose.test.yml` — Integration test environment
- [ ] Individual `Dockerfile` for each backend service
- [ ] `.env.template` — Environment variable template
- [ ] `nginx.conf` — Reverse proxy for Flutter web in production
- [ ] Health check scripts for all services

### Part C — Integration Tests (`tests/integration/`)

- [ ] `test_full_pipeline.py` — MQTT payload → Ingestion → Middleware → RabbitMQ → Engine → InfluxDB
- [ ] `test_alert_flow.py` — Threshold breach → Alert published → SMS/Email dispatched
- [ ] `test_rbac.py` — Manager can access config; resident cannot
- [ ] `test_privacy.py` — Researcher query returns PII-free data
- [ ] `test_circuit_breaker.py` — InfluxDB kill → circuit opens → service degrades gracefully
- [ ] `test_contract.py` — SmartCityObject schema matches across all services

---

## 6. Directory Structure

```
frontend/
├── lib/
│   ├── main.dart
│   ├── app_state.dart           # State Pattern: navigation
│   ├── core/
│   │   ├── api_service.dart     # Singleton HTTP client
│   │   ├── auth_manager.dart    # Singleton JWT handler
│   │   └── config.dart
│   ├── models/
│   │   ├── dashboard_data.dart
│   │   ├── energy_data.dart
│   │   ├── ehs_data.dart
│   │   ├── alert_data.dart
│   │   └── device_health.dart
│   ├── adapters/                # Adapter Pattern
│   │   ├── base.dart
│   │   ├── energy_adapter.dart
│   │   ├── ehs_adapter.dart
│   │   └── alert_adapter.dart
│   ├── viewmodels/              # MVVM ViewModels + Observer
│   │   ├── energy_vm.dart
│   │   ├── ehs_vm.dart
│   │   ├── alerts_vm.dart
│   │   ├── devices_vm.dart
│   │   └── analytics_vm.dart
│   ├── factories/               # Factory Pattern
│   │   ├── base.dart
│   │   ├── management_factory.dart
│   │   ├── serviceability_factory.dart
│   │   └── analytics_factory.dart
│   ├── components/              # Composite Pattern
│   │   ├── base.dart
│   │   ├── gauge_widget.dart
│   │   ├── chart_widget.dart
│   │   ├── kpi_card.dart
│   │   ├── data_table.dart
│   │   └── section_composite.dart
│   ├── charts/                  # Strategy Pattern
│   │   ├── base.dart
│   │   ├── line_chart.dart
│   │   ├── bar_chart.dart
│   │   └── gauge.dart
│   ├── screens/
│   │   ├── login_screen.dart
│   │   ├── dashboard_screen.dart
│   │   ├── settings_screen.dart
│   │   └── alert_history_screen.dart
│   └── theme/
│       ├── colors.dart
│       ├── typography.dart
│       └── dark_theme.dart
├── pubspec.yaml
├── web/
│   └── index.html
└── test/
    ├── viewmodels/
    │   ├── energy_vm_test.dart
    │   └── ehs_vm_test.dart
    ├── adapters/
    │   └── energy_adapter_test.dart
    └── factories/
        └── dashboard_factory_test.dart

infra/
├── docker-compose.yml
├── docker-compose.override.yml
├── docker-compose.test.yml
├── .env.template
├── nginx.conf
├── dockerfiles/
│   ├── Dockerfile.api_gateway
│   ├── Dockerfile.ingestion
│   ├── Dockerfile.middleware
│   ├── Dockerfile.ehs_engine
│   ├── Dockerfile.energy_engine
│   ├── Dockerfile.alerting
│   └── Dockerfile.privacy
└── scripts/
    ├── healthcheck.sh
    ├── seed_db.sh
    └── run_integration_tests.sh

tests/
└── integration/
    ├── test_full_pipeline.py
    ├── test_alert_flow.py
    ├── test_rbac.py
    ├── test_privacy.py
    ├── test_circuit_breaker.py
    └── test_contract.py
```

---

## 7. Design Pattern Summary Table

| Pattern | Where Used | Purpose |
|:---|:---|:---|
| **MVVM** | App Architecture | Separate UI rendering from business logic |
| **Observer** | StreamBuilder | Real-time UI updates on data change |
| **Factory** | Dashboard per Role | Produce correct widget tree based on user role |
| **Adapter** | API Responses | Normalize different engine JSON formats |
| **Composite** | Widget Tree | Uniform treatment of leaf and group widgets |
| **Singleton** | APIService, AuthManager | One shared instance for HTTP and auth |
| **Strategy** | Chart Rendering | Swap visualization type per data context |
| **State** | App Navigation | Control screen access based on auth state |
| **Sidecar** | Log Aggregation | Non-invasive log collection per container |
| **Health Check** | All Services | Deep dependency verification |

---

## 8. Acceptance Criteria

### Flutter Frontend
- [ ] Factory: manager login shows KPI dashboard; serviceability login shows device table
- [ ] MVVM: ViewModel unit tests pass without Flutter test harness
- [ ] Observer: dashboard updates in real-time via StreamBuilder
- [ ] Adapter: different engine JSON formats rendered uniformly
- [ ] Composite: nested sections render correctly
- [ ] State: unauthenticated user can ONLY see login screen
- [ ] Responsive: web dashboard adapts to mobile viewport

### Docker Infrastructure
- [ ] `docker compose up` boots all 10 containers in correct order
- [ ] Health checks pass for all services within 60 seconds
- [ ] Killing one engine container doesn't crash others (fault isolation verified)
- [ ] `docker compose up -d energy-engine` updates only that service

### Integration Tests
- [ ] Full pipeline: MQTT → Ingestion → Middleware → RabbitMQ → EHS Engine → InfluxDB ✓
- [ ] Alert flow: threshold breach → RabbitMQ → Alerting → formatted SMS/Email ✓
- [ ] RBAC: manager accesses config ✓, resident blocked ✓
- [ ] Privacy: researcher query returns zero PII columns ✓
- [ ] Contract: SmartCityObject schema consistent across all services ✓
