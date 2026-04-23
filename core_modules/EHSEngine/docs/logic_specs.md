# 🌬️💧 EHS Engine — Logic Specification

**Service Port:** `8005`  
**Role:** Monitors Environmental Health & Safety (EHS) telemetry. Detects dangerous air quality, water hazards, and equipment failures. Exposes endpoints for UserService (Analyst dashboards + alert dispatch).

---

## 📐 Design Patterns

| Pattern | Where Applied | Purpose |
|---|---|---|
| **Template Method** | `BaseEngine` | Shared pipeline (fetch → analyse → alert). EHSEngine only declares its rules |
| **Strategy** | Each `AnalysisRule` subclass | Q1–Q5 are independent strategies; adding Q6 = new file |
| **Factory + Registry** | `RuleRegistry` | Auto-discovers all rule subclasses; zero core changes to extend |
| **Observer** | Background async poller | Watches PersistentMiddleware for new node readings every 30s |

**Open/Closed Principle in practice:**  
`base_engine.py` is **never modified**. To add a new capability (e.g., Noise Pollution Detection), you drop `noise_pollution.py` into the `rules/` folder — the registry auto-registers it.

---

## 🏗️ Directory Structure

```
EHSEngine/
├── main.py                  # FastAPI entry point (port 8005)
├── engine.py                # EHSEngine(BaseEngine) — declares its rule set
├── requirements.txt
├── rules/
│   ├── __init__.py          # Rule auto-registration
│   ├── base_rule.py         # Abstract AnalysisRule (Strategy interface)
│   ├── air_quality.py       # Q1: PM2.5 / CO2 / NO2 / O3 thresholds
│   ├── indoor_comfort.py    # Q2: Temp/Humidity/CO2 comfort violation
│   ├── water_safety.py      # Q3: Dry run, leakage, pump anomaly
│   ├── water_quality.py     # Q4: pH, turbidity, TDS spikes
│   └── equipment_health.py  # Q5: Motor temp, vibration, filter pressure
└── shared/                  # Shared with EnergyManagementEngine
    ├── base_engine.py
    ├── middleware_client.py
    └── threshold_store.py
```

---

## 📊 Analysis Questions

### 🌬️ Q1 — Air Quality Safety
> "Is the air quality crossing safe limits for campus occupants?"

**Nodes:** Air Quality Monitoring Node, Environmental Sensor Node  
**Parameters:** `pm2_5`, `pm10`, `co2`, `no2`, `o3`, `noise_db`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Spike | `pm2_5` rises > 30μg/m³ in < 5 min | CRITICAL |
| Sustained | `co2` > 1000 ppm for > 10 min | WARNING |
| Threshold breach | `no2` or `o3` > WHO limit | CRITICAL |
| Mismatch | Purifier `state: OFF` when `pm2_5 > 50` | WARNING |

**Metrics exposed:**
- `pm2_5_timeseries` (rolling 1h)
- `co2_trend` (rising/stable/falling — 3-point SMA)
- `air_quality_index` (AQI composite score per zone)
- `zone_air_ranking` (best → worst air quality)

**Default Thresholds (Analyst sliders):**
```json
{ "pm2_5_spike_ugm3": 30, "co2_sustained_ppm": 1000, "co2_sustained_min": 10, "no2_limit_ppb": 53, "o3_limit_ppb": 70 }
```

---

### 🌡️ Q2 — Indoor Comfort Violation
> "Are classrooms/offices thermally comfortable and ventilated?"

**Nodes:** Temperature & Humidity Node, HVAC AHU (proxy via Ventilation Control)  
**Parameters:** `temperature`, `humidity`, `co2_ppm`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Overheating | `temperature > 30°C` in occupied space | WARNING |
| High humidity | `humidity > 70%` for > 15 min | WARNING |
| Poor ventilation | `co2 > 800 ppm` with ventilation `state: OFF` | CRITICAL |
| Mismatch | Ventilation ON but CO2 still rising | WARNING |

**Metrics exposed:**
- `temp_humidity_heatmap` per zone (for grid visualization)
- `avg_co2_ppm` per zone over time
- `comfort_score` = 100 − penalty (temp, humidity, CO2 deviations)

**Default Thresholds:**
```json
{ "max_temp_c": 30, "max_humidity_pct": 70, "co2_poor_ppm": 800, "humidity_sustained_min": 15 }
```

---

### 💧 Q3 — Water System Safety & Efficiency
> "Is the water system running safely? Any dry runs or leaks?"

**Nodes:** Water Pump Node, Smart Water Meter, Reservoir Level Node, Valve Control  
**Parameters:** `flow_rate_lpm`, `level_percent`, `motor_state`, `leak_detected`, `total_consumption`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| **DRY RUN** 🚨 | Pump `state: ON` AND `flow_rate < 2 LPM` for > 2 min | CRITICAL |
| Leakage | `flow_rate` spike with no valve command issued | CRITICAL |
| Low reservoir | `level_percent < 20%` | WARNING |
| Abnormal flow | `flow_rate` > 2× historical average for zone | WARNING |
| Mismatch | Valve `state: OPEN` but flow = 0 | WARNING |

**Metrics exposed:**
- `flow_rate_timeseries` per pump/meter
- `reservoir_level_timeseries`
- `daily_consumption_litres` per zone
- `dry_run_events_count` (last 24h)

**Default Thresholds:**
```json
{ "dry_run_min_flow_lpm": 2, "dry_run_sustained_min": 2, "low_reservoir_pct": 20, "flow_spike_multiplier": 2.0 }
```

---

### 🧪 Q4 — Water Quality Monitoring
> "Is the water safe to use and within acceptable quality limits?"

**Nodes:** Water Quality Monitoring Node  
**Parameters:** `ph`, `turbidity`, `tds`, `temperature`, `contamination_level`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| pH out of range | `ph < 6.5` or `ph > 8.5` | CRITICAL |
| Turbidity spike | `turbidity > 4 NTU` (WHO safe = <1 NTU drinking) | WARNING (>1) / CRITICAL (>4) |
| TDS spike | `tds > 500 mg/L` (BIS limit) | WARNING |
| Contamination | `contamination_level` non-zero | CRITICAL |
| Sustained bad | Any parameter bad for > 5 min | escalation to CRITICAL |

**Metrics exposed:**
- `ph_timeseries`
- `turbidity_timeseries`
- `water_quality_score` = composite safety score (0-100)
- `water_quality_violations_count` (last 24h)

**Default Thresholds:**
```json
{ "ph_min": 6.5, "ph_max": 8.5, "turbidity_warning_ntu": 1.0, "turbidity_critical_ntu": 4.0, "tds_max_mgl": 500, "sustained_min": 5 }
```

---

### ⚠️ Q5 — Equipment Health Risk
> "Are pumps, HVAC units, or server room systems showing early failure signs?"

**Nodes:** Water Pump Node, Ventilation Control, Environmental Sensor (server rooms)  
**Parameters:** `motor_temp_c` (inferred from power+state), `vibration_level` (if available), `filter_pressure_pa`

| Detection Type | Condition | Alert Severity |
|---|---|---|
| Overheating | `motor_temp > 75°C` | CRITICAL |
| Vibration anomaly | `vibration_level = HIGH` | WARNING |
| Filter clog | `filter_pressure_pa` > threshold | WARNING |
| Sustained operation | Device run-time > max hours without rest | WARNING |
| Pre-failure pattern | Temp rising + vibration increasing (trend) | CRITICAL |

**Metrics exposed:**
- `equipment_runtime_hours` per node
- `motor_temp_trend` (rising/stable/cooling)
- `equipment_health_score` per node (0-100)
- `at_risk_equipment_list`

**Default Thresholds:**
```json
{ "max_motor_temp_c": 75, "max_filter_pressure_pa": 500, "max_daily_runtime_hours": 18 }
```

---

## 📡 REST API Endpoints

| Method | Path | Who Calls | Returns |
|---|---|---|---|
| `GET` | `/health` | Monitoring | Engine status + rule count |
| `GET` | `/metrics/summary` | UserService → Analyst Dash | AQI, water quality score, at-risk equipment count |
| `GET` | `/metrics/timeseries` | UserService → Analyst Dash | `?node_id=X&param=pm2_5&window=1h` → `{ts, value}[]` |
| `GET` | `/metrics/aggregate` | UserService → Analyst Dash | `?zone=LIB` → zone-level averages, min, max |
| `GET` | `/alerts` | UserService | Recent 100 rule-triggered alerts |
| `GET` | `/thresholds` | Flutter Analyst UI | All adjustable thresholds |
| `PUT` | `/thresholds/{rule_id}` | Flutter Analyst UI (Slider) | Update threshold value |
| `GET` | `/trends/{domain}` | UserService | SMA trend + 3-step prediction |

---

## 📈 Flutter Analyst Dashboard — Chart Plan (EHS Team)

| Chart | Type | Data Source | Purpose |
|---|---|---|---|
| Air Quality Index (AQI) Timeline | Area Chart | `/metrics/timeseries?param=pm2_5` | PM2.5 trends with danger band |
| CO2 Heatmap by Zone | Bar/Grid Chart | `/metrics/aggregate` | Which zones have poor ventilation |
| Water Quality Score | Radial/Gauge | `/metrics/summary → water_quality_score` | Composite safety score |
| Reservoir Level Over Time | Line Chart | `/metrics/timeseries?param=level_percent` | Trend towards low-level alert |
| Equipment Health Status | Sorted List | `/metrics/summary → at_risk_equipment_list` | Sorted by risk, tap for detail |
| Flow Rate Anomaly | Spike Chart | `/metrics/timeseries?param=flow_rate_lpm` | Highlight dry-run events |

### 🎚️ Analyst Slider Controls (live threshold tuning):
- **PM2.5 Alert Level (μg/m³)** → Q1 spike alert trigger
- **CO2 Poor Ventilation Limit (ppm)** → Q2 comfort alert
- **Dry Run Sensitivity (min flow LPM)** → Q3 dry run detection
- **Turbidity Warning Level (NTU)** → Q4 water quality alert
- **Max Equipment Runtime (hours/day)** → Q5 failure warning

---

## 🔔 Special "Mismatch" Conditions (High Value Detections)

These are the most powerful detections because they catch **systematic failures**, not just value spikes:

| Mismatch | What it means | Alert |
|---|---|---|
| Pump ON + Flow = 0 | Dry run or blocked pipe | **CRITICAL** |
| Valve OPEN + Flow = 0 | Valve stuck / upstream issue | **CRITICAL** |
| Ventilation ON + CO2 rising | Ductwork failure | **WARNING** |
| Purifier OFF + PM2.5 > 50 | Control system didn't respond | **WARNING** |
| Water quality bad + no treatment running | Treatment failure | **CRITICAL** |

---

## 🔁 Data Flow

```
PersistentMiddleware (:8001)
        │
        │  GET /api/nodes?engine_type=ehs (polling every 30s)
        ▼
EHSEngine (:8005)
        │
        ├── RuleRegistry.run_all(latest_data)
        │       ├── AirQualityRule.analyse()       → Alert or None
        │       ├── IndoorComfortRule.analyse()    → Alert or None
        │       ├── WaterSafetyRule.analyse()      → Alert or None
        │       ├── WaterQualityRule.analyse()     → Alert or None
        │       └── EquipmentHealthRule.analyse()  → Alert or None
        │
        ├── POST /internal/alerts → UserService (:8003)  [alert triggered]
        │
        └── Expose /metrics/* → UserService fetches for Analyst Dashboard
```

---

## 🧠 Trend Prediction (Simple & Real-Time)

For charts we use **Simple Moving Average (SMA-3)**:

```
prediction[t+1] = (val[t] + val[t-1] + val[t-2]) / 3
```

This gives a near-future trend estimate that analysts can see as a **dashed continuation** on the Flutter chart. No ML required, but it's still "predictive" for the purposes of the system.

For threshold-crossing predictions:
```
time_to_breach = (threshold - current_value) / rate_of_change_per_min
```
This tells an analyst: "At the current rate, we'll breach PM2.5 safety in ~12 minutes."
