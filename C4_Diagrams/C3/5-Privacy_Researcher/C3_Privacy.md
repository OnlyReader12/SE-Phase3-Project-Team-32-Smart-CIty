# Component (C3) Level: 5. Data Privacy & Researcher Gateway

## Overview
This folder provides the structural breakdown of the **Privacy & Researcher Gateway**. As dictated by our ADR-009, this container acts as the definitive "Scrubbing Wall" guaranteeing that researchers never accidentally query PII from our Telemetry TSDB.

## Diagram Details (`C3_Privacy.puml`)

### Internal Components
*   **Researcher API Controller:** The external facing REST endpoint exposing `GET` routes for historical data queries.
*   **Time-Bounded Query Validator:** Checks incoming requests to ensure they do not exceed the strictly permitted 30-day lookback window.
*   **InfluxDB Reader DAO:** Executes the safe query against the Telemetry TSDB.
*   **Pandas Scraping Engine:** The functional core that strips predefined PII columns out of the returned data frames *in-memory* before returning the final JSON.

### Connections
*   External Researchers -> (HTTPS) -> API Controller
*   API Controller -> Query Validator -> InfluxDB Reader
*   InfluxDB Reader -> (Query) -> InfluxDB
*   InfluxDB Reader -> Pandas Scraper -> API Controller

## PlantUML Implementation
The components and strict scrubbing paths are mapped in `C3_Privacy.puml`.
