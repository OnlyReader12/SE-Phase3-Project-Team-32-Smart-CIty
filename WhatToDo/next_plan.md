# Smart City — Next Implementation Plan
## Gap Audit + Task Breakdown for 5 Features

---

## Feature Status Summary

| # | Feature | Status | Gap |
|---|---|---|---|
| 1 | Manager: Browse team nodes + schedule assignments | 🟡 **Partial** | Backend exists; Flutter UI has no node browser or assignment create flow |
| 2 | All users: Toggle + node report + alert + history | 🟡 **Partial** | Backend endpoint exists; Flutter uses hardcoded node IDs; history screen missing |
| 3 | Resident: Search → Subscribe / Unsubscribe nodes | 🔴 **Missing** | No browse-nodes-then-subscribe UI; SubscriptionPanel is static |
| 4 | IoT data triggers engine rules → graphs render | 🟡 **Partial** | Engine rules exist; middleware client fixed; chart shows 0s because engine has no live data yet |
| 5 | In-app + SMS + Email alert subsystem (Twilio) | 🟡 **Partial** | Twilio stub exists; no event bus; no in-app notification bell; no delivery log |

---

## Feature 1 — Manager: Browse Nodes + Schedule Assignments

### What Exists ✅
- `POST /manager/assignments` — create assignment
- `GET /manager/team` — list team members (but filtered by `created_by`, misses seeded users)
- `GET /manager/assignments` — list assignments
- Flutter `_TeamPanel` — shows members and their existing assignments

### What Is Missing ❌
- No API to browse all nodes under the engine team
- No Flutter UI to pick a node and assign it to a technician
- `/manager/team` uses `created_by` filter — misses seeded users not created by this manager

### Tasks

**Backend — UserService**
- [ ] `GET /manager/nodes` — proxy to Middleware `/domain/{team_domain}`, returns live node list for manager's team
- [ ] Fix `/manager/team` filter: change from `created_by == me.id` to `team == me.team AND role != MANAGER`
- [ ] Add `zone_id` to `AssignmentCreate` schema (field exists in model, missing from schema)

**Flutter — `manager_dashboard.dart`**
- [ ] Add "Assign Node" IconButton to each `_MemberCard` (per Servicer)
- [ ] New `_AssignNodeSheet` bottom sheet:
  - Fetches `GET /manager/nodes` → shows node list with zone/health/status
  - Lets manager pick a node → select Servicer → POST assignment
- [ ] New `_NodeBrowserTab` (4th tab in ManagerDashboard): Full team node list with health badges

---

## Feature 2 — All Users: Toggle + Node Report + Alert + History

### What Exists ✅
- `PATCH /actuators/{node_id}/command` — toggle (team-scoped)
- `GET /actuators/{node_id}/state` — current state
- `GET /history/{node_id}` on Middleware — time series data
- Flutter `ActuatorToggle` widget
- Flutter `AlertFeed` widget

### What Is Missing ❌
- Resident dashboard shows hardcoded `AC-UNIT-001` and `INDOOR-LIGHT-001` — not live
- No `NodeDetailScreen` — clicking a node should show: telemetry + toggle + 24h chart
- Manager/Servicer: no node-list-with-toggle screen (only dashboard summaries)
- Analyst: no "Node Report" drilldown (read-only detail view)
- No `GET /nodes/my` endpoint that returns the correct scoped node list per role

### Tasks

**Backend — UserService — new `routers/nodes.py`**
- [ ] `GET /nodes/my` — role-aware node list:
  - MANAGER/ANALYST → all nodes in team domain from Middleware
  - SERVICER → nodes from active assignments only
  - RESIDENT/SMART_USER → nodes in subscribed zones + domains
- [ ] `GET /nodes/{node_id}/history` — proxy to Middleware `/history/{node_id}`

**Flutter**
- [ ] New `NodeDetailScreen`:
  - Header: node_id, type, zone, health badge (🟢🟡🔴)
  - Toggle switch (shown only if role has actuator access)
  - Telemetry cards showing latest payload fields
  - 24h history `LineChart` via `fl_chart`
  - Alert history list for this specific node
- [ ] Fix `ResidentDashboard._buildActuators`: Replace hardcoded nodes with live `GET /nodes/my`
- [ ] `ServicerDashboard`: Each node card navigates to `NodeDetailScreen`
- [ ] `AnalystDashboard`: Add "Raw Nodes" tab — read-only data table per node
- [ ] `ManagerDashboard`: Navigate to `NodeDetailScreen` from Health Map tab

---

## Feature 3 — Resident: Search Node → Subscribe / Unsubscribe

### What Exists ✅
- `POST /resident/subscriptions` — create subscription
- `DELETE /resident/subscriptions/{id}` — delete subscription
- `SubscriptionPanel` widget — shows existing subscriptions (static)

### What Is Missing ❌
- No `GET /nodes/browse` endpoint for zone/domain discovery
- No search/browse UI for residents to discover what zones exist
- `SubscriptionPanel` cannot discover and subscribe to new zones

### Tasks

**Backend — UserService — add to `routers/nodes.py`**
- [ ] `GET /nodes/browse` — public catalog of all zones + domains:
  ```json
  { "zones": ["BLK-A", "BLK-B", "LIB", ...], "domains": ["energy", "water", "air"] }
  ```
- [ ] `GET /nodes/browse/{zone_id}` — nodes in that zone with type/health/last_seen

**Flutter — `subscription_panel.dart` full rewrite**
- [ ] Search bar with zone filter
- [ ] Zone list from `GET /nodes/browse`, grouped by domain
- [ ] Zone card with domain badges (⚡ 💧 🌬️) and Subscribe/Unsubscribe toggles
- [ ] Subscribed zones shown first with distinct styling
- [ ] On Subscribe: `POST /resident/subscriptions` with selected zone + domain
- [ ] On Unsubscribe: `DELETE /resident/subscriptions/{id}`
- [ ] Node count + last-seen shown per zone card

---

## Feature 4 — IoT Data Triggers Engine Rules → Graphs Render

### What Exists ✅
- All 5 engine rules coded per engine
- `MiddlewareClient.fetch_latest` fixed to call `/domain/{domain}`
- Analyst dashboard charts coded with `fl_chart`
- `BaseEngine` analysis loop runs every 30s
- `MetricsService.simple_moving_average` for trend calculation

### What Is Missing ❌

**Data Pipeline Gaps:**
- Simulator → IngestionEngine → RabbitMQ → Middleware chain may be broken (no data in Middleware = engine gets 0 nodes)
- Dashboard data source mismatch: Analyst Flutter calls UserService `/dashboard/analyst` which calls Middleware directly — NOT the engine `/metrics/summary`
- `AlertIn` schema uses `Domain` enum which only accepts `energy`, `water`, `air` — EHS engine sends `'ehs'` causing crash
- Charts show flat lines because `prediction_3_readings` is SMA of one data point

### Tasks

**Debugging (do FIRST)**
- [ ] Verify pipeline: `curl :8001/domain/energy` → should return nodes
- [ ] Verify: `curl :8004/health` → `nodes_cached` should be > 0
- [ ] Verify: `curl :8004/metrics/summary` → non-zero KPIs
- [ ] Fix `AlertIn.domain` field in `schemas.py`: change from `Domain` enum to `str`

**Backend**
- [ ] UserService `GET /dashboard/analyst` — proxy to Engine `/metrics/summary` instead of calling Middleware directly (or merge both)
- [ ] Add `GET /dashboard/analyst/timeseries?node_id=X&param=Y` proxy to Engine `/metrics/timeseries`

**Flutter**
- [ ] `analystDashboardProvider` — call Engine APIs (`:8004`/`:8005`) directly for real metrics
- [ ] Replace `prediction_3_readings` chart with actual time-series `LineChart` from `GET /metrics/timeseries`
- [ ] Add threshold slider (`Slider` widget) per rule wired to `PUT /thresholds/{rule_id}`
- [ ] Confirm Simulator sends to `:8000` (IngestionEngine) not `:8001` (Middleware)

---

## Feature 5 — Alert & Notification Subsystem

### What Exists ✅
- `process_alert()` in `alert_service.py` — persists + routes by team/subscription
- `send_sms()` stub in `twilio_service.py`
- `send_email()` stub in `sendgrid_service.py`
- `AlertFeed` widget in Flutter
- `Alert` DB table

### What Is Missing ❌
- No in-app notification bell (badge count) in Flutter AppBar
- No `GET /alerts/my` endpoint scoped to logged-in user
- Flutter alerts fetched once on load only — no live polling
- No `AlertDeliveryLog` table — can't audit who was notified
- No cooldown/deduplication — engine fires same alert every 30s creating duplicates
- Alert logic scattered across 3 files — needs to be a proper subsystem

### Tasks

**Backend — Refactor into `AlertSubsystem`**
- [ ] `AlertDeliveryLog` model — track: `alert_id`, `user_id`, `channel` (in_app/sms/email), `status` (sent/failed/rate_limited), `attempted_at`
- [ ] Cooldown store — in-memory dict: `(rule_id, node_id)` → `last_triggered_at`, suppress if < 5 min ago
- [ ] `GET /alerts/my` — filter by role:
  - MANAGER/ANALYST: alerts where `domain IN team_domains`
  - SERVICER: alerts where `node_id IN assigned_nodes`
  - RESIDENT/SMART_USER: alerts where `zone_id IN subscribed_zones`
- [ ] `PUT /alerts/{id}/acknowledge` — mark as read, record `acknowledged_by`
- [ ] SMS rate limiter — max 3 SMS per user per hour
- [ ] Email severity filter — only WARNING + CRITICAL, never INFO
- [ ] Auto-ack background job — marks alerts older than 24h as `auto_acked=True`

**Flutter — Notification System**
- [ ] `notification_bell.dart` — AppBar icon showing unread count badge
  - Polls `GET /alerts/my?acknowledged=false` every 30s
  - Red badge with count
- [ ] `NotificationPanel` — full-screen or slide-in panel:
  - CRITICAL: red card with pulse border
  - WARNING: amber card
  - INFO: blue card
  - Tap → mark as ACK'd via `PUT /alerts/{id}/acknowledge`
  - "Mark All Read" button
- [ ] After ACK: card moves to greyed-out "History" section inline
- [ ] Add `notification_provider.dart` Riverpod provider with auto-refresh

---

## Implementation Order

```
Phase A — Fix the data pipeline (unblocks graphs + alerts)
  A1. Verify Simulator → Ingestion → Middleware → Engine chain
  A2. Fix AlertIn.domain from Enum to str in schemas.py
  A3. Add GET /nodes/my and GET /nodes/browse endpoints

Phase B — Core user flows
  B1. Feature 1: Fix /manager/team filter + node browser + assign sheet Flutter UI
  B2. Feature 2: NodeDetailScreen + live node list
  B3. Feature 3: Resident SubscriptionPanel rewrite

Phase C — Graphs
  C1. Point Flutter at Engine APIs for real metrics
  C2. Replace prediction chart with actual timeseries LineChart
  C3. Add threshold slider widgets

Phase D — Alert subsystem
  D1. Add AlertDeliveryLog + cooldown + GET /alerts/my
  D2. Flutter notification bell + NotificationPanel
  D3. Wire Twilio SMS with rate limiter
  D4. Wire SendGrid email
```

---

## New Files to Create

| File | Purpose |
|---|---|
| `UserService/routers/nodes.py` | `GET /nodes/my`, `/nodes/browse`, `/nodes/{id}/history` |
| `flutter_app/lib/screens/node_detail_screen.dart` | Node detail + toggle + time-series chart |
| `flutter_app/lib/widgets/notification_bell.dart` | AppBar bell with unread badge |
| `flutter_app/lib/screens/notification_panel.dart` | Full notification list |
| `flutter_app/lib/providers/notification_provider.dart` | Riverpod auto-refresh provider |

## Files to Modify

| File | Change |
|---|---|
| `UserService/routers/manager.py` | Fix `/team` filter scope to `team` column |
| `UserService/schemas.py` | Fix `AlertIn.domain` to `str`; add `NodeOut` schema |
| `UserService/services/alert_service.py` | Add cooldown + delivery log |
| `UserService/database/models.py` | Add `AlertDeliveryLog` table |
| `flutter_app/lib/providers/dashboard_provider.dart` | Add `myNodesProvider`, `notificationProvider` |
| `flutter_app/lib/screens/dashboard/manager_dashboard.dart` | + node browser tab + assign sheet |
| `flutter_app/lib/screens/dashboard/resident_dashboard.dart` | Replace hardcoded actuators |
| `flutter_app/lib/widgets/subscription_panel.dart` | Full rewrite with search + subscribe |
