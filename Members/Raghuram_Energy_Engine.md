# Team Member 3: Energy Domain Engine

## Overview
You are the **Energy Automation Engineer**. Your focus is on the power flow of the entire Smart City. You will build the independent service that reads solar output, monitors AC load, and executes the scheduling rules for the campus smart lampposts to optimize efficiency.

## Module Boundaries
The Energy Engine is a functional silo. A crash in your AC load-balancer should only affect power dashboards, leaving the security and EHS systems untouched.
*   **What you don't care about:** You do not care about air quality or user passwords. You act solely as the "brains" of the city's power grid. 
*   **Core Responsibilities:** 
    *   Building the **FastAPI** microservice.
    *   Using the **Command Pattern** to build automated control sequences (e.g., creating `TurnOffLamppostCommand` objects) that can be queued, executed, or paused at specific times.
    *   Writing your telemetry numbers explicitly out to **InfluxDB** alongside Member 2's data.

## Integration & Independence
Your integration works through the unified **RabbitMQ Context**.
*   **Inbound Integration:** You run a lightweight consumer that binds strictly to the `telemetry.power.*` topics. You rely entirely on Member 1 to ensure that whatever brand of solar panel the university buys, it arrives at your engine looking identical to every other solar panel.
*   **Outbound Integration:** When your logic determines a lamppost must be turned off at 11 PM, you publish a control payload down to a `commands.hardware` topic. You don't try to HTTP POST directly to the lamppost IP address, preserving total isolation.
