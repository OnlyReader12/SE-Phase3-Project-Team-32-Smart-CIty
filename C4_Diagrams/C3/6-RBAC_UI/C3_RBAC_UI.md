# Component (C3) Level: 6. RBAC & UI Subsystem

## Overview
This folder provides the structural breakdown of the **RBAC & UI Subsystem**. This covers the core API Gateway that authenticates all human frontend requests, validating permissions tightly against the PostgreSQL database before allowing dashboards to load.

## Diagram Details (`C3_RBAC_UI.puml`)

### Internal Components
*   **Flutter WebView / Mobile Views:** The actual rendered screen components generating the queries.
*   **Auth Gateway Controller:** The primary entry point intercepting all inbound UI requests.
*   **JWT Token Validator:** Unpacks browser/mobile auth tokens.
*   **Postgres RBAC Verifier:** Queries the rigid relational database to assert if the user role is permitted to execute the requested route (e.g., stopping a student from controlling lampposts).
*   **Dashboard Aggregator:** If permitted, this component fans out the request to fetch the necessary UI data from the TSDB or Message Bus and packages it for the dashboard.

### Connections
*   Flutter Views -> (HTTPS) -> Auth Gateway
*   Auth Gateway -> JWT Validator -> Postgres Verifier
*   Postgres Verifier -> (SQL) -> PostgreSQL
*   Verifier -> Dashboard Aggregator

## PlantUML Implementation
The security barriers are mapped out in `C3_RBAC_UI.puml`.
