# Smart City — Data & Control Flow Audit

## Flow Map

```
Simulator (IOTDataGenerator/)
   │
   ├─ MQTT  ─────────────────────────────────────────┐
   ├─ HTTP POST :8000/api/telemetry ─────────────────┤
   ├─ CoAP UDP :5683/telemetry ──────────────────────┤──▶ IngestionEngine (:8000)
   └─ WebSocket ws://8000/ws/actuator ───────────────┘         │
        (actuator nodes stream their state here)               │ RabbitMQ
                                                               ▼
                                                   PersistentMiddleware (:8001)
                                                          SQLite DB
                                                               │
                   ┌───────────────────────────────────────────┤
                   │                                           │
                   ▼                                           ▼
         EnergyEngine (:8004)                       EHSEngine (:8005)
         polls GET /domain/energy                  polls GET /domain/water+air
               every 30s                                every 30s
                   │                                           │
                   ▼ POST /internal/alerts                     ▼ POST /internal/alerts
                                                               
                   UserService (:8003)
                        │
                        ├── GET /dashboard/analyst → calls Middleware /domain/{X}
                        ├── GET /alerts/my
                        ├── GET /nodes/my → calls Middleware /domain/{X}
                        ├── GET /nodes/browse → calls Middleware /domain/energy+water+air
                        ├── GET /nodes/{id}/history → calls Middleware /history/{id}
                        └── PATCH /actuators/{id}/command
                                    │
                                    ▼ POST /api/actuator/{node_id}/command   ⚠️ BROKEN
                             IngestionEngine (:8000)
                             (endpoint does NOT exist yet)

Flutter (:3000 or device) ─── All calls → UserService :8003 (kBaseUrl)
```

---

## Flow Status Table

| Flow | Status | Issue |
|------|--------|-------|
| **Simulator → IngestionEngine (HTTP)** | ✅ WORKS | `POST :8000/api/telemetry` exists |
| **Simulator → IngestionEngine (MQTT)** | ✅ WORKS | Embedded broker + Paho adapter |
| **Simulator → IngestionEngine (CoAP)** | ✅ WORKS | aiocoap server |
| **Simulator → IngestionEngine (WebSocket)** | ✅ WORKS | `ws://8000/ws/actuator` |
| **IngestionEngine → RabbitMQ → Middleware** | ✅ WORKS | `RabbitMQForwarder` → `amqp_consumer` |
| **Middleware SQLite persistence** | ✅ WORKS | `GET /domain/{domain}` returns latest per node |
| **Engine polls Middleware** | ✅ WORKS | `MiddlewareClient.fetch_latest()` calls `/domain/{domain}` |
| **Engine rule analysis** | ✅ WORKS | `BaseEngine._run_cycle()` runs every 30s |
| **Engine → UserService alerts** | ✅ WORKS (now) | `POST /internal/alerts` fixed (domain = str, not enum) |
| **Alert service → DB** | ✅ WORKS (now) | `process_alert()` with cooldown + delivery log |
| **Flutter → UserService GET /alerts/my** | ✅ WORKS (now) | `myAlertsProvider` calls `GET /alerts/my` |
| **Flutter → UserService GET /dashboard/analyst** | ✅ WORKS | Calls Middleware `/domain/{X}`, returns analytics |
| **Flutter → UserService GET /nodes/my** | ✅ WORKS (now) | New endpoint, proxies Middleware |
| **Flutter → UserService GET /nodes/browse** | ✅ WORKS (now) | New endpoint, returns zone catalog |
| **Flutter → UserService PATCH /actuators** | ✅ WORKS | `actuator_service._check_access()` then forwards |
| **UserService → IngestionEngine actuator command** | 🔴 **BROKEN** | `POST :8000/api/actuator/{id}/command` does NOT exist on IngestionEngine |
| **IngestionEngine → Simulator (command delivery)** | 🔴 **BROKEN** | No pending_commands dict or WebSocket push to specific node |

---

## Root Cause: Toggle Flow is Broken

The toggle flow is:
```
Flutter → PATCH /actuators/{node_id}/command (UserService)
       → POST :8000/api/actuator/{node_id}/command (IngestionEngine) ← MISSING
       → push command to Simulator node via WebSocket               ← MISSING
```

**IngestionEngine has NO REST endpoint to receive actuator commands.**
It only has `ws://8000/ws/actuator` where Simulator NODES PUSH their state TO the engine.
There is no reverse path: engine → simulator node.

### Fix Applied
Added `POST /api/actuator/{node_id}/command` to IngestionEngine.
For now this stores the command in an in-memory `pending_commands` dict.
The WebSocket `ws/actuator` handler checks this dict and sends the command
as a JSON frame when the matching node connects (it connects every tick).

---

## Analyst Dashboard Chart Data Source

**Current**: Flutter `analystDashboardProvider` calls `GET /dashboard/analyst`
which calls `Middleware /domain/{X}` and computes SMA from a single time point.

**Result**: Charts show flat lines / 0s because only the latest reading per node
is used, not historical data.

**Fix Applied**: Added `GET /dashboard/analyst/timeseries` endpoint that proxies
`GET :8001/history/{node_id}` — Flutter uses this for real LineChart data.
