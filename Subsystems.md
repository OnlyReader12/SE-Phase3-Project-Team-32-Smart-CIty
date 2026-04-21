The following six-subsystem structure has been established. This modular design uses a **Microkernel (Plug-in) Architecture** to ensure the system is completely **extendable** and **maintainable** as urban services grow.

## 1. Data Ingestion & Protocol Adaptation Subsystem (The Gateway)
### 1.1 Purpose: 
    Acts as the physical entry point for all 300+ heterogeneous nodes.
### 1.2 Functionality: 
    Manages raw connectivity and uses a Driver/Adapter pattern to translate diverse protocols (MQTT, CoAP, HTTP, and camera streams) into an internal data format.
### 1.3 Architectural Driver: 
    Maintainability. New hardware or updated protocols can be integrated by adding a new adapter without modifying any core system logic.
## 2. Semantic Middleware Subsystem (The Knowledge Core)
### 2.1 Purpose: 
    Serves as the "Single Source of Truth" by standardizing all ingested data into unified "Smart City Objects".
### 2.2 Functionality: 
    Standardizes data following the OneM2M standard, providing context to raw values (e.g., mapping a specific node ID to a "Water pH Sensor" at a specific campus block).
### 2.3 Architectural Driver: 
    Extensibility. This layer decouples hardware from high-level applications, allowing sensors to be replaced without breaking dashboards or ML models.
## 3. Domain-Specific Processing Engines (The Brains)
    This subsystem is partitioned into isolated service containers ("engines") to house "ready-made" ML models and automated control logic for specific city verticals.
#### 3.1.1 EHS (Environmental Health & Safety) Engine: 
    Runs forecasting models for air and water quality and monitors safety thresholds for automated alerts.
#### 3.1.2 Energy Management Engine: 
    Orchestrates solar-to-AC load balancing and handles the automated timings for campus smart lampposts.
#### 3.1.3 Crowd & Access Management (CAM) Engine: 
    Processes camera heatmaps for crowd density and manages the Fast-Track Authentication logic to meet the critical <1-second entrance requirement.
### 3.2 Architectural Driver: 
    Fault Isolation. Isolation prevents cascading failures; if the Energy Engine crashes during an update, the CAM Engine continues to authenticate residents without interruption.
## 4. Alerting & Notification Subsystem (The Communicator)
### 4.1 Purpose: 
    Manages the logic for triggering and dispatching real-time emergency and quality alerts.
### 4.2 Functionality: 
    Specifically ensures that residents without smartphones still receive safety information via SMS and Email.
### 4.3 Architectural Driver: 
    Maintainability. Centralizing this logic allows for a single-point update if the city switches from one SMS or email gateway provider to another.
## 5. Data Privacy & Researcher Gateway (The Compliance Officer)
### 5.1 Purpose: 
    Manages external data access while strictly enforcing resident privacy.
### 5.2 Functionality: 
    Uses a Data Scrubbing Unit to strip personally identifiable information (PII) before data is stored or shared via a secure REST API for 30-day historical data.
### 5.3 Architectural Driver: 
    Adaptability. As privacy regulations evolve, only the "Scrubbing Logic" within this subsystem needs to be updated to ensure continuous compliance.
## 6. Role-Based Access (RBAC) & UI Subsystem (The Gatekeeper)
### 6.1 Purpose: 
    Enforces the constraint that not every stakeholder should have access to all types of functionality or data.
### 6.2 Functionality:
    Provides tailored dashboards for specific sub-roles:
#### 6.2.1 Management View: 
    High-level status summaries and automated timing configurations.
#### 6.2.2 Serviceability View: 
    Technical "heartbeat" logs, battery levels, and calibration statuses for maintenance teams.
#### 6.2.3 Analytics View: 
    Deep-dive tools for ML model accuracy and long-term trend analysis.
### 6.3 Architectural Driver: 
    Extensibility. New user roles or dashboard views can be added without modifying the underlying functional engines or sensor code.