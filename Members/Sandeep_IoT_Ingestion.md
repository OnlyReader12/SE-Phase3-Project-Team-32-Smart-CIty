# Team Member 1: IoT Ingestion & Semantic Middleware

## Overview
You are the **Edge Integration Developer**. Your single overarching goal is to act as the firewall between messy physical hardware and our clean backend systems. You will build a consolidated microservice container that receives raw telemetry from 300 unpredictable outdoor sensors, cleans it up, and drops it securely onto our central message bus.

## Module Boundaries
Your module must operate entirely in isolation from the backend domain engines (Energy, EHS).
*   **What you don't care about:** You do not care what the data means, whether it triggers an alert, or how it gets saved to the database. You also do not handle any Front-end UI requests or mobile API connections.
*   **Core Responsibilities:** 
    *   Implementing TCP/UDP sockets to accept raw data.
    *   Implementing the **Adapter Pattern** to convert raw MQTT, CoAP, and HTTP signals.
    *   Leveraging **Eclipse OM2M** (Semantic Middleware) to translate the physical node data into standard JSON `SmartCityObject` payloads.

## Integration & Independence
Your only point of connection to the rest of the Smart City ecosystem is the **RabbitMQ Message Broker**.
*   **Outbound Integration:** After formatting a `SmartCityObject`, your code acts as an **AMQP Publisher**. It simply publishes the normalized JSON payload onto broad topics (e.g., `telemetry.water`, `telemetry.solar`) on the RabbiMQ exchange. 
*   **Independence:** Because you use fire-and-forget publishing, your service can run locally on your laptop without needing Member 2 or Member 3's code running. If their databases crash, your ingestion engine safely continues translating and buffering messages locally without dropping a beat.
