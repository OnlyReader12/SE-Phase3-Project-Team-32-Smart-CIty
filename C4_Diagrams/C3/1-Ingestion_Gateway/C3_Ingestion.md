# Component (C3) Level: 1. Data Ingestion Gateway

## Overview
This folder provides the structural breakdown of the very first container in the Smart City data pipeline: the **Data Ingestion Gateway**. This container acts as the physical edge that directly receives TCP/UDP payloads from the 300 IoT nodes.

## Diagram Details (`C3_Ingestion.puml`)

### Internal Components
*   **MQTT Broker Endpoint:** Captures lightweight telemetry topics published by battery-constrained outdoor nodes.
*   **HTTP REST Endpoint:** Captures standard JSON POST payloads from hardwired campus sensors (like smart lamppost energy readouts).
*   **Connection Validator:** Basic security component that checks the incoming hardware MAC address or API key against an approved "Hardware Whitelist".
*   **Raw Dispatcher:** Forwards the validated, but still unstructured, data stream to the Semantic Middleware container for processing.

### Connections
*   External IoT Nodes -> (MQTT/HTTP) -> Gateway Endpoints
*   Gateway Endpoints -> Connection Validator -> Raw Dispatcher
*   Raw Dispatcher -> (TCP) -> Semantic Middleware

## PlantUML Implementation
The components and relationships within this ingestion layer are mapped out in the accompanied `C3_Ingestion.puml` file.
