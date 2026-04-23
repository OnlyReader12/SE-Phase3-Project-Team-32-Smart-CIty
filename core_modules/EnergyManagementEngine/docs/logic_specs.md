# ⚡ Energy Management Engine — Logic Specification

**Service Port:** `8004`  
**Role:** Continuously analyses energy telemetry from PersistentMiddleware and exposes REST API endpoints used by UserService (for analyst dashboards) and alert dispatch.

---

## 📐 Design Patterns

| Pattern | Where Applied | Purpose |
|---|---|---|
| **Template Method** | `BaseEngine` | Defines the fixed analysis pipeline; subclasses only declare their rules |
| **Strategy** | Each `AnalysisRule` subclass | Each question (Q1-Q5) is a self-contained strategy, added without changing the core |
| **Factory + Registry** | `RuleRegistry` | Rules are auto-discovered; adding a new rule = dropping a new file, zero core edits |
| **Observer** | RabbitMQ subscriber | Engine observes the live telemetry stream; decoupled from Ingestion |

**Open/Closed Principle in practice:**  
The engine core is **open for extension** (new rule file → auto-registered) and **closed for modification** (you never touch `base_engine.py` to add a new Q6).

---

## 🏗️ Directory Structure

```
EnergyManagementEngine/
├── main.py                  # FastAPI entry point (port 8004)
├── engine.py                # EnergyEngine(BaseEngine) — declares its rule set
├── requirements.txt
├── rules/
│   ├── __init__.py          # Rule auto-registration via importlib
│   ├── base_rule.py         # Abstract AnalysisRule (Strategy interface)
│   ├── power_balance.py     # Q1: Generation vs Consumption
│   ├── ac_efficiency.py     # Q2: AC inefficiency detection
│   ├── light_waste.py       # Q3: Lights ON without occupancy
│   ├── battery_health.py    # Q4: Battery SOC & discharge
│   └── ev_peak_load.py      # Q5: EV charger load spikes
└── shared/                  # Shared across both engines
    ├── base_engine.py       # Template Method core
    ├── middleware_client.py # Async fetcher from PersistentMiddleware
    └── threshold_store.py   # In-memory threshold cache (updated via API)
```

---

## 📊 Analysis Questions

### ⚡ Q1 — Power Balance: Generation vs Consumption
> "Are we generating enough power right now?"

**Nodes:** Solar Panel, Smart Energy Meter, Grid/Transformer  
**Parameters watched:** `power_w`, `energy_kwh`, `load_percent`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Spike | Solar `power_w` drops >40% in <5 min | WARNING |
| Sustained | Consumption > Generation for >10 min | CRITICAL |
| Mismatch | Grid `load_percent` > 90% | CRITICAL |

**Metrics exposed (for Flutter charts):**
- `solar_output_kw` time series (rolling 1h)
- `net_balance_kw` = generation − consumption
- `peak_demand_kw` (max in window)

**Default Thresholds (Analyst-adjustable sliders):**
```json
{ "solar_drop_pct": 40, "sustained_deficit_min": 10, "grid_overload_pct": 90 }
```

---

### ❄️ Q2 — AC Efficiency Detection
> "Is the AC consuming more than it should for the cooling it delivers?"

**Nodes:** AC Unit  
**Parameters:** `power_usage`, `current_temp`, `set_temp`, `mode`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Inefficiency | `power_usage` high AND `|current_temp - set_temp|` < 1°C | WARNING |
| Overload | `current_temp - set_temp` > threshold AND power high | CRITICAL |
| Mismatch | AC `state: ON` but mode = COOL and outdoor temp < 18°C | INFO |

**Metrics exposed:**
- `avg_power_per_ac_unit_kw` per zone
- `efficiency_score` = cooling_delta / power_kw (lower = worse)

**Default Thresholds:**
```json
{ "efficiency_min_delta_c": 1.0, "overload_delta_c": 5.0, "cold_outdoor_threshold_c": 18 }
```

---

### 💡 Q3 — Light Waste Detection
> "Are lights ON when no one is around?"

**Nodes:** Indoor Lighting, Outdoor Lamp Post, Occupancy/Footfall  
**Parameters:** `state`, `occupancy`, `count`, `brightness`, `power_usage`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Waste | Light `state: ON` AND `occupancy: false` for > 5 min | WARNING |
| Schedule mismatch | Lamp post ON during daylight hours (time-based) | INFO |
| Savings opportunity | Zone-wide: all lights ON, footfall < 3 | INFO |

**Metrics exposed:**
- `wasted_light_zones` list
- `estimated_wasted_kwh` in window
- `lights_on_no_occupancy_count` per zone

**Default Thresholds:**
```json
{ "idle_min_before_alert": 5, "daylight_start_hour": 6, "daylight_end_hour": 19, "min_footfall": 3 }
```

---

### 🔋 Q4 — Battery Health & Discharge Monitoring
> "Is the battery being used optimally or is it draining under high demand?"

**Nodes:** Battery/Energy Storage  
**Parameters:** `soc`, `charge_rate`, `status`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Low SOC | `soc < 20%` during peak demand hours | CRITICAL |
| Excessive discharge | Discharge rate > threshold for > 15 min | WARNING |
| Full but not charging | Solar available, `soc < 95%`, not charging | INFO |

**Metrics exposed:**
- `soc_timeseries` (rolling 2h)
- `avg_discharge_rate`
- `charge_cycles_today`

**Default Thresholds:**
```json
{ "low_soc_pct": 20, "max_discharge_rate_kw": 10, "peak_hour_start": 9, "peak_hour_end": 20 }
```

---

### 🚗 Q5 — EV Charger Peak Load
> "Are multiple EV chargers creating a simultaneous peak load spike?"

**Nodes:** (Occupancy nodes at parking zone as proxy for EV presence)  
**Parameters:** `occupancy_state`, `count`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Simultaneous load | >N chargers concurrently active | WARNING |
| Grid stress | EV load coincides with grid `load_pct` > 80% | CRITICAL |

**Metrics exposed:**
- `concurrent_ev_chargers` count (time series)
- `estimated_ev_load_kw`

**Default Thresholds:**
```json
{ "max_concurrent_chargers": 3, "grid_stress_pct": 80 }
```

---

## 📡 REST API Endpoints

| Method | Path | Who Calls It | Returns |
|---|---|---|---|
| `GET` | `/health` | Monitoring | Engine status + uptime |
| `GET` | `/metrics/summary` | UserService → Analyst Dash | KPI cards: total consumption, net balance, waste estimate |
| `GET` | `/metrics/timeseries` | UserService → Analyst Dash | `?node_id=X&param=power_w&window=1h` — array of `{ts, value}` |
| `GET` | `/metrics/aggregate` | UserService → Analyst Dash | `?zone=BLK-A` — zone-level totals, averages, min/max |
| `GET` | `/alerts` | UserService | Recent rule-triggered alerts (last 100) |
| `GET` | `/thresholds` | Flutter Analyst UI | All analyst-adjustable thresholds |
| `PUT` | `/thresholds/{rule_id}` | Flutter Analyst UI (Slider) | Update threshold for a specific rule |
| `GET` | `/trends/{domain}` | UserService → Analyst Dash | Moving avg, 3-point trend prediction |

---

## 📈 Flutter Analyst Dashboard — Chart Plan (Energy Team)

| Chart | Type | Data Source | Purpose |
|---|---|---|---|
| Real-time Power Balance | Area Chart (fl_chart) | `/metrics/timeseries?param=power_w` | Generation vs Consumption live |
| Battery SOC Over Time | Line Chart | `/metrics/timeseries?node=battery&param=soc` | See drain patterns |
| Energy Heatmap By Zone | Bar Chart | `/metrics/aggregate?groupby=zone` | Highest consuming zones |
| AC Efficiency Ranking | Horizontal Bar | `/metrics/summary` → ac_efficiency_score | Which AC units are wasteful |
| Lights Waste Estimate | KPI Card + Sparkline | `/metrics/summary` → wasted_kwh | Cost of idle lighting |

### 🎚️ Analyst Slider Controls (set thresholds live):
- **Solar Drop Alert %** → triggers Q1 spike alert
- **AC Efficiency Min Delta (°C)** → triggers Q2 alert
- **Idle Light Minutes** → triggers Q3 waste alert
- **Low Battery SOC %** → Battery alert threshold
- **Max Concurrent EVs** → Q5 peak load alert

---

## 🔁 Data Flow

```
PersistentMiddleware (:8001)
        │
        │  GET /api/nodes?engine_type=energy (polling every 30s)
        ▼
EnergyManagementEngine (:8004)
        │
        ├── RuleRegistry.run_all(latest_data)
        │       ├── PowerBalanceRule.analyse() → Alert or None
        │       ├── ACEfficiencyRule.analyse() → Alert or None
        │       ├── LightWasteRule.analyse()    → Alert or None
        │       ├── BatteryHealthRule.analyse() → Alert or None
        │       └── EVPeakLoadRule.analyse()    → Alert or None
        │
        ├── POST /internal/alerts → UserService (:8003)  [if alert triggered]
        │
        └── Expose /metrics/* → UserService fetches for Analyst Dashboard
```
