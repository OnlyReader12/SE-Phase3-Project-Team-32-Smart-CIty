# Team Member 2: EHS Domain Engine

## Overview
You are the **Environment ML Engineer**. Your responsibility is managing the Environmental, Health, and Safety (EHS) logic. You are tasked with determining if the campus air and water quality levels are safe, running machine learning forecasts to predict upcoming trends, and ensuring this specific telemetry is explicitly written to the time-series database.

## Module Boundaries
Your EHS engine is an entirely independent container, isolated from the ingestion adapters and all other internal domain teams.
*   **What you don't care about:** You do not care *how* the water pH sensor talks to the network (Member 1 handles that). You also do not handle sending emails or SMS messages when an alert fires (Member 4 handles that). 
*   **Core Responsibilities:** 
    *   Building a **FastAPI** web service.
    *   Implementing the **Strategy Pattern** to load integration files for `Scikit-learn` or `TensorFlow` predictive algorithms without hard-coding them into your routes.
    *   Validating incoming Air Quality (AQI) and water pH numbers against emergency bounds.
    *   Connecting directly to **InfluxDB** via TCP to bulk-write your evaluated data.

## Integration & Independence
Your integration points are explicitly via **RabbitMQ** (for messaging) and **InfluxDB** (for data persistence).
*   **Inbound Integration:** Your service acts as an **AMQP Consumer**. You will subscribe *only* to the `telemetry.enviro.*` topics on RabbitMQ. This guarantees your container does not waste RAM processing solar panel data. 
*   **Outbound Integration:** When your engine detects a terrifyingly high AQI score, your service publishes a minimal warning payload to the `alerts.critical` RabbitMQ topic. Member 4's isolated engine will pick that up and handle the actual SMS notification. You are independent and never talk to Twilio.
