# Component (C3) Level: 3. Domain Processing Engines

## Overview
Because the 3 major Domain Engines (EHS, Energy, and CAM) share an identical architectural pattern as "Microkernel Plugins," this C3 diagram abstracts them into a master structural template. They are standard FastAPI containers pulling data from RabbitMQ and saving it to InfluxDB.

## Diagram Details (`C3_Domain_Engines.puml`)

### Internal Components
*   **AMQP Routing Consumer:** Listens to highly specific RabbitMQ topics (e.g., only "Energy.*" topics).
*   **Engine Controller/Evaluator:** The primary business logic loop evaluating standard thresholds.
*   **ML Integration Module:** A dedicated component importing `scikit-learn` or `TensorFlow` to execute predictions.
*   **TSDB Output Synchronizer:** Formats the outputs and ships them bulk to InfluxDB.
*   **Action Publisher:** Can publish *back* to the RabbitMQ bus to trigger actions (like turning off a smart lamppost if energy is low).

### Connections
*   RabbitMQ -> AMQP Consumer -> Evaluator -> ML Module
*   Evaluator / ML Module -> TSDB Synchronizer -> InfluxDB
*   Evaluator -> Action Publisher -> RabbitMQ (Triggers)

## PlantUML Implementation
The internal plugin pattern is mapped inside `C3_Domain_Engines.puml`.
