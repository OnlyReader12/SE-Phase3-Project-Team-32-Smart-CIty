# Team Member 5: Data Privacy API & RBAC Security Core

## Overview
You are the **Security & Privacy Developer**. Your tasks are incredibly high-stakes as you defend the outer walls of the Smart City ecosystem. You have two distinct but interrelated responsibilities: stopping residents from executing commands above their paygrade (RBAC), and stopping researchers from viewing protected Personal Identifiable Information (Privacy Scrubbing).

## Module Boundaries
You sit directly between the outside world and the databases.
*   **What you don't care about:** You don't build predictive models, and you don't subscribe to fast-moving sensor queues on RabbitMQ.
*   **Core Responsibilities:** 
    *   Managing the **PostgreSQL** database where all structured user schemas and RBAC roles live.
    *   Executing the **Factory/Builder Patterns** to dynamically construct dashboard data permissions when a user logs in.
    *   Executing the **Strategy Pattern** (specifically, building the `PrivacyScrubber`) to mask, delete, or anonymize columns in datasets.
    *   Exposing the specific 30-day Researcher Gateway REST endpoints using **FastAPI**.

## Integration & Independence
You control the physical entry points to the application via HTTPS requests.
*   **Inbound Integration:** You receive HTTPS requests from the Flutter UI (passwords and token verification) and from Researchers (API keys and GET dataset requests).
*   **Internal Integration:** Once you verify a JWT token via PostgreSQL, you query **InfluxDB** (populated entirely by Members 2 and 3). You never execute the Influx query without first checking the RBAC permissions. When Researchers query InfluxDB, they are forced to funnel their query through your explicit in-memory Pandas scrubbing engine, ensuring compliance by design. No other team member needs to write privacy checks inside their own code, thanks to your centralized wall.
