# 🧪 Smart City — Manual Test Scenarios

Each scenario tells you exactly what to **do** and what you should **see**. 
Run them in order after all services are running.

> **Prerequisites:** All 6 services running + Simulator active.  
> **Tools needed:** Browser, one open terminal for `curl`.

---

## 🟢 PHASE 1 — Infrastructure Verification

### T-01: Ingestion Engine is alive
**Activity:** Open browser → `http://127.0.0.1:8000/docs`  
**Expected:** Swagger UI loads. You can see endpoints like `/ingest/http`, `/health`.

---

### T-02: Persistent Middleware is storing data
**Activity:** Wait 35 seconds after simulator starts, then open:  
`http://127.0.0.1:8001/api/nodes/latest`  
**Expected:** A JSON list of node readings. You should see 50–100 entries with fields like `node_id`, `zone`, `data`.

---

### T-03: Node count grows over time
**Activity:** Open `http://127.0.0.1:8001/api/nodes/latest` twice — 30 seconds apart.  
**Expected:** The `timestamp` fields in the second response are newer. Data is being updated as the simulator publishes.

---

### T-04: Engines are running
**Activity:** Open `http://127.0.0.1:8004/health` and `http://127.0.0.1:8005/health`  
**Expected for Energy Engine:**
```json
{ "engine": "EnergyManagementEngine", "rules": ["power_balance","ac_efficiency","light_waste","battery_health","ev_peak_load"], "nodes_cached": <N> }
```
**Expected for EHS Engine:**
```json
{ "engine": "EHSEngine", "rules": ["air_quality","indoor_comfort","water_safety","water_quality","equipment_health"], "nodes_cached": <N> }
```

---

## 🔐 PHASE 2 — Authentication (UserService)

### T-05: Resident self-registration
**Activity:** Open `http://127.0.0.1:8003/docs` → `POST /auth/register`  
Fill:
```json
{ "email": "newuser@test.com", "full_name": "Test Resident", "password": "test1234" }
```
**Expected:** `201 Created`. Response contains `access_token` and `role: RESIDENT`.

---

### T-06: Login with seeded Manager account
**Activity:** `POST /auth/login`
```json
{ "email": "manager@city.com", "password": "password123" }
```
**Expected:** `200 OK`. Copy the `access_token` — you'll use it in next tests.

---

### T-07: Role is enforced — Resident cannot create users
**Activity:** Login as `resident@city.com`. Then call `POST /manager/create-user` with any body.  
**Expected:** `403 Forbidden`. Message: "Insufficient role".

---

### T-08: Token refresh works
**Activity:** Login → copy `refresh_token`. Call `POST /auth/refresh` with `{"refresh_token": "<your_token>"}`.  
**Expected:** `200 OK` with a new `access_token`.

---

## 🏠 PHASE 3 — Resident User Flow

### T-09: Resident creates a zone subscription
**Activity:** Login as `resident@city.com`. Call `POST /resident/subscriptions`:
```json
{
  "zone_ids": ["BLK-A"],
  "engine_types": ["energy"],
  "alert_in_app": true,
  "alert_sms": false,
  "alert_email": false
}
```
**Expected:** `201 Created`. Subscription ID returned.

---

### T-10: Resident sees filtered dashboard data
**Activity:** Call `GET /dashboard/resident` with the Resident token.  
**Expected:** JSON with `summary` and `alerts` scoped only to `BLK-A` zone. Data from other zones (e.g., `HOSTEL-N`) should NOT appear.

---

### T-11: Resident sees subscription list
**Activity:** `GET /resident/subscriptions`  
**Expected:** List with the subscription created in T-09. Contains `zone_ids: ["BLK-A"]`.

---

## 👑 PHASE 4 — Manager User Flow

### T-12: Manager creates a Servicer account
**Activity:** Login as `manager@city.com`. Call `POST /manager/create-user`:
```json
{
  "email": "newtech@city.com",
  "full_name": "New Technician",
  "password": "tech1234",
  "role": "SERVICER"
}
```
**Expected:** `201 Created`. Role is `SERVICER`. This user is now in the Manager's team.

---

### T-13: Manager sees their team
**Activity:** `GET /manager/team`  
**Expected:** List includes `newtech@city.com`. Does NOT include `resident@city.com` (not created by this manager).

---

### T-14: Manager assigns a node to a Servicer
**Activity:** `POST /manager/assignments`:
```json
{
  "servicer_id": <id of newtech@city.com>,
  "node_id": "AC-UNIT-001",
  "zone_id": "BLK-A",
  "notes": "Check AC unit in Block A, reported inefficiency"
}
```
**Expected:** `201 Created`. Assignment created with `status: PENDING`.

---

### T-15: Manager views full alert history
**Activity:** `GET /alerts/history`  
**Expected:** List of all alerts across all zones. Not filtered by zone (unlike Resident view).

---

## 🛠️ PHASE 5 — Servicer (Technician) Flow

### T-16: Servicer sees their assigned nodes
**Activity:** Login as `servicer@city.com` (or the newly created `newtech@city.com`). Call `GET /servicer/assignments`.  
**Expected:** List contains the `AC-UNIT-001` assignment from T-14.

---

### T-17: Servicer updates assignment status
**Activity:** `PUT /servicer/assignments/{id}/status`  
Body: `{"status": "IN_PROGRESS"}`  
**Expected:** `200 OK`. Status is now `IN_PROGRESS`.

---

### T-18: Servicer adds field notes  
**Activity:** `PUT /servicer/assignments/{id}/notes`  
Body: `{"notes": "Visited site. AC filter is clogged. Scheduling replacement."}`  
**Expected:** `200 OK`. Notes persisted.

---

### T-19: Servicer views their Health Dashboard
**Activity:** `GET /dashboard/servicer`  
**Expected:** JSON with `nodes` (only their assigned nodes) and a `summary` object with `{total, healthy, degraded, offline}` counts.

---

## 📈 PHASE 6 — Analyst User Flow

### T-20: Analyst views energy metrics summary
**Activity:** Open `http://127.0.0.1:8004/metrics/summary`  
**Expected:** JSON with:
```json
{
  "solar_generation_kw": <float>,
  "total_consumption_kw": <float>,
  "net_balance_kw": <float>,
  "avg_battery_soc_pct": <float or null>,
  "recent_alerts": <int>
}
```

---

### T-21: Analyst views EHS air quality summary
**Activity:** Open `http://127.0.0.1:8005/metrics/summary`  
**Expected:** JSON with `avg_pm2_5_ugm3`, `water_quality_score`, `dry_run_risk_nodes`.

---

### T-22: Analyst reads current thresholds (slider defaults)
**Activity:** `GET http://127.0.0.1:8004/thresholds`  
**Expected:** JSON with all 5 rule threshold maps:
```json
{
  "power_balance": { "solar_drop_pct": 40, ... },
  "ac_efficiency":  { "efficiency_min_delta_c": 1.0, ... },
  ...
}
```

---

### T-23: Analyst tightens a threshold (slider action)
**Activity:** `PUT http://127.0.0.1:8005/thresholds/air_quality?key=pm2_5_warning_ugm3&value=15`  
**Expected:** `200 OK` with `{ "updated": true, "rule_id": "air_quality", "key": "pm2_5_warning_ugm3", "value": 15 }`.  
**Then verify:** `GET /thresholds` → `air_quality.pm2_5_warning_ugm3` is now `15`.  
**Effect:** Next engine cycle will trigger alerts at 15 μg/m³ instead of 25.

---

### T-24: Analyst can NOT access Resident subscription API
**Activity:** Login as `analyst@city.com`. Call `POST /resident/subscriptions` with any body.  
**Expected:** `403 Forbidden`.

---

## 🚨 PHASE 7 — Alert Flow

### T-25: Engine triggers alert and it appears in UserService
**Activity:**  
1. Set a very low threshold: `PUT http://127.0.0.1:8004/thresholds/battery_health?key=low_soc_pct&value=99`  
2. Wait 35 seconds (next engine cycle).  
3. Call `GET http://127.0.0.1:8003/alerts/history` (as Manager).  
**Expected:** A new alert appears with `rule_id: battery_health` and `severity: CRITICAL`.

> This verifies the full Engine → UserService alert pipeline.

---

### T-26: Alert appears in Resident's in-app feed
**Activity:**  
1. Ensure Resident has a subscription for a zone where an alert was triggered.  
2. `GET /dashboard/resident` (as `resident@city.com`).  
**Expected:** `alerts` array is non-empty. Alert has `severity`, `message`, `zone_id`.

---

## 🕹️ PHASE 8 — Actuator Control

### T-27: Resident toggles an actuator in their zone
**Activity:** Login as `resident@city.com`. Call:  
`PATCH /actuators/AC-UNIT-001/command`  
Body: `{"field": "state", "value": "OFF"}`  
**Expected:** `200 OK`. Command acknowledged.

---

### T-28: Servicer cannot control a node outside their assignments
**Activity:** Login as `servicer@city.com`. Try to control a node NOT in their assignment list:  
`PATCH /actuators/SOLAR-PANEL-001/command`  
Body: `{"field": "state", "value": "OFF"}`  
**Expected:** `403 Forbidden`. Solar panels are not assigned to this servicer.

---

### T-29: Manager has full actuator access
**Activity:** Login as `manager@city.com`. Control any node:  
`PATCH /actuators/WATER-PUMP-001/command`  
Body: `{"field": "state", "value": "OFF"}`  
**Expected:** `200 OK`. Managers can control any node.

---

## 📱 PHASE 9 — Flutter App (Manual UI Check)

### T-30: Login screen renders
**Activity:** Open `http://localhost:8080`  
**Expected:** Dark-themed login screen with email/password fields and a "Login" button.

---

### T-31: Resident login shows Resident Dashboard
**Activity:** Enter `resident@city.com` / `password123` → Login.  
**Expected:** Redirected to Resident Dashboard. Shows `My Subscriptions` panel with zone chips and domain toggles.

---

### T-32: Analyst login shows Analytics Dashboard
**Activity:** Logout → Login as `analyst@city.com`.  
**Expected:** Analyst Dashboard with energy/water/air tabs. Charts visible (may show empty state if no history data yet).

---

### T-33: Servicer login shows Node Health view
**Activity:** Login as `servicer@city.com`.  
**Expected:** Servicer Dashboard with Zone Node Grid. Each zone shows coloured dots (🟢 green / 🟡 amber / 🔴 red). Assignment list visible on right panel.

---

### T-34: Manager login shows combined view
**Activity:** Login as `manager@city.com`.  
**Expected:** Manager Dashboard with two tab groups — "Analytics" and "Node Health". Team management section visible.

---

## ✅ Test Results Tracker

| Test | Pass / Fail | Notes |
|---|---|---|
| T-01 Ingestion alive | | |
| T-02 Middleware storing data | | |
| T-03 Node count grows | | |
| T-04 Engines running | | |
| T-05 Resident registration | | |
| T-06 Manager login | | |
| T-07 Role enforcement | | |
| T-08 Token refresh | | |
| T-09 Resident subscription | | |
| T-10 Resident filtered dash | | |
| T-11 Subscription list | | |
| T-12 Manager creates Servicer | | |
| T-13 Manager sees team | | |
| T-14 Node assignment | | |
| T-15 Alert history | | |
| T-16 Servicer assignments | | |
| T-17 Status update | | |
| T-18 Field notes | | |
| T-19 Servicer health dash | | |
| T-20 Energy metrics | | |
| T-21 EHS air quality metrics | | |
| T-22 Thresholds read | | |
| T-23 Threshold update | | |
| T-24 Analyst access control | | |
| T-25 Alert pipeline | | |
| T-26 Resident alert feed | | |
| T-27 Resident actuator | | |
| T-28 Servicer access control | | |
| T-29 Manager full access | | |
| T-30 Login screen | | |
| T-31 Resident Flutter dash | | |
| T-32 Analyst Flutter dash | | |
| T-33 Servicer Flutter dash | | |
| T-34 Manager Flutter dash | | |
