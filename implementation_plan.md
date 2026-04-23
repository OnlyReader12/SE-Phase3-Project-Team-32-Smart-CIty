# Expand EHS IoT Nodes → Middleware → Prediction, Visualization & Suggestions

## Background

Currently, the EHS Engine monitors only **2 metrics** (AQI and Water pH) from a single `EHSNode` type in the IoT generator. The real Environmental Health & Safety domain on a campus requires monitoring a much richer set of environmental parameters across multiple specialized sensor types. This plan expands the entire pipeline end-to-end.

---

## User Review Required

> [!IMPORTANT]
> This is a significant expansion across 3 codebases (IoT Generator, Middleware, EHS Engine) plus a new dashboard. Please review the node types, parameters, and protocols carefully.

> [!WARNING]
> The current `EHSData` Pydantic schema only accepts `aqi` and `water_ph`. All existing fields will be preserved, but new fields will be **Optional** so backward compatibility is maintained.

---

## 1. EHS IoT Node Inventory

The EHS Engine monitors **6 distinct node types** across a campus. Here's what each measures, the protocol it uses, and why:

| Node Type | Node ID Prefix | Parameters | Protocol | Rationale |
|---|---|---|---|---|
| **Air Quality Station** | `EHS-AQI-xxx` | `aqi` (0–500), `pm25` (µg/m³), `pm10` (µg/m³), `co2_ppm`, `temperature_c`, `humidity_pct` | **MQTT** | Battery-powered outdoor stations; MQTT is lightweight for constrained devices |
| **Water Quality Probe** | `EHS-WTR-xxx` | `water_ph` (0–14), `turbidity_ntu` (0–1000), `dissolved_oxygen_mgl` (0–20), `water_temp_c` | **MQTT** | Submerged probes in campus water bodies; event-driven push via MQTT |
| **Noise Level Monitor** | `EHS-NOS-xxx` | `noise_db` (30–130 dB), `peak_db`, `frequency_hz` | **MQTT** | Small acoustic sensors near roads/construction; low-power MQTT |
| **Weather Station** | `EHS-WEA-xxx` | `temperature_c`, `humidity_pct`, `wind_speed_ms`, `wind_direction_deg`, `pressure_hpa`, `uv_index`, `rainfall_mm` | **HTTP** | Campus rooftop weather stations; powered by AC, uses HTTP REST for richer payloads |
| **Soil & Agriculture Sensor** | `EHS-SOL-xxx` | `soil_moisture_pct`, `soil_ph` (0–14), `soil_temp_c` | **CoAP** | Campus garden/greenhouse sensors; CoAP for ultra-low-power constrainted devices |
| **Radiation & Gas Detector** | `EHS-RAD-xxx` | `radiation_usv` (µSv/h), `voc_ppb` (volatile organic compounds), `co_ppm` (carbon monoxide), `methane_ppm` | **MQTT** | Lab-adjacent safety sensors; critical safety data via persistent MQTT |

### Total node count allocation (out of 300)
- AQI Stations: **40 nodes**
- Water Probes: **25 nodes**
- Noise Monitors: **20 nodes**
- Weather Stations: **10 nodes**
- Soil Sensors: **15 nodes**
- Radiation/Gas Detectors: **10 nodes**
- **EHS Total: 120 nodes** (remaining 180 split across Energy & CAM domains)

---

## Proposed Changes

### Component 1: IoT Data Generator

Summary: Add 5 new node types (keeping existing `EHSNode`→renamed to `AirQualityNode`) and a `CoAPAdapter`.

#### [MODIFY] [iot_generator.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/IOTDataGenerator/iot_generator.py)

1. **Add `CoAPAdapter`** — New protocol adapter extending `ProtocolAdapter` for simulated CoAP transmissions
2. **Refactor `EHSNode` → `AirQualityNode`** — Rename for clarity, expand payload with `pm25`, `pm10`, `co2_ppm`, `temperature_c`, `humidity_pct`
3. **Add `WaterQualityNode`** — Generates `water_ph`, `turbidity_ntu`, `dissolved_oxygen_mgl`, `water_temp_c`
4. **Add `NoiseMonitorNode`** — Generates `noise_db`, `peak_db`, `frequency_hz`
5. **Add `WeatherStationNode`** — Generates full weather telemetry via HTTP
6. **Add `SoilSensorNode`** — Generates soil data via CoAP
7. **Add `RadiationGasNode`** — Generates gas/radiation safety data
8. **Update `main()` orchestrator** — Distribute 120 EHS nodes proportionally across all 6 types with correct protocol assignments

---

### Component 2: Persistent Middleware

Summary: Expand the middleware to support EHS-specific querying and expose data for the EHS Engine's visualization and suggestion features.

#### [MODIFY] [routes.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/PersistentMiddleware/api/routes.py)

1. **Add `GET /ehs/nodes`** — Returns all active EHS nodes with their latest readings (for dashboard)
2. **Add `GET /ehs/latest/{node_type}`** — Returns latest readings filtered by EHS node type (e.g., `aqi`, `water`, `noise`)
3. **Add `GET /ehs/timeseries/{node_id}`** — Returns time-series data for a specific node (for charts)
4. **Add `GET /ehs/summary`** — Aggregated campus-wide EHS health summary (avg AQI, avg pH, max noise, etc.)

#### [MODIFY] [models.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/PersistentMiddleware/database/models.py)

1. **Add `ehs_node_type` column** — To classify telemetry records by node type (`aqi`, `water`, `noise`, `weather`, `soil`, `radiation`)

---

### Component 3: EHS Engine — Schemas & Evaluators

Summary: Expand schemas to accept all 6 node types, add new threshold evaluators, and register them in the factory.

#### [MODIFY] [schemas.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/models/schemas.py)

1. **Expand `MetricType` enum** — Add `NOISE_DB`, `PM25`, `CO2`, `UV_INDEX`, `VOC`, `TURBIDITY`, `SOIL_MOISTURE`
2. **Expand `EHSData`** — Make new fields Optional so old payloads still work
3. **Add `EHSSuggestion` model** — For actionable recommendations (e.g., "Close windows", "Evacuate lab")
4. **Add `EHSDashboardSummary` model** — Aggregated campus-wide stats for the dashboard
5. **Add `EHSVisualizationPoint` model** — Time-bucketed data for charts

#### [MODIFY] [threshold_evaluator.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/evaluator/threshold_evaluator.py)

1. **Add `NoiseThresholdEvaluator`** — SAFE < 70dB, WARNING 70–85dB, CRITICAL > 85dB
2. **Add `PM25ThresholdEvaluator`** — SAFE < 35µg/m³, WARNING 35–150µg/m³, CRITICAL > 150µg/m³
3. **Add `UVIndexEvaluator`** — SAFE < 6, WARNING 6–8, CRITICAL > 8
4. **Add `VOCEvaluator`** — SAFE < 500ppb, WARNING 500–2000ppb, CRITICAL > 2000ppb
5. **Add `TurbidityEvaluator`** — SAFE < 5 NTU, WARNING 5–50 NTU, CRITICAL > 50 NTU

#### [MODIFY] [evaluator_factory.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/evaluator/evaluator_factory.py)

1. **Register all 5 new evaluators** — Adding cases for `noise_db`, `pm25`, `uv_index`, `voc`, `turbidity`

---

### Component 4: EHS Engine — Prediction, Visualization & Suggestions

Summary: Add new API endpoints for prediction output, visualization data, and actionable suggestions.

#### [MODIFY] [engine_evaluator.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/evaluator/engine_evaluator.py)

1. **Expand evaluate() pipeline** — Handle all new metrics (noise, PM2.5, UV, VOC, turbidity) when present
2. **Add `generate_suggestions()` method** — Rule-based actionable suggestions based on current + forecasted values
3. **Add `get_dashboard_summary()` method** — Aggregate latest readings across all nodes
4. **Add `get_visualization_data()` method** — Return time-bucketed history for charting

#### [MODIFY] [config.yaml](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/config.yaml)

1. **Add thresholds** — For noise_db, pm25, uv_index, voc, turbidity

#### [MODIFY] [main.py](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/main.py)

1. **Add `GET /predict/{node_id}`** — Returns ML forecast for a specific node
2. **Add `GET /visualize/timeseries`** — Returns time-series visualization data for specified metrics
3. **Add `GET /visualize/heatmap`** — Returns campus-wide metric heatmap data
4. **Add `GET /suggestions`** — Returns current actionable EHS suggestions
5. **Add `GET /dashboard`** — Returns full campus EHS dashboard summary

---

### Component 5: EHS Dashboard (New)

Summary: A standalone HTML dashboard served by the EHS Engine that visualizes all EHS metrics in real-time.

#### [NEW] [dashboard.html](file:///c:/Users/Saich/OneDrive/Desktop/SePhase3/SE-Phase3-Project-Team-32-Smart-CIty/core_modules/EHSEngine/static/dashboard.html)

A premium, dark-themed single-page dashboard featuring:
- **Campus Health Score** — Composite EHS safety indicator
- **Live Metric Cards** — AQI, Water pH, Noise, PM2.5, UV Index, VOC, Radiation
- **Time-Series Charts** — Interactive (Chart.js) plots for each metric's trend
- **ML Prediction Panel** — Forecasted values with confidence intervals  
- **Suggestions Panel** — Real-time actionable recommendations with severity badges
- **Node Status Grid** — All 120 EHS nodes with health status indicators
- Auto-refreshes every 5 seconds via `fetch()` API calls to the EHS Engine

---

## Open Questions

> [!IMPORTANT]
> **Soil sensor protocol:** I've assigned CoAP to Soil sensors for protocol diversity. If you'd prefer all nodes to use only HTTP/MQTT (avoiding the CoAP dependency), I can adjust.

> [!NOTE]
> **Node count distribution:** 120 EHS nodes out of 300 total. The remaining 180 are for Energy (Member 3) and CAM (not implemented). This ratio is adjustable.

---

## Verification Plan

### Automated Tests
1. **IoT Generator** — Run `python iot_generator.py` and verify all 6 node types emit correctly formatted payloads via their assigned protocols
2. **Middleware** — Start the middleware, send a sample payload via `POST /middleware/ingest`, then query `GET /ehs/nodes` to confirm storage and retrieval
3. **EHS Engine** — Use `POST /evaluate` with payloads for each node type and verify:
   - Correct threshold evaluation (SAFE/WARNING/CRITICAL)
   - ML predictions returned in response
   - Suggestions generated for WARNING/CRITICAL readings
4. **Dashboard** — Open `http://localhost:8002/dashboard` in browser and verify real-time visualization

### Manual Verification
- Run all 3 services simultaneously and confirm end-to-end data flow: Generator → Middleware → EHS Engine → Dashboard
