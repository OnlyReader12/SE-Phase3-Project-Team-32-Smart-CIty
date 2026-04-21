# Component (C3) Level: 4. Alerting & Notification Subsystem

## Overview
This folder provides the structural breakdown of the **Alerting & Notification Subsystem**. This container is responsible for bridging the gap between internal Smart City emergencies (like a failing EHS sensor) and the physical real-world delivery of offline SMS/Email alerts.

## Diagram Details (`C3_Alerting.puml`)

### Internal Components
*   **Emergency Topic Subscriber:** Secures a binding to the RabbitMQ `Alerts.*` topics, waking the container up only when a Domain Engine publishes an emergency state.
*   **Message Formatter Logic:** Takes the raw emergency object and converts it into human-readable text (e.g., converting {node: 12, AQI: 400} to "DANGER: High Smog at Campus Block A").
*   **Twilio REST Client:** Dedicated adapter handling HTTP POST mapping to the external Twilio API.
*   **SendGrid REST Client:** Dedicated adapter handling HTTP POST mapping to the external SendGrid API.

### Connections
*   RabbitMQ -> (AMQP) -> Emergency Topic Subscriber
*   Subscriber -> Message Formatter
*   Formatter -> Twilio/SendGrid Clients
*   Clients -> (HTTPS) -> Twilio/SendGrid External Systems

## PlantUML Implementation
The internal translation flows are visualized in `C3_Alerting.puml`.
