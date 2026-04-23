# Plan 2 (Revised): User & Dashboard Service + Flutter Frontend

## Decisions Locked In
| Decision | Choice |
|---|---|
| UserService DB | SQLite (via SQLAlchemy) |
| Dashboard API | Merged into UserService — one service |
| Alerts | **Origin: Domain Engines → UserService → Flutter + Twilio SMS + SendGrid Email** |
| Actuator Control | Any authorized user can toggle actuator nodes via Flutter |
| Predictions (Analyst) | Simple moving average placeholder |
| Frontend | Flutter (Web + Mobile, single codebase) |
| Frontend Pattern | Decorator Pattern for dashboard views |

---

## High-Level Architecture

```
IoT Nodes (100 nodes — sensors + actuators)
   ↓  HTTP / MQTT / CoAP / WS
IngestionEngine (:8000)
   │  ← also receives actuator COMMANDS (POST /api/actuator/{node_id}/command)
   ↓  RabbitMQ
PersistentMiddleware (:8001)  ← telemetry store, read by UserService
   ↓
Domain Engines (EHSEngine, EnergyEngine)
   │  detect threshold breaches
   ↓  POST /internal/alerts  →  UserService (:8003)
UserService (:8003)
   │  ← Auth + RBAC + Dashboard + Alert fanout + Actuator auth check
   ↓  REST / JSON  (JWT-gated)
Flutter App
   ↓  Decorator-rendered dashboard per role + actuator toggle controls
[Resident | Analyst | Servicer | Manager]
```

---

## Feature 1 (New): Actuator Control

### What it is
Any user who has **access** to an actuator node can toggle its state (ON/OFF, OPEN/CLOSED, etc.)
from the Flutter app. Access is defined as:

| Role | Access rule |
|---|---|
| RESIDENT | Node is in a subscribed zone + subscribed engine_type |
| SERVICER | Node appears in their `servicer_assignments` |
| MANAGER | All actuator nodes across all domains |
| ANALYST | Read-only — no actuator control |

### Data Flow (Simple)

```
Flutter sends:
  PATCH /actuators/{node_id}/command
  Body: { "field": "state", "value": "OFF" }
  Header: Bearer JWT

UserService:
  1. Validates JWT
  2. Checks if this user has access to node_id (role-based check)
  3. If OK → forwards command to IngestionEngine:
       POST http://localhost:8000/api/actuator/{node_id}/command
       Body: { "field": "state", "value": "OFF" }

IngestionEngine:
  - Stores command in an in-memory dict: pending_commands[node_id] = command
  - When the actuator node's next WS message arrives,
    the ACK response embeds the pending command:
       { "ack": "ok", "node_id": "AC-001", "command": {"state": "OFF"} }

Simulator (NodeSimulator):
  - WebSocketSender reads the ACK
  - If ACK contains "command", applies it to node state immediately
  - Next tick emits the updated state back as confirmation
```

### Why this is simple
- **No new protocol needed** — uses existing WebSocket connection bidirectionally
- **No persistent queue** — command is in-memory; if node is offline it waits until next WS reconnect
- **One new endpoint** on UserService + one on IngestionEngine

### New IngestionEngine Route
```
POST /api/actuator/{node_id}/command
Body: { "field": "state", "value": "OFF" }
Response: { "accepted": true, "node_id": "AC-001" }
```
Stores in `pending_commands: dict[str, dict]` (in-memory, one command per node at a time).

### Updated WebSocket ACK (in websocket_adapter.py)
```python
# After persisting the message, check for a pending command
pending = pending_commands.pop(node_id, None)
ack = {"ack": "ok", "node_id": node_id}
if pending:
    ack["command"] = pending   # e.g. {"field": "state", "value": "OFF"}
await websocket.send_text(json.dumps(ack))
```

### Updated Simulator WebSocketSender
```python
ack_data = json.loads(await ws.recv())
if "command" in ack_data:
    field = ack_data["command"]["field"]
    value = ack_data["command"]["value"]
    # Apply directly to the node's generator state
    node.apply_command(field, value)
```

### NodeSimulator.apply_command (simple addition)
```python
def apply_command(self, field: str, value):
    """Override a generator's current value from an external command."""
    if field in self.generators:
        gen = self.generators[field]
        if hasattr(gen, "current"):       # RandomWalk / StepChange
            gen.current = value
        elif hasattr(gen, "_forced"):     # SineWave — add a force override
            gen._forced = value
```

### What is Missing / Next Improvements
- Currently one pending command per node (last-write-wins). Fine for now; can add a queue later.
- If a node is offline (CoAP/HTTP nodes don't hold a WS connection), the command can't be delivered.
  → Next: store commands in the DB and deliver on next HTTP/CoAP poll response.
- No confirmation back to the user that the command was applied (only eventual state update via dashboard).
  → Next: add a `/actuators/{node_id}/state` GET endpoint that returns the last known state.

---

## Feature 2 (Corrected): Alert Flow

### Alert Origin: Domain Engines → UserService (NOT polling)

The Domain Engines (EHSEngine, EnergyManagementEngine) are the correct origin of alerts —
they already process threshold logic. They POST to UserService when a breach is detected.

```
EHSEngine / EnergyEngine
   ↓  POST /internal/alerts  (service-to-service, no JWT — shared internal API key)
UserService.alert_service
   ↓  Looks up subscriptions matching zone + domain
   ↓  For each matching subscriber:
       → In-app: write to alerts table (readable via /dashboard/alerts)
       → SMS (if alert_sms=True): Twilio
       → Email (if alert_email=True): SendGrid
   ↓  Flutter polls /dashboard/alerts every 30s (or on push notification)
```

### New Table: `alerts`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| zone_id | String | Which zone triggered |
| domain | ENUM | energy, water, air |
| node_id | String | Which node triggered it |
| field | String | e.g. "pm2_5", "ph" |
| value | Float | The breaching value |
| threshold | String | Human-readable: "> 100 µg/m³" |
| severity | ENUM | INFO, WARNING, CRITICAL |
| message | Text | Human-readable alert text |
| created_at | DateTime | |
| acknowledged | Boolean | Default false |

### POST /internal/alerts (from Domain Engines)
```json
{
  "zone_id": "BLK-A",
  "domain": "air",
  "node_id": "AIR-QUALITY-081",
  "field": "pm2_5",
  "value": 145.3,
  "threshold": "> 100 µg/m³",
  "severity": "WARNING",
  "message": "PM2.5 level 145 µg/m³ exceeded safe threshold in BLK-A"
}
```

### What is Missing / Next Improvements
- Domain Engines need to be updated to POST alerts here instead of self-managing them.
  → This is a simple add to EHSEngine/EnergyEngine — a `requests.post()` call.
- Alert deduplication: same alert shouldn't fire every 30s if condition persists.
  → Next: add a `last_alerted_at` per (node_id, field) and only re-alert after a cooldown (e.g. 10 min).
- Alerts table grows unbounded.
  → Next: auto-archive alerts older than 7 days.

---

## Service: UserService (`core_modules/UserService/`)
**Port: 8003 | FastAPI + SQLite + SQLAlchemy**

---

### Database Schema (SQLite) — Complete

#### Table: `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| email | String (UNIQUE) | Login credential |
| password_hash | String | bcrypt |
| full_name | String | |
| role | ENUM | RESIDENT, ANALYST, SERVICER, MANAGER |
| created_by | UUID (FK → users.id) | NULL = self-registered |
| is_active | Boolean | |
| phone_number | String (nullable) | Twilio SMS |
| created_at | DateTime | |

#### Table: `subscriptions` (Resident only)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id) | |
| zone_ids | JSON Array | ["BLK-A", "LIB"] |
| engine_types | JSON Array | ["energy", "air"] |
| alert_in_app | Boolean | |
| alert_sms | Boolean | |
| alert_email | Boolean | |
| created_at | DateTime | |

#### Table: `servicer_assignments`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| servicer_id | UUID (FK → users.id) | |
| domain | ENUM | energy, water, air |
| node_id | String | Specific node (e.g. "SOLAR-PANEL-003") |
| status | ENUM | ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED |
| notes | Text (nullable) | Field notes by technician |
| assigned_by | UUID (FK → users.id) | Manager |
| assigned_at | DateTime | |
| updated_at | DateTime | |

#### Table: `alerts`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| zone_id | String | |
| domain | ENUM | |
| node_id | String | |
| field | String | |
| value | Float | |
| threshold | String | |
| severity | ENUM | INFO, WARNING, CRITICAL |
| message | Text | |
| created_at | DateTime | |
| acknowledged | Boolean | Default false |

---

### Complete API Route Table

#### Auth (Public)
| Method | Route | Description |
|---|---|---|
| POST | `/auth/register` | Resident self-registration |
| POST | `/auth/login` | Returns JWT access + refresh token |
| POST | `/auth/refresh` | Refresh token exchange |
| GET | `/users/me` | Current user profile |

#### Manager Routes
| Method | Route | Description |
|---|---|---|
| POST | `/manager/create-user` | Create Analyst or Servicer |
| GET | `/manager/team` | List team members |
| PUT | `/manager/users/{id}/deactivate` | Deactivate member |
| POST | `/manager/assignments` | Assign node to Servicer |
| GET | `/manager/assignments` | List all assignments |
| PUT | `/manager/assignments/{id}` | Update status/notes |

#### Resident Routes
| Method | Route | Description |
|---|---|---|
| POST | `/resident/subscriptions` | Create subscription |
| GET | `/resident/subscriptions` | List my subscriptions |
| PUT | `/resident/subscriptions/{id}` | Update |
| DELETE | `/resident/subscriptions/{id}` | Remove |

#### Servicer Routes
| Method | Route | Description |
|---|---|---|
| GET | `/servicer/assignments` | My assignments |
| PUT | `/servicer/assignments/{id}/status` | Update status |
| PUT | `/servicer/assignments/{id}/notes` | Add notes |

#### Actuator Control (NEW)
| Method | Route | Access | Description |
|---|---|---|---|
| PATCH | `/actuators/{node_id}/command` | RESIDENT (subscribed zone), SERVICER (assigned), MANAGER | Send ON/OFF/value command |
| GET | `/actuators/{node_id}/state` | Same as above | Last known state from Middleware |

#### Dashboard Routes
| Method | Route | Access | Description |
|---|---|---|---|
| GET | `/dashboard/resident` | RESIDENT | Summary + alerts for subscribed zones |
| GET | `/dashboard/analyst` | ANALYST, MANAGER | Trends + KPIs + predictions |
| GET | `/dashboard/servicer` | SERVICER, MANAGER | Node map + health per assigned domain |
| GET | `/dashboard/manager/team` | MANAGER | Team + assignment overview |
| GET | `/dashboard/alerts` | RESIDENT | Active alerts for my subscriptions |

#### Alert Routes
| Method | Route | Access | Description |
|---|---|---|---|
| POST | `/internal/alerts` | Internal (API key) | Domain Engines post alert here |
| GET | `/alerts/history` | MANAGER | Full alert log |
| PUT | `/alerts/{id}/acknowledge` | Any auth user | Mark alert as acknowledged |

---

### File Structure
```
UserService/
├── main.py
├── requirements.txt
├── .env                      # SECRET_KEY, TWILIO_*, SENDGRID_*, INTERNAL_API_KEY
├── core/
│   ├── config.py             # Reads .env
│   ├── security.py           # JWT + bcrypt
│   └── dependencies.py       # get_current_user(), require_role()
├── database/
│   ├── db.py                 # SQLAlchemy + SQLite
│   └── models.py             # All 4 ORM tables
├── schemas/
│   ├── auth.py
│   ├── user.py
│   ├── subscription.py
│   ├── assignment.py
│   ├── alert.py
│   └── actuator.py           # ActuatorCommandRequest
├── routers/
│   ├── auth.py
│   ├── manager.py
│   ├── resident.py
│   ├── servicer.py
│   ├── actuators.py          # NEW: actuator toggle
│   ├── dashboard.py
│   └── alerts.py
└── services/
    ├── dashboard_service.py  # Reads from PersistentMiddleware :8001
    ├── actuator_service.py   # Access check + forwards to IngestionEngine
    ├── alert_service.py      # Receives from Engines, fans out SMS/Email/in-app
    ├── twilio_service.py
    └── sendgrid_service.py
```

---

## Flutter App Changes (Actuator Toggle)

### Where toggles appear

| Dashboard | Location | Condition |
|---|---|---|
| ResidentDashboardDecorator | Inside node detail card | Node is actuator + in subscribed zone |
| ServicerDashboardDecorator | Node Detail Drawer (tap map pin) | Node is in servicer's assignments |
| ManagerDashboardDecorator | Node Detail Drawer (all domains) | Always visible |

### Toggle Widget (reusable)
```dart
class ActuatorToggleWidget extends StatelessWidget {
  final String nodeId;
  final String currentState;   // "ON" / "OFF" / "OPEN" / "CLOSED"
  final String field;          // "state"
  // Calls PATCH /actuators/{nodeId}/command
  // Shows loading spinner → success/fail snackbar
}
```

### Updated Dashboard Wireframes

**RESIDENT — with actuator panel**
```
┌─────────────────────────────────────┐
│  My Subscriptions  [BLK-A] [LIB]   │
│  Energy ✓  Water ✓  Air □           │
├─────────────────────────────────────┤
│  Summary cards (filtered by zones)  │
├─────────────────────────────────────┤
│  🔔 Alerts (2)                      │
│  • PM2.5 high BLK-A — 13:22        │
├─────────────────────────────────────┤
│  [Chart: 24h trend]                 │
├─────────────────────────────────────┤
│  🕹 Actuators in my zones           │
│  AC-001  BLK-A  [ON  ●────○ OFF]   │  ← toggle
│  LIGHT-003 LIB  [ON  ●────○ OFF]   │
└─────────────────────────────────────┘
```

**SERVICER — node detail drawer (tap map pin)**
```
┌────────────────────────────┐
│  Node: AC-001              │
│  Type: ac_unit             │
│  Zone: BLK-A               │
│  Health: ✅ OK              │
│  Last seen: 13:28          │
│  ─────────────────         │
│  State:  [ON  ●────○ OFF]  │  ← toggle (only if assigned)
│  Temp:   24°C              │
│  Power:  1450W             │
│  ─────────────────         │
│  Assignment: IN_PROGRESS   │
│  [Update Status] [Notes]   │
└────────────────────────────┘
```

---

## Implementation Order (Updated)

### Phase 1 — UserService Backend
1. `[ ]` Bootstrap FastAPI + SQLite
2. `[ ]` ORM models: User, Subscription, ServicerAssignment, Alert
3. `[ ]` JWT security core
4. `[ ]` `/auth/*`
5. `[ ]` `/manager/*`
6. `[ ]` `/resident/subscriptions`
7. `[ ]` `/servicer/assignments`
8. `[ ]` `dashboard_service.py` + `/dashboard/*`
9. `[ ]` `alert_service.py` + `/internal/alerts` + `/alerts/*`
10. `[ ]` `twilio_service.py` + `sendgrid_service.py`
11. `[ ]` `actuator_service.py` + `/actuators/*`

### Phase 2 — IngestionEngine Updates
1. `[ ]` Add `pending_commands: dict` in-memory store
2. `[ ]` `POST /api/actuator/{node_id}/command` endpoint
3. `[ ]` Update `websocket_adapter.py` to embed command in ACK

### Phase 3 — Simulator Updates
1. `[ ]` Update `WebSocketSender` to read `command` from ACK
2. `[ ]` Add `NodeSimulator.apply_command(field, value)`

### Phase 4 — Flutter App
1. `[ ]` Scaffold + go_router + flutter_riverpod
2. `[ ]` AuthProvider (JWT, role, refresh)
3. `[ ]` Login + Register screens
4. `[ ]` BaseDashboardView + all 4 Decorators
5. `[ ]` `ActuatorToggleWidget` (reusable)
6. `[ ]` Wire toggles into Resident + Servicer + Manager dashboards
7. `[ ]` Alert provider + alert feed
8. `[ ]` TeamManagementPanel

---

## Port Registry (Full System)
| Service | Port | Notes |
|---|---|---|
| IngestionEngine | 8000 | HTTP + WS + CoAP UDP 5683 |
| PersistentMiddleware | 8001 | HTTP REST |
| UserService | 8003 | HTTP REST |
| RabbitMQ AMQP | 5672 | |
| RabbitMQ Management UI | 15672 | |
| Embedded MQTT Broker | 1883 | Inside IngestionEngine |

---

## What is Still Missing (Honest Assessment)

| Gap | Impact | Fix When |
|---|---|---|
| Domain Engines don't POST alerts yet | Alerts won't flow until EHSEngine/EnergyEngine are updated | Phase 1 end |
| CoAP/HTTP actuator nodes can't receive commands via WS | Only WS-connected actuators respond to toggle | Phase 3 — add command delivery via HTTP polling |
| No alert deduplication | Same alert fires on every engine run cycle | Phase 1 polish |
| Flutter has no push notifications | User must open app to see alerts | Future: FCM integration |
| Simulator `apply_command` only overrides generators, doesn't persist | Simulated state reverts on next generator tick | Phase 3 — add `forced_value` flag |
