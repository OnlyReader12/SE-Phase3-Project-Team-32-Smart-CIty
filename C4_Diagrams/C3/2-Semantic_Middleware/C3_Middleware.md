# Component (C3) Level: 2. Semantic Middleware

## Overview
This folder provides the structural breakdown of the **Semantic Middleware Subsystem**. Once data passes the physical Gateway, it enters this container to be standardized strictly to the OneM2M protocol. This prevents our core engines from worrying about 300 different hardware formats.

## Diagram Details (`C3_Middleware.puml`)

### Internal Components
*   **Payload Ingestor:** Receives the raw TCP streams forwarded from the Ingestion Gateway.
*   **Knowledge Graph / Dictionary:** A static mapping file that links specific hardware IDs to physical concepts (e.g., "Node 44A" = "Building_A_Air_Quality").
*   **Ontology Translator (OneM2M):** The core logic that converts the messy raw payloads into standardized `SmartCityObject` JSON structures.
*   **AMQP Publisher:** Pushes the finalized, clean OneM2M object onto the RabbitMQ Microkernel bus for the rest of the city to consume.

### Connections
*   Raw Dispatcher -> Payload Ingestor
*   Payload Ingestor -> Ontology Translator (reads Knowledge Graph)
*   Ontology Translator -> AMQP Publisher
*   AMQP Publisher -> (AMQP) -> RabbitMQ Message Bus

## PlantUML Implementation
The internal translation flows are visualized in `C3_Middleware.puml`.
