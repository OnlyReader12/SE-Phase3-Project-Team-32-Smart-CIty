# EHS Documentation

## Overview

The Environmental Health and Safety (EHS) subsystem is one domain of the Smart City Living Lab microkernel architecture. Its purpose is to ingest environmental telemetry, evaluate safety thresholds, forecast future risk, generate actionable suggestions, and present those results in a dashboard for operators and presentations.

The EHS stack is intentionally split into separate services so each responsibility can evolve without forcing changes into the others. The main participating services are:

- IoT Data Generator
- Persistent Middleware
- EHS Engine
- EHS Presentation Dashboard

Each service communicates through narrow interfaces and well-defined payloads.

## Service Map

### 1. IoT Data Generator

Location: [IOTDataGenerator/iot_generator.py](../IOTDataGenerator/iot_generator.py)

This component simulates campus EHS devices and produces telemetry for all monitored node types. It acts as the source of sample telemetry for demonstrations and testing.

Key responsibilities:

- Generate realistic node-specific payloads
- Assign a communication protocol per device class
- Emit telemetry with node identity, node type, timestamp, and data fields
- Provide a canonical catalog of monitored EHS nodes

### 2. Persistent Middleware

Location: [core_modules/PersistentMiddleware/api/routes.py](../core_modules/PersistentMiddleware/api/routes.py)

This service receives telemetry, stores it in the middleware database, and exposes query endpoints for node discovery and history lookup. It is the source of truth for node catalog and historical records.

Key responsibilities:

- Persist telemetry records
- Expose EHS node inventory
- Return node history and time series
- Provide middleware summary endpoints for downstream services

### 3. EHS Engine

Location: [core_modules/EHSEngine/main.py](../core_modules/EHSEngine/main.py)

The EHS Engine is the core decision-making microservice. It loads configuration, evaluates readings, runs forecasting, generates suggestions, and returns dashboard-ready summaries.

Key responsibilities:

- Evaluate current telemetry against safety thresholds
- Run ML-based or fallback forecasting
- Build campus-wide dashboard summaries
- Generate warnings, critical alerts, and suggestions
- Serve the presentation demo page and API responses

### 4. EHS Presentation Dashboard

Location: [core_modules/EHSEngine/static/presentation.html](../core_modules/EHSEngine/static/presentation.html)

This page is a presentation-first front end. It shows the internal flow from node discovery to final results. It is designed for live demonstrations, not just routine monitoring.

## Monitored Node Types

The EHS subsystem monitors six node families. These are the canonical EHS node classes used by the generator, middleware, and engine.

| Node Type | Prefix | Protocol | Main Parameters | Used For |
|---|---|---|---|---|
| Air Quality Station | EHS-AQI | MQTT | aqi, pm25, pm10, co2_ppm, temperature_c, humidity_pct | prediction, visualization, suggestions |
| Water Quality Probe | EHS-WTR | MQTT | water_ph, turbidity_ntu, dissolved_oxygen_mgl, water_temp_c | prediction, visualization, suggestions |
| Noise Level Monitor | EHS-NOS | MQTT | noise_db, peak_db, frequency_hz | visualization, suggestions |
| Weather Station | EHS-WEA | HTTP | temperature_c, humidity_pct, wind_speed_ms, wind_direction_deg, pressure_hpa, uv_index, rainfall_mm | visualization, suggestions |
| Soil Sensor | EHS-SOL | CoAP | soil_moisture_pct, soil_ph, soil_temp_c | visualization, suggestions |
| Radiation/Gas Detector | EHS-RAD | MQTT | radiation_usv, voc_ppb, co_ppm, methane_ppm | prediction, visualization, suggestions |

## Microservices Architecture

The EHS flow follows the larger Smart City microservice pattern. The services are intentionally isolated so they can fail, scale, and be deployed independently.

### IoT Data Generator

The generator simulates many nodes across the city. For EHS, it creates the sensor payloads and tags each message with:

- `node_id`
- `domain`
- `node_type`
- `timestamp`
- `data`

It also documents the protocol used by each node family:

- MQTT for battery-powered or event-driven sensors
- HTTP for richer AC-powered station payloads
- CoAP for constrained low-power devices

### Persistent Middleware

The middleware is the persistence and discovery layer. It stores telemetry and exposes a stable query surface for other services.

Important routes:

- `POST /middleware/ingest` - persist and publish telemetry
- `GET /ehs/nodes` - return all active EHS nodes with latest readings
- `GET /ehs/latest/{node_type}` - return readings by node type
- `GET /ehs/timeseries/{node_id}` - return history for one node
- `GET /ehs/summary` - return aggregated EHS metrics
- `GET /ehs/catalog` - return the canonical node catalog

### EHS Engine

The EHS Engine consumes the normalized telemetry model and turns it into actionable outputs.

Important routes:

- `POST /evaluate` - manual evaluation of one telemetry payload
- `GET /health` - service health status
- `GET /thresholds` - current safety thresholds
- `GET /predict/{node_id}` - forecast for a node
- `GET /visualize/timeseries` - chart-ready history
- `GET /visualize/heatmap` - campus heatmap data
- `GET /suggestions` - actionable suggestions
- `GET /dashboard-data` - dashboard summary JSON
- `GET /dashboard` - standard dashboard page
- `GET /presentation-data` - aggregated presentation payload
- `GET /presentation` - presentation front end

## How the Services Communicate

Communication is based on a simple flow from telemetry generation to decision output.

### 1. Generator to Middleware

The IoT Data Generator produces telemetry payloads and sends them through protocol adapters. In the live design, it represents the device layer and protocol translation boundary. The middleware receives normalized JSON and stores it.

### 2. Middleware to EHS Engine

The EHS Engine reads the persisted data via the middleware query endpoints. The shared node catalog from middleware ensures the engine and presentation page use the same node definitions.

### 3. EHS Engine to Dashboard

The engine aggregates the current campus state and serves it through dashboard and presentation endpoints. The front end polls or fetches these routes to render live status, predictions, and suggestions.

### 4. Presentation Mode Flow

The presentation page is designed to make the internal pipeline visible:

1. Discover the node catalog from middleware
2. Ingest or summarize the latest telemetry state
3. Run predictions for the most relevant node
4. Build visualization-ready metrics
5. Generate final suggestions and health score

## Design Patterns Used

### Adapter Pattern

Used in the IoT Data Generator for protocol-specific transmission.

Why it matters:

- HTTP, MQTT, and CoAP are isolated behind adapter classes
- New device protocols can be added without rewriting node logic
- The telemetry payload format remains stable for downstream services

### Strategy Pattern

Used in the EHS Engine forecasting layer.

The predictor is chosen by configuration, not by hardcoded logic. The engine can use one forecasting strategy today and a different one tomorrow without changing the evaluator.

Why it matters:

- Swapping prediction models does not affect the rest of the engine
- The evaluator calls a common `PredictorStrategy` interface
- The engine can support both scikit-learn and TensorFlow approaches

### Factory Method

Used to create threshold evaluators for different metrics.

Each environmental metric has different safety rules. A factory returns the correct evaluator for AQI, water pH, noise, PM2.5, UV, VOC, or turbidity.

Why it matters:

- Each metric can have custom thresholds
- The evaluator logic stays compact and extensible
- New metrics can be added with a new evaluator class and one factory case

### Observer Pattern

Used in two places:

- The middleware publishes telemetry events
- The EHS Engine can listen to environmental telemetry streams in a background consumer

Why it matters:

- Producers and consumers remain loosely coupled
- The engine can process data asynchronously
- A failure in one consumer does not require changes to the producer

### Builder Pattern

Used in the dashboard and presentation experience.

The dashboard is assembled from multiple metric cards, status blocks, charts, and suggestion panels. The presentation page uses the aggregated response to build the flow step by step.

Why it matters:

- The UI can present only the parts needed for a live demo
- Different roles can see different levels of detail
- The page can be extended without changing the data model

## EHS Engine Evaluation Pipeline

The core evaluation pipeline works as follows:

1. Parse the telemetry payload into the schema model
2. Evaluate AQI and water pH first because they are always present
3. Evaluate any optional extended metrics when they appear
4. Determine the overall status using the worst-case severity
5. Run forecasting for risky or historical nodes
6. Persist and publish side effects asynchronously
7. Update dashboard state and suggestions

## Why the Node Catalog Matters

The node catalog makes the EHS system easier to present and maintain because it gives one consistent source of truth for:

- Which node types are monitored
- Which telemetry parameters each node emits
- Which protocol each node uses
- Which downstream features consume the data

This is useful for prediction, visualization, and suggestion generation because each of those features depends on knowing what data is available and how it is structured.

## Presentation Demo Usage

For the presentation, the recommended flow is:

1. Start the EHS Engine
2. Open the presentation page
3. Click `Start Demo`
4. Walk through the flow from catalog discovery to final outcome
5. Use the dashboard link if you want the fuller operational view

If you use the automated demo runner, it will open the presentation page and trigger the flow for you.

## Summary

The EHS subsystem is built as a set of decoupled microservices that communicate through clearly defined contracts. The IoT generator creates protocol-specific telemetry, the middleware stores and serves the canonical node inventory, and the EHS Engine evaluates, predicts, visualizes, and recommends actions. The architecture uses Adapter, Strategy, Factory Method, Observer, and Builder patterns to keep the system extensible, presentation-friendly, and safe to evolve.