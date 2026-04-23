# 🔔 Alert Sources — What Triggers an Alert

This document defines every event that can produce an alert in the system, with the exact trigger condition, severity, and metadata produced.

---

## 1. 🧠 DOMAIN Alerts — Engine Rule Violations

**Source:** `EnergyManagementEngine` (:8004) or `EHSEngine` (:8005)  
**How:** `POST /internal/alerts` on UserService after each 30s analysis cycle  
**Cooldown:** 5 minutes per `(rule_id + node_id)` pair  

### Energy Engine Triggers

| Rule | Event | Severity |
|---|---|---|
| `power_balance` | Consumption > Generation for 10 min | `WARNING` |
| `power_balance` | Grid load > 90% | `CRITICAL` |
| `ac_efficiency` | AC high power + low cooling delta | `WARNING` |
| `ac_efficiency` | AC room still >5°C above setpoint | `CRITICAL` |
| `light_waste` | Lights ON + zero occupancy > 5 min | `WARNING` |
| `light_waste` | Outdoor lamp ON in daylight | `INFO` |
| `battery_health` | SOC < 20% during peak hours | `CRITICAL` |
| `ev_peak_load` | >3 EV chargers simultaneously active | `WARNING` |
| `ev_peak_load` | EV load + grid > 80% | `CRITICAL` |

### EHS Engine Triggers

| Rule | Event | Severity |
|---|---|---|
| `air_quality` | PM2.5 > 25 μg/m³ | `WARNING` |
| `air_quality` | PM2.5 > 50 μg/m³ | `CRITICAL` |
| `air_quality` | CO2 > 800 ppm | `WARNING` |
| `air_quality` | CO2 > 1000 ppm | `CRITICAL` |
| `air_quality` | NO2 > 53 ppb | `CRITICAL` |
| `indoor_comfort` | Temp > 30°C | `WARNING` |
| `indoor_comfort` | Humidity > 70% | `WARNING` |
| `indoor_comfort` | CO2 > 800 ppm + ventilation OFF | `CRITICAL` |
| `water_safety` | **Pump ON + Flow < 2 LPM (DRY RUN)** | `CRITICAL` |
| `water_safety` | Reservoir < 20% | `WARNING` |
| `water_safety` | Water meter reports `leak_detected` | `CRITICAL` |
| `water_quality` | pH < 6.5 or pH > 8.5 | `CRITICAL` |
| `water_quality` | Turbidity > 4 NTU | `CRITICAL` |
| `water_quality` | TDS > 500 mg/L | `WARNING` |
| `equipment_health` | Motor temp > 75°C | `CRITICAL` |
| `equipment_health` | Vibration = HIGH | `WARNING` |
| `equipment_health` | Filter pressure > 500 Pa | `WARNING` |

**Payload produced:**
```json
{
  "alert_type": "DOMAIN",
  "rule_id": "water_safety",
  "severity": "CRITICAL",
  "message": "DRY RUN: Pump WATER-PUMP-003 ON but flow=0.5 LPM",
  "node_id": "WATER-PUMP-003",
  "zone_id": "BLK-A",
  "domain": "ehs",
  "metric_key": "flow_rate_lpm",
  "metric_value": 0.5,
  "threshold_value": 2.0,
  "triggered_at": "2026-04-23T10:00:00Z"
}
```

---

## 2. 📴 NODE Alerts — Node Health Events

**Source:** `PersistentMiddleware` or `IngestionEngine` (heartbeat miss detection)  
**How:** When a node has not sent data within `2 × send_interval` (default 60s), it is considered OFFLINE.

| Event | Severity | Notes |
|---|---|---|
| Node goes **OFFLINE** | `CRITICAL` | No heartbeat for >60s |
| Node comes back **ONLINE** | `INFO` | After being offline |
| Node reports `fault_status: true` | `WARNING` | Grid/transformer fault |
| Node sends consistent error responses | `WARNING` | Protocol-level failures |

**Payload produced:**
```json
{
  "alert_type": "NODE",
  "severity": "CRITICAL",
  "message": "Node AC-UNIT-007 is OFFLINE (last seen: 2 min ago)",
  "node_id": "AC-UNIT-007",
  "zone_id": "BLK-B",
  "domain": "energy",
  "triggered_at": "2026-04-23T10:05:00Z"
}
```

---

## 3. 📋 ASSIGNMENT Alerts — Task Lifecycle Events

**Source:** `UserService` — generated internally when assignment state changes  
**How:** Produced synchronously when a Manager or Servicer performs an action  

| Event | Who gets it | Severity |
|---|---|---|
| New assignment created by Manager | **Assigned Servicer** | `INFO` |
| Assignment status → `IN_PROGRESS` | **Manager who assigned it** | `INFO` |
| Assignment status → `RESOLVED` | **Manager who assigned it** | `INFO` |
| Assignment **overdue** (no update for >24h) | **Manager + Servicer** | `WARNING` |
| Assignment node goes CRITICAL while ASSIGNED | **Manager + Servicer** | `CRITICAL` |

**Payload produced:**
```json
{
  "alert_type": "ASSIGNMENT",
  "severity": "INFO",
  "message": "New assignment: Inspect AC-UNIT-007 in BLK-B [assigned by Manager]",
  "assignment_id": "uuid-xxx",
  "node_id": "AC-UNIT-007",
  "zone_id": "BLK-B",
  "target_user_id": "servicer-uuid",  
  "triggered_at": "2026-04-23T10:10:00Z"
}
```

---

## 4. 🕹️ ACTUATOR Alerts — Device Toggle Audit

**Source:** `UserService` — generated every time someone sends an actuator command  
**How:** Always produced on `PATCH /actuators/{node_id}/command`  
**Purpose:** Creates a full audit trail of who changed what, when.

| Event | Who gets it | Severity |
|---|---|---|
| ANY actuator toggled | **Manager** (always) | `INFO` |
| CRITICAL node toggled OFF | **Manager + assigned Servicer** | `WARNING` |
| Unauthorized toggle attempt (blocked) | **Manager** | `WARNING` |

**Payload produced:**
```json
{
  "alert_type": "ACTUATOR",
  "severity": "INFO",
  "message": "AC-UNIT-001 toggled OFF by resident@city.com",
  "node_id": "AC-UNIT-001",
  "zone_id": "BLK-A",
  "domain": "energy",
  "triggered_by_user": "resident-uuid",
  "triggered_by_role": "RESIDENT",
  "command": {"field": "state", "value": "OFF"},
  "triggered_at": "2026-04-23T10:15:00Z"
}
```

---

## 5. ⚙️ SYSTEM Alerts — Platform Health Events

**Source:** Internal to each service (startup, shutdown, connection lost)  
**Who gets it:** Manager only  

| Event | Severity |
|---|---|
| Engine lost connection to Middleware | `WARNING` |
| RabbitMQ connection dropped | `CRITICAL` |
| Any service returned 5xx repeated times | `WARNING` |
| UserService DB file locked/corrupted | `CRITICAL` |

---

## Summary Table

| Type | Source Service | Cooldown | Can be suppressed? |
|---|---|---|---|
| `DOMAIN` | EnergyEngine / EHSEngine | 5 min per rule+node | Yes (by Analyst adjusting threshold) |
| `NODE` | Middleware / IngestionEngine | 10 min per node | No |
| `ASSIGNMENT` | UserService | None (one-time events) | No |
| `ACTUATOR` | UserService | None (audit log) | No |
| `SYSTEM` | Any service | 15 min per event | No |
